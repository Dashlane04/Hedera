#!/usr/bin/env python3
"""Run flow-level cases, preserving one verified workload per matched group."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import itertools
import json
from pathlib import Path
import subprocess


def file_sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('executable', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--figure10-stag50-only', action='store_true',
                   help='Run only the four Fig. 10 Stag(0.5,0) cases as a supplemental batch')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    algorithms = ['ecmp', 'gff', 'sa', 'nonblocking']
    plan = list(itertools.product([16], ['randbij'], algorithms, [1, 2, 3], [1000], [1]))
    plan += list(itertools.product([32], ['stag100', 'stag50pod0', 'stag20', 'stride1', 'stride16',
                                        'stride256', 'randbij', 'rand'], algorithms, [1], [1000], [1]))
    plan += list(itertools.product([16], ['rand'], ['sa'], [1, 2], [100, 1000, 10000], [0, 1]))
    if a.figure10_stag50_only:
        plan = [case for case in plan if case[1]=='stag50pod0']
    root = Path(__file__).resolve().parents[1]
    provenance = {str(f.relative_to(root)): file_sha(f) for f in
                  [root/'tests/paper-flow-study.cc', root/'sim/hedera-core.cc', Path(__file__).resolve()]}
    a.output.joinpath('manifest.json').write_text(json.dumps({
        'plan': plan, 'source_sha256': provenance, 'binary_sha256': file_sha(a.executable),
        'nic_gbps': 1, 'tick_s': .02, 'schedule_s': 1, 'duration_s': 60,
        'window_s': [10, 50], 'offered_load': .8, 'mean_bytes': 125000000}, indent=2))

    def run(params):
        k, pattern, algorithm, seed, steps, warm = params
        name = f'k{k}-{pattern}-{algorithm}-s{seed}-i{steps}-w{warm}'
        prefix = a.output / name
        subprocess.run([str(a.executable), *map(str, params), str(prefix)], check=True)
        trace = prefix.with_suffix('.csv')
        with trace.open(newline='') as f:
            rows = list(csv.DictReader(f))
        if len(rows)!=3000 or any(float(r['max_link_load'])>1+1e-9 for r in rows):
            raise ValueError(f'Incomplete or infeasible trace: {trace}')
        window = [r for r in rows if 10<float(r['time_s'])<=50]
        if len(window)!=2000:
            raise ValueError(f'Wrong measurement window: {trace}')
        workload = prefix.with_suffix('.workload.csv')
        digest = file_sha(workload)
        print(f'{name}: {len(window)} measurement ticks', flush=True)
        return dict(name=name, k=k, hosts=k**3//4, pattern=pattern, algorithm=algorithm,
                    seed=seed, steps=steps, warm=warm, workload_sha256=digest,
                    total_gbps=sum(float(r['total_gbps']) for r in window)/len(window),
                    cut_gbps=sum(float(r['cut_gbps']) for r in window)/len(window))

    hashes = {}
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        results = list(pool.map(run, plan))
    for row in results:
        key = (row['k'], row['pattern'], row['seed'])
        digest = row['workload_sha256']
        if hashes.setdefault(key, digest)!=digest:
            raise ValueError(f'Workload mismatch: {key}')
    with a.output.joinpath('summary.csv').open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)


if __name__ == '__main__':
    main()
