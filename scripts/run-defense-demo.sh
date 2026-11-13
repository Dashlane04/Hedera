#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_OUTPUT="${1:-$PROJECT_ROOT/results/demo-$(date -u +%Y%m%dT%H%M%SZ)}"
# Build also runs core tests and prevents accidentally demonstrating a stale binary.
bash "$PROJECT_ROOT/scripts/build-wsl.sh"
python3 "$PROJECT_ROOT/scripts/benchmark-study.py" --suite demo --jobs 1 --output "$DEMO_OUTPUT" \
  --ns3-dir "${NS3_DIR:-$HOME/network-perf/ns-3}"
python3 "$PROJECT_ROOT/scripts/validate-results.py" "$DEMO_OUTPUT"
python3 "$PROJECT_ROOT/scripts/analyze-followup.py" --demo "$DEMO_OUTPUT" --demo-only --output "$DEMO_OUTPUT/figures"
printf '\nDemo ready: %s/figures/demo-timeline.png\n' "$DEMO_OUTPUT"
