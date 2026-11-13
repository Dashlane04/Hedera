#!/usr/bin/env python3
"""Export a complete controller tick for exact state-space comparison."""
import argparse
import csv
import json
from pathlib import Path
from collections import defaultdict
from metrics import read_rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run',type=Path);p.add_argument('--time',type=float,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    data=read_rows(a.run/'controller-flows.csv')
    times=sorted({float(r['time']) for r in data if float(r['time'])<=a.time+1e-9})
    if not times:p.error('No nonempty controller snapshot at/before requested time')
    t=times[-1];selected=[r for r in data if abs(float(r['time'])-t)<1e-9]
    endpoints={r['flow_id']:r for r in read_rows(a.run/'flows.csv')}
    initial={r['flow_id']:r['new_path'] for r in read_rows(a.run/'routes.csv') if r['reason']=='initial'}
    rows=[];loads=defaultdict(float)
    for r in selected:
        f=endpoints[r['flow_id']]
        rows.append(dict(id=int(r['flow_id']),src=int(f['src']),dst=int(f['dst']),demand=float(r['selected_demand']),baseline=initial[r['flow_id']]))
        path=[int(x) for x in r['planned_path'].split('-')]
        for edge in zip(path,path[1:]):loads[edge]+=float(r['selected_demand'])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    if a.output.exists():p.error('Choose a new snapshot output')
    with a.output.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['id','src','dst','demand','baseline']);writer.writeheader();writer.writerows(rows)
    info=dict(source_run=str(a.run),snapshot_time=t,flows=len(rows),planned_energy=sum(max(0,v-1) for v in loads.values()),
              objective='sum normalized demand overload; same SA destination-core state space')
    a.output.with_suffix('.json').write_text(json.dumps(info,indent=2))
    print(json.dumps(info))


if __name__=='__main__':main()
