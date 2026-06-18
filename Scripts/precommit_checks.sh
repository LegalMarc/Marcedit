#!/bin/bash
# precommit_checks.sh — tracked pre-commit checks for Marcedit
#
# Install as your git pre-commit hook:
#   ln -sf "$(git rev-parse --show-toplevel)/Scripts/precommit_checks.sh" \
#          "$(git rev-parse --show-toplevel)/.git/hooks/pre-commit"
#
# Runs the Python 3.11 version gate first, then the critical unit tests.

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ── Python 3.11 version gate ──────────────────────────────────────────────────
# The bundled framework (Sources/Marcedit/Frameworks/Python.framework) and CI
# both target Python 3.11.  The vendored *.cpython-311-darwin.so extensions will
# NOT load under any other interpreter version.  Fail fast with an actionable
# message rather than surfacing confusing import errors later.

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "unknown")
PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo "0")
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "0")

if [ "$PYTHON_MAJOR" != "3" ] || [ "$PYTHON_MINOR" != "11" ]; then
    echo -e "${RED}[ERROR] Python version mismatch.${NC}"
    echo ""
    echo "  Marcedit targets Python 3.11 (bundled framework + CI)."
    echo "  Detected: Python ${PYTHON_VERSION}"
    echo ""
    echo "  The vendored .cpython-311-darwin.so modules will not load under"
    echo "  any other interpreter version.  Tests may pass locally on ${PYTHON_VERSION}"
    echo "  while masking real 3.11-specific failures."
    echo ""
    echo "  Fix: activate a Python 3.11 virtual environment before committing:"
    echo "    source .venv/bin/activate   # if created with python3.11 -m venv .venv"
    echo ""
    exit 1
fi

echo -e "${GREEN}[OK] Python ${PYTHON_VERSION}${NC}"

# ── Unit tests ────────────────────────────────────────────────────────────────

# Check if pytest is available
if ! python3 -c "import pytest" 2>/dev/null; then
    echo -e "${YELLOW}[WARN] pytest not found, skipping tests${NC}"
    exit 0
fi

echo "Running critical unit tests..."
if python3 -m pytest tests/test_editor_core.py tests/test_reflow_synthesizer.py tests/test_performance_regression.py tests/test_scrub_annotations.py -v -q --tb=line; then
    echo -e "${GREEN}[OK] Tests passed${NC}"
    exit 0
else
    echo -e "${RED}[ERROR] Tests failed${NC}"
    echo "Commit aborted. Fix failing tests or ask a maintainer for a hook bypass if truly needed."
    exit 1
fi
