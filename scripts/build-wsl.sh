#!/usr/bin/env bash
set -euo pipefail
# Limit this process's PATH only. Avoid slow CMake probes into Windows mounts.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
NS3_DIR="${NS3_DIR:-$HOME/network-perf/ns-3}"
JOBS="${JOBS:-4}"
if [[ ! -f "$NS3_DIR/ns3" ]]; then
    printf 'ns-3 not found: %s\nSet NS3_DIR to an existing ns-3.47 checkout.\n' "$NS3_DIR" >&2
    exit 1
fi
if [[ "$(tr -d '\r\n' < "$NS3_DIR/VERSION")" != "3.47" ]]; then
    printf 'This scenario is validated against ns-3.47; found another VERSION.\n' >&2
    exit 1
fi
SCENARIO=hedera
PROGRAM=hedera-sim
if [[ "${HEDERA_PAPER_BUILD:-0}" == 1 ]]; then
    SCENARIO=hedera-paper
    PROGRAM=hedera-paper-sim
fi
DEST="$NS3_DIR/scratch/$SCENARIO"
if [[ -d "$DEST" && ! -f "$DEST/.network-perf-managed" ]] && [[ -n "$(ls -A "$DEST")" ]]; then
    printf 'Refusing to overwrite unmanaged scratch directory: %s\n' "$DEST" >&2
    exit 1
fi
mkdir -p "$DEST"
printf '%s\n' "$PROJECT_ROOT" > "$DEST/.network-perf-managed"
for source in "$PROJECT_ROOT"/sim/*; do
    [[ -f "$source" ]] || continue
    target="$DEST/$(basename "$source")"
    if [[ "$SCENARIO" == hedera-paper && "$(basename "$source")" == CMakeLists.txt ]]; then
        sed 's/EXECNAME hedera-sim/EXECNAME hedera-paper-sim/;s|/scratch/hedera$|/scratch/hedera-paper|' "$source" > "$target"
    elif ! cmp -s -- "$source" "$target"; then
        cp -- "$source" "$target"
    fi
done
cmake -S "$PROJECT_ROOT" -B "$HOME/network-perf/hedera-core-build" -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build "$HOME/network-perf/hedera-core-build" -j "$JOBS"
ctest --test-dir "$HOME/network-perf/hedera-core-build" --output-on-failure
cd "$NS3_DIR"
./ns3 configure
./ns3 build "$PROGRAM" -j "$JOBS"
printf '\nBuilt scenario. Try:\ncd %q\n./ns3 run "%s --algorithm=ecmp --output=%s/results/ecmp"\n' "$NS3_DIR" "$PROGRAM" "$PROJECT_ROOT"
