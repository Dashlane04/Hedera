#!/usr/bin/env bash
set -euo pipefail
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project"
out="$(realpath -m -- "${1:?Usage: run-paper-reproduction.sh NEW_RESULTS_DIR [--long]}")"
mkdir -- "$out"
ns3_dir="${NS3_DIR:-$HOME/network-perf/ns-3}"
core="$HOME/network-perf/hedera-core-build"
HEDERA_PAPER_BUILD=1 bash scripts/build-wsl.sh
mkdir "$out/core-verified"
"$core/paper-core-study" "$out/core-verified/scheduler"
lscpu > "$out/core-verified/machine.txt"
ctest --test-dir "$core" --output-on-failure > "$out/core-verified/ctest.log"
python3 scripts/run-paper-flow.py "$core/paper-flow-study" "$out/flow"
for pair in paper16-compact:compact16 paper-mechanisms:mechanisms paper-shuffle-ack:shuffle-ack; do
    python3 scripts/benchmark-study.py --ns3-dir "$ns3_dir" --paper-build --suite "${pair%:*}" --output "$out/${pair#*:}" --jobs 2
    python3 scripts/validate-results.py "$out/${pair#*:}" | tee "$out/${pair#*:}-validation.log"
done
analyze_options=(--allow-partial-gigabit)
if [[ "${2:-}" == --long ]]; then
    for pair in paper16-scaled:scaled16 paper16:gigabit16 paper-gigabit-tcp-trace:gigabit-tcp paper-gigabit-tcp:gigabit-tcp-short paper-gigabit-bijection:gigabit-bijection; do
        python3 scripts/benchmark-study.py --ns3-dir "$ns3_dir" --paper-build --suite "${pair%:*}" --output "$out/${pair#*:}" --jobs 2 --timeout 7200
        python3 scripts/validate-results.py "$out/${pair#*:}" | tee "$out/${pair#*:}-validation.log"
    done
    analyze_options=()
fi
mkdir "$out/paper"
cp "$project/report/hedera-paper-vi/"{main.tex,README.md} "$out/paper/"
cp -R "$project/report/hedera-paper-vi/"{diagrams,fonts} "$out/paper/"
python3 scripts/analyze-paper-reproduction.py "$out" "$out/paper" "${analyze_options[@]}"
