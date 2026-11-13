#!/usr/bin/env python3
"""Compare packet outcomes with an existing matched demo, ignoring added columns/runtime."""
import argparse
import csv
import json
from pathlib import Path


def rows(path):
    with path.open(newline='') as f: return list(csv.DictReader(f))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('before',type=Path);p.add_argument('after',type=Path);a=p.parse_args()
    for alg in ['ecmp','gff','sa']:
        old=a.before/f'collision-demo-s1-{alg}';new=a.after/f'collision-demo-s1-{alg}'
        old_s=json.loads((old/'summary.json').read_text());new_s=json.loads((new/'summary.json').read_text())
        for key in ['window_goodput_mbps','received_payload_bytes','route_changes','completed','detected_large']:
            assert old_s[key]==new_s[key],(alg,key,old_s[key],new_s[key])
        for name in ['workload.csv','flows.csv','routes.csv','goodput.csv']:
            previous,current=rows(old/name),rows(new/name)
            assert len(previous)==len(current),(alg,name,'row count')
            for x,y in zip(previous,current):
                assert all(x[k]==y[k] for k in x),(alg,name,x,y)
        print('PASS unchanged packet outcomes:',alg)


if __name__=='__main__':main()
