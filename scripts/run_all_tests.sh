#!/usr/bin/env bash
# run_all_tests.sh — runs pytest citation suite + live CLI quality tests
# Usage: bash scripts/run_all_tests.sh [--skip-live]
set -e

SKIP_LIVE=false
for arg in "$@"; do
  if [[ "$arg" == "--skip-live" ]]; then
    SKIP_LIVE=true
  fi
done

echo "=== pytest (citation suite) ==="
( cd "$(dirname "$0")/../backend" && pytest -m citation -v )

if [[ "$SKIP_LIVE" == "false" ]]; then
  echo ""
  echo "=== live CLI quality tests ==="
  python "$(dirname "$0")/run_quality_tests.py"
fi

echo ""
echo "=== ALL TESTS PASSED ==="
