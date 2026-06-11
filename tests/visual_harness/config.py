"""
Configuration for LLM-based visual evaluation.

Environment Variables:
    MARCEDIT_ALLOW_EXTERNAL_LLM: Must be "1" to send document-derived images/text
        to an external LLM service.
    ANTHROPIC_AUTH_TOKEN: Required for Claude API access (custom endpoint)
    ANTHROPIC_BASE_URL: Custom API base URL
    ANTHROPIC_API_KEY: Alternative to AUTH_TOKEN for standard Anthropic API
"""

import os

# API Configuration - supports both custom endpoint and standard Anthropic
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
ALLOW_EXTERNAL_LLM = os.environ.get("MARCEDIT_ALLOW_EXTERNAL_LLM") == "1"

# Use AUTH_TOKEN if available, otherwise fall back to API_KEY
API_KEY = ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY

# Model Configuration
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Cost Controls
MAX_TESTS_PER_RUN = 100  # Maximum tests to evaluate in one run
SKIP_PASSED_TESTS = True  # Skip tests with PASS status by default

# Evaluation Thresholds
CONFIDENCE_THRESHOLD = 0.7  # Minimum confidence to trust LLM verdict

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1

# Timeout Configuration
API_TIMEOUT_MS = int(os.environ.get("API_TIMEOUT_MS", "120000"))
API_TIMEOUT_SECONDS = API_TIMEOUT_MS / 1000

# Image Configuration
MAX_IMAGE_DIMENSION = 1568  # Max dimension for images sent to Claude
IMAGE_QUALITY = 85  # JPEG quality for image compression


def validate_config() -> tuple[bool, str]:
    """Validate configuration and return (is_valid, error_message)."""
    if not ALLOW_EXTERNAL_LLM:
        return False, "Set MARCEDIT_ALLOW_EXTERNAL_LLM=1 to enable external LLM evaluation"

    if not API_KEY:
        return False, "ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY environment variable not set"

    return True, ""
