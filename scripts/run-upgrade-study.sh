#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
OUT="${1:-$PROJECT_ROOT/results/upgrade-$(date +%Y%m%d-%H%M%S)}"
OUT="$(realpath -m -- "$OUT")"
if [[ -e "$OUT" ]]; then printf 'Choose a new output directory: %s\n' "$OUT" >&2; exit 1; fi
mkdir -p "$OUT/oracle"
bash scripts/build-wsl.sh
python3 tests/test_metrics.py
"$HOME/network-perf/hedera-core-build/oracle-study" "$OUT/oracle/oracle-comparisons.csv"
for suite in dynamic control-lifecycle demo; do
    python3 scripts/benchmark-study.py --suite "$suite" --jobs 2 --output "$OUT/$suite"
    python3 scripts/validate-results.py "$OUT/$suite"
    python3 scripts/analyze-benchmarks.py "$OUT/$suite"
done
if [[ -d "$PROJECT_ROOT/results/defense-demo" ]]; then
    python3 scripts/check-regression.py "$PROJECT_ROOT/results/defense-demo" "$OUT/demo"
fi
python3 scripts/benchmark-smoke.py --output "$OUT/smoke"
python3 scripts/smoke-tests.py --output "$OUT/integration"
python3 scripts/extract-oracle-snapshot.py "$OUT/dynamic/phased-load-s1-sa" --time 3.2 --output "$OUT/oracle/live-snapshot.csv"
"$HOME/network-perf/hedera-core-build/oracle-study" "$OUT/oracle/live-comparisons.csv" "$OUT/oracle/live-snapshot.csv"
python3 scripts/analyze-upgrade.py --dynamic "$OUT/dynamic" --control "$OUT/control-lifecycle" \
    --oracle "$OUT/oracle/oracle-comparisons.csv" --output "$OUT/analysis"
python3 scripts/export-replay.py "$OUT/dynamic" "$OUT/control-lifecycle" --output "$OUT/replay.html"
if command -v node >/dev/null 2>&1; then
    node tests/replay-tests.mjs "$OUT/replay.html"
else
    printf 'Replay exported. Optional offline UI logic test: node tests/replay-tests.mjs %s/replay.html\n' "$OUT"
fi
python3 scripts/summarize-upgrade.py --dynamic "$OUT/dynamic" --control "$OUT/control-lifecycle" \
    --oracle "$OUT/oracle" --analysis "$OUT/analysis" --smoke "$OUT/smoke" \
    --integration "$OUT/integration" --regression "$OUT/demo" --replay "$OUT/replay.html" \
    --markdown "$OUT/summary.md"
printf '\nFinished. Open %s/replay.html\n' "$OUT"
