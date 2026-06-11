"""
LLM Evaluator - Uses Claude vision to evaluate PDF edit quality.

Provides:
- LLMEvaluation dataclass for structured results
- LLMEvaluator class for running evaluations
- Batch processing with progress reporting
"""

import os
import sys
import json
import base64
import time
from dataclasses import dataclass, asdict, field
from typing import Optional
from datetime import datetime

try:
    from PIL import Image
    import io
except ImportError:
    print("Error: Pillow required. Install with: pip install pillow")
    sys.exit(1)

try:
    import anthropic
except ImportError:
    anthropic = None

# Handle both module and standalone imports
try:
    from . import config
    from . import llm_prompts
except ImportError:
    import config
    import llm_prompts


@dataclass
class LLMIssue:
    """A single issue identified by the LLM."""
    category: str
    severity: str  # low, medium, high
    description: str


@dataclass
class LLMEvaluation:
    """Result of LLM evaluation for a single test."""
    test_id: str
    verdict: str  # PERFECT, ACCEPTABLE, DEGRADED, BROKEN
    confidence: float
    issues: list[LLMIssue] = field(default_factory=list)
    suggested_fixes: list[str] = field(default_factory=list)
    summary: str = ""

    # Metadata
    evaluated_at: str = ""
    model_used: str = ""
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d["issues"] = [asdict(i) for i in self.issues]
        return d


class LLMEvaluator:
    """Evaluates PDF edit quality using Claude's vision capabilities."""

    def __init__(self, model: str = None):
        # Validate configuration
        is_valid, error = config.validate_config()
        if not is_valid:
            raise ValueError(f"Configuration error: {error}")

        if anthropic is None:
            raise ImportError(
                "anthropic package not installed. "
                "Install with: pip install anthropic"
            )

        self.model = model or config.DEFAULT_MODEL

        # Configure client with custom base URL if provided
        client_kwargs = {"api_key": config.API_KEY}
        if config.ANTHROPIC_BASE_URL:
            client_kwargs["base_url"] = config.ANTHROPIC_BASE_URL

        self.client = anthropic.Anthropic(**client_kwargs)

    def evaluate_test(self, test_result: dict, images_dir: str = None) -> LLMEvaluation:
        """
        Evaluate a single test result using Claude vision.

        Args:
            test_result: Dictionary from results.json containing test info
            images_dir: Optional override for images directory

        Returns:
            LLMEvaluation with verdict and issues
        """
        test_id = test_result.get("test_id", "UNKNOWN")

        try:
            # Load images
            images = self._load_images(test_result, images_dir)
            if not images:
                return self._error_evaluation(
                    test_id, "Could not load before/after images"
                )

            # Build test context
            test_context = {
                "edit_type": test_result.get("edit_type", "unknown"),
                "target_text": test_result.get("target_text", ""),
                "replacement_text": test_result.get("replacement_text", ""),
                "original_font": test_result.get("original_font", "Unknown"),
                "pixel_diff_pct": test_result.get("pixel_diff_pct", 0),
                "ssim_score": test_result.get("ssim_score", 0),
            }

            # Call Claude API
            evaluation = self._call_claude(test_id, images, test_context)
            return evaluation

        except anthropic.APIError as e:
            return self._error_evaluation(test_id, f"API error: {e}")
        except Exception as e:
            return self._error_evaluation(test_id, f"Evaluation failed: {e}")

    def evaluate_batch(
        self,
        results: list[dict],
        images_dir: str = None,
        progress_callback=None,
        skip_passed: bool = None
    ) -> list[LLMEvaluation]:
        """
        Evaluate multiple test results.

        Args:
            results: List of test result dictionaries
            images_dir: Optional override for images directory
            progress_callback: Optional callback(current, total, test_id)
            skip_passed: Skip tests with PASS status (default from config)

        Returns:
            List of LLMEvaluation objects
        """
        if skip_passed is None:
            skip_passed = config.SKIP_PASSED_TESTS

        # Filter results if needed
        if skip_passed:
            results = [r for r in results if r.get("status") != "PASS"]

        # Apply max tests limit
        if len(results) > config.MAX_TESTS_PER_RUN:
            print(f"Limiting to {config.MAX_TESTS_PER_RUN} tests (from {len(results)})")
            results = results[:config.MAX_TESTS_PER_RUN]

        evaluations = []
        total = len(results)

        for i, result in enumerate(results):
            test_id = result.get("test_id", "")

            if progress_callback:
                progress_callback(i + 1, total, test_id)

            evaluation = self.evaluate_test(result, images_dir)
            evaluations.append(evaluation)

            # Rate limiting - brief pause between requests
            if i < total - 1:
                time.sleep(0.5)

        return evaluations

    def _load_images(
        self, test_result: dict, images_dir: str = None
    ) -> Optional[dict[str, str]]:
        """Load and encode images as base64."""
        images = {}

        for key in ["before_image", "after_image", "diff_image"]:
            path = test_result.get(key, "")

            # Try to resolve path
            if not os.path.isabs(path) and images_dir:
                path = os.path.join(images_dir, os.path.basename(path))

            if not path or not os.path.exists(path):
                continue

            try:
                # Load and optionally resize image
                img = Image.open(path)

                # Resize if too large
                max_dim = config.MAX_IMAGE_DIMENSION
                if img.width > max_dim or img.height > max_dim:
                    ratio = min(max_dim / img.width, max_dim / img.height)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, Image.LANCZOS)

                # Convert to base64
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                b64 = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")

                label = key.replace("_image", "").upper()
                images[label] = b64

            except Exception as e:
                print(f"Warning: Could not load {path}: {e}")
                continue

        # Need at least before and after
        if "BEFORE" not in images or "AFTER" not in images:
            return None

        return images

    def _call_claude(
        self, test_id: str, images: dict[str, str], test_context: dict
    ) -> LLMEvaluation:
        """Make the Claude API call and parse response."""
        # Build message content with images
        content = []

        # Add images with labels
        for label in ["BEFORE", "AFTER", "DIFF"]:
            if label in images:
                content.append({
                    "type": "text",
                    "text": f"**{label} Image:**"
                })
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": images[label]
                    }
                })

        # Add evaluation prompt
        content.append({
            "type": "text",
            "text": llm_prompts.get_evaluation_prompt(test_context)
        })

        # Call API with retry
        response = None
        for attempt in range(config.MAX_RETRIES):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=llm_prompts.SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": content}],
                    timeout=config.API_TIMEOUT_SECONDS
                )
                break
            except anthropic.RateLimitError:
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(config.RETRY_DELAY_SECONDS * (attempt + 1))
                else:
                    raise

        if not response:
            return self._error_evaluation(test_id, "No response from API")

        # Parse response
        return self._parse_response(test_id, response)

    def _parse_response(self, test_id: str, response) -> LLMEvaluation:
        """Parse Claude's response into LLMEvaluation."""
        try:
            # Extract text content
            text = ""
            for block in response.content:
                if block.type == "text":
                    text = block.text
                    break

            # Parse JSON from response
            # Handle markdown code blocks
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            data = json.loads(text.strip())

            # Build evaluation
            issues = [
                LLMIssue(
                    category=i.get("category", "UNKNOWN"),
                    severity=i.get("severity", "medium"),
                    description=i.get("description", "")
                )
                for i in data.get("issues", [])
            ]

            return LLMEvaluation(
                test_id=test_id,
                verdict=data.get("verdict", "UNKNOWN"),
                confidence=float(data.get("confidence", 0.5)),
                issues=issues,
                suggested_fixes=data.get("suggested_fixes", []),
                summary=data.get("summary", ""),
                evaluated_at=datetime.now().isoformat(),
                model_used=self.model
            )

        except json.JSONDecodeError as e:
            return self._error_evaluation(
                test_id, f"Failed to parse LLM response: {e}"
            )
        except Exception as e:
            return self._error_evaluation(
                test_id, f"Error processing response: {e}"
            )

    def _error_evaluation(self, test_id: str, error_msg: str) -> LLMEvaluation:
        """Create an error evaluation."""
        return LLMEvaluation(
            test_id=test_id,
            verdict="ERROR",
            confidence=0.0,
            issues=[],
            suggested_fixes=[],
            summary="",
            evaluated_at=datetime.now().isoformat(),
            model_used=self.model,
            error_message=error_msg
        )


def save_evaluations(evaluations: list[LLMEvaluation], output_path: str):
    """Save evaluations to JSON file."""
    summary = {
        "perfect": sum(1 for e in evaluations if e.verdict == "PERFECT"),
        "acceptable": sum(1 for e in evaluations if e.verdict == "ACCEPTABLE"),
        "degraded": sum(1 for e in evaluations if e.verdict == "DEGRADED"),
        "broken": sum(1 for e in evaluations if e.verdict == "BROKEN"),
        "error": sum(1 for e in evaluations if e.verdict == "ERROR"),
    }

    output = {
        "evaluated_at": datetime.now().isoformat(),
        "total": len(evaluations),
        "summary": summary,
        "evaluations": [e.to_dict() for e in evaluations]
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nLLM evaluations saved to: {output_path}")
    print(f"Summary: {summary}")


def load_evaluations(path: str) -> list[LLMEvaluation]:
    """Load evaluations from JSON file."""
    with open(path, 'r') as f:
        data = json.load(f)

    evaluations = []
    for e in data.get("evaluations", []):
        issues = [
            LLMIssue(
                category=i.get("category", ""),
                severity=i.get("severity", ""),
                description=i.get("description", "")
            )
            for i in e.get("issues", [])
        ]

        evaluations.append(LLMEvaluation(
            test_id=e.get("test_id", ""),
            verdict=e.get("verdict", ""),
            confidence=e.get("confidence", 0),
            issues=issues,
            suggested_fixes=e.get("suggested_fixes", []),
            summary=e.get("summary", ""),
            evaluated_at=e.get("evaluated_at", ""),
            model_used=e.get("model_used", ""),
            error_message=e.get("error_message")
        ))

    return evaluations
