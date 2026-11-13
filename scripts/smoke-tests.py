#!/usr/bin/env python3
"""Small integration checks beyond the comparison study; run after build-wsl.sh."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ns3-dir', type=Path, default=Path.home() / 'network-perf/ns-3')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    ns3_dir = args.ns3_dir.resolve()
    out_root = args.output.resolve()
    cases = []
    for algorithm in ['ecmp', 'gff', 'sa']:
        cases.append((f'locality-{algorithm}', dict(algorithm=algorithm,
                      workloadFile=str(root / 'examples/locality.csv'), checkEnergy=1)))
    cases += [
        ('k8-single', dict(algorithm='ecmp', k=8, workload='single', flowBytes=262144)),
        ('delayed-gff', dict(algorithm='gff', workload='collision', controlDelay=0.02)),
        ('unfinished-hotspot', dict(algorithm='sa', workload='hotspot', flows=4,
                                   flowBytes=1024 * 1024 * 1024, duration=0.8,
                                   checkEnergy=1)),
        ('staggered-local', dict(algorithm='ecmp', workload='staggered', flows=8,
                                flowBytes=262144, duration=1, localProbability=1)),
        ('staggered-remote', dict(algorithm='ecmp', workload='staggered', flows=8,
                                 flowBytes=262144, duration=1, localProbability=0)),
    ]
    locality_reference = None
    for name, options in cases:
        out = out_root / name
        if out.exists():
            raise RuntimeError(f'refusing to overwrite {out}')
        options['output'] = str(out)
        command = shlex.join(['hedera-sim'] + [f'--{k}={v}' for k, v in options.items()])
        completed = subprocess.run([str(ns3_dir / 'ns3'), 'run', command, '--no-build'],
                                   cwd=ns3_dir, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=300)
        out.mkdir(parents=True, exist_ok=True)
        (out / 'run.log').write_text(completed.stdout)
        print(completed.stdout, flush=True)
        if completed.returncode:
            raise RuntimeError(f'{name} failed')
        summary = json.loads((out / 'summary.json').read_text())
        if name.startswith('locality-'):
            content = (out / 'workload.csv').read_bytes()
            if locality_reference is not None:
                assert content == locality_reference
            locality_reference = content
        if name == 'unfinished-hotspot':
            assert summary['completed'] == 0
            assert summary['mean_fct_completed_s'] is None
            assert summary['p95_fct_completed_s'] is None
        else:
            assert summary['completed'] == summary['flows'], name
        if name.startswith('staggered-'):
            import csv
            with (out / 'workload.csv').open() as stream:
                for flow in csv.DictReader(stream):
                    same_pod = int(flow['src']) // 4 == int(flow['dst']) // 4
                    assert same_pod == (name == 'staggered-local')
        if name == 'delayed-gff':
            assert summary['route_changes'] > 0
            with (out / 'routes.csv').open() as stream:
                import csv
                for route in csv.DictReader(stream):
                    if route['reason'] == 'gff':
                        # Snapshot ticks end in .0; apply time ends in .02.
                        ticks = (float(route['time']) - 0.02) / 0.1
                        assert abs(ticks - round(ticks)) < 1e-6
    subprocess.run(['python3', str(root / 'scripts/validate-results.py'), str(out_root)], check=True)
    print(f'PASS {len(cases)} integration scenarios.')


if __name__ == '__main__':
    main()
