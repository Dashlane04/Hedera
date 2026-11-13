#!/usr/bin/env python3
"""Build a self-contained, offline replay from measured CSV logs; no packet animation."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from metrics import read_rows, run_metrics, phase_metrics


def path_nodes(text):
    return [int(x) for x in text.split('-')] if text else []


def pack(directory):
    summary=json.loads((directory/'summary.json').read_text())
    nodes=[dict(id=int(n['model_node']),kind=n['kind']) for n in read_rows(directory/'nodes.csv')]
    links={}; frames=defaultdict(dict)
    for r in read_rows(directory/'links.csv'):
        i=int(r['link_id']); links[i]=dict(id=i,src=int(r['from']),dst=int(r['to']))
        frames[float(r['time'])][i]=[float(r['utilization']),int(r['queue_packets']),int(r['drops_total'])]
    metrics,flow_details,cohorts=run_metrics(directory,summary)
    flows=[]
    for raw,detail in zip(read_rows(directory/'flows.csv'),flow_details):
        flows.append(detail|dict(firstDetected=float(raw.get('first_detected_s',-1))))
    routes=[dict(time=float(r['time']),flow=int(r['flow_id']),reason=r['reason'],old=path_nodes(r['old_path']),path=path_nodes(r['new_path']))
            for r in read_rows(directory/'routes.csv')]
    demand=[dict(time=float(r['time']),flow=int(r['flow_id']),measured=float(r['measured_fraction']),demand=float(r['selected_demand']),planned=path_nodes(r['planned_path']))
            for r in read_rows(directory/'controller-flows.csv')]
    tcp=[]; previous={}
    for r in read_rows(directory/'tcp-samples.csv'):
        fid=int(r['flow_id']); t=float(r['time']); rx=int(r['rx_bytes'])
        pt,prx=previous.get(fid,(0,0)); previous[fid]=(t,rx)
        tcp.append(dict(time=t,flow=fid,rate=(rx-prx)*8/(t-pt)/1e6,cwnd=int(r['cwnd_bytes']),retransmissions=int(r['retransmissions'])))
    events=[dict(time=float(r['time']),flow=int(r['flow_id']),event=r['event'],age=float(r['age_s']),plan=int(r['plan_id']))
            for r in read_rows(directory/'control-events.csv')]
    events.extend(dict(time=float(r['time']),flow=int(r['flow_id']),event=r['event'],cohort=r['cohort'])
                  for r in read_rows(directory/'workload-events.csv'))
    goodput=[dict(time=float(r['time']),rate=float(r['payload_bps'])/1e6) for r in read_rows(directory/'goodput.csv')]
    return dict(name=directory.name,summary=summary,nodes=nodes,links=[links[i] for i in sorted(links)],
                frames=[dict(time=t,links=[rows.get(i,[0,0,0]) for i in sorted(links)]) for t,rows in sorted(frames.items())],
                flows=flows,routes=sorted(routes,key=lambda r:r['time']),demand=demand,tcp=tcp,
                events=sorted(events,key=lambda r:r['time']),goodput=goodput,metrics=metrics,cohorts=cohorts,
                phases=[dict(name=r['name'],start=float(r['start']),end=float(r['end'])) for r in read_rows(directory/'phases.csv')],
                phaseMetrics=phase_metrics(directory))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs',type=Path,nargs='+')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); directories=[]
    for item in a.inputs:
        directories.extend([item] if (item/'summary.json').is_file() else sorted(x.parent for x in item.rglob('summary.json')))
    directories=list(dict.fromkeys(x.resolve() for x in directories))
    if not directories: p.error('No simulation results found')
    data=dict(schema=1,runs=[pack(d) for d in directories])
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('<','\\u003c')
    template=Path(__file__).resolve().parents[1]/'web/replay.html'
    a.output.parent.mkdir(parents=True,exist_ok=True)
    if a.output.exists(): p.error('Output exists; choose a new replay file')
    a.output.write_text(template.read_text(encoding='utf-8').replace('__HEDERA_DATA__',payload),encoding='utf-8')
    print(f'Exported {len(directories)} runs to {a.output} ({a.output.stat().st_size:,} bytes)')


if __name__=='__main__': main()
