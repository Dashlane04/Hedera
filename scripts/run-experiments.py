#!/usr/bin/env python3
"""Run matched ns-3 scenarios. Execute inside WSL; all paths are Linux paths."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ns3-dir', type=Path, default=Path.home() / 'network-perf/ns-3')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--algorithms', nargs='+', choices=['ecmp', 'gff', 'sa'], default=['ecmp', 'gff', 'sa'])
    parser.add_argument('--workloads', nargs='+', default=['collision', 'permutation', 'mixed'])
    parser.add_argument('--seeds', nargs='+', type=int, default=[1, 2, 3])
    parser.add_argument('--duration', type=float, default=3)
    parser.add_argument('--drain', type=float, default=1)
    parser.add_argument('--k', type=int, default=4)
    parser.add_argument('--rate', default='100Mbps')
    parser.add_argument('--flow-bytes', type=int, default=8 * 1024 * 1024)
    parser.add_argument('--flows', type=int, default=32)
    parser.add_argument('--interval', type=float, default=0.1)
    parser.add_argument('--control-delay', type=float, default=0)
    parser.add_argument('--iterations', type=int, default=1000)
    parser.add_argument('--check-energy', action='store_true')
    parser.add_argument('--timeout', type=float, default=600)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.ns3_dir = args.ns3_dir.resolve()
    if not (args.ns3_dir / 'ns3').is_file():
        parser.error('ns-3 wrapper not found; set --ns3-dir')
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = args.output / 'manifest.json'
    if manifest.exists():
        parser.error('output already has a manifest; select a new directory')
    manifest.write_text(json.dumps({key: str(value) if isinstance(value, Path) else value
                                    for key, value in vars(args).items()}, indent=2) + '\n')
    count = 0
    for workload in args.workloads:
        for seed in args.seeds:
            reference = None
            for algorithm in args.algorithms:
                out = args.output / f'{workload}-seed{seed}-{algorithm}'
                if out.exists():
                    raise RuntimeError(f'refusing to overwrite {out}')
                options = dict(algorithm=algorithm, workload=workload, seed=seed, run=1,
                               k=args.k, duration=args.duration, drain=args.drain, rate=args.rate,
                               flowBytes=args.flow_bytes, flows=args.flows, interval=args.interval,
                               controlDelay=args.control_delay, iterations=args.iterations,
                               checkEnergy=int(args.check_energy), output=str(out))
                command = shlex.join(['hedera-sim'] + [f'--{key}={value}' for key, value in options.items()])
                print(command, flush=True)
                completed = subprocess.run([str(args.ns3_dir / 'ns3'), 'run', command, '--no-build'],
                                           cwd=args.ns3_dir, text=True, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, timeout=args.timeout)
                out.mkdir(parents=True, exist_ok=True)
                (out / 'run.log').write_text(completed.stdout)
                print(completed.stdout, flush=True)
                if completed.returncode:
                    raise RuntimeError(f'scenario failed; inspect {out / "run.log"}')
                workload_bytes = (out / 'workload.csv').read_bytes()
                if reference is None:
                    reference = workload_bytes
                elif workload_bytes != reference:
                    raise RuntimeError(f'workload mismatch for {workload}, seed={seed}')
                count += 1
    print(f'Completed {count} matched runs under {args.output}')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
