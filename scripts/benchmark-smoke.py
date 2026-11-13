#!/usr/bin/env python3
"""Checks new reference, persistent traffic and Poisson workload before studies."""
import argparse
import csv
import json
from pathlib import Path
import shlex
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ns3-dir',type=Path,default=Path.home()/'network-perf/ns-3')
    a=p.parse_args(); root=Path(__file__).resolve().parents[1]
    cases=[('finite-reference',dict(algorithm='nonblocking',workload='single',flowBytes=262144)),
           ('finite-fat',dict(algorithm='ecmp',workload='single',flowBytes=262144)),
           ('poisson',dict(algorithm='sa',workload='poisson',duration=2,arrivalStop=0.6,
                           meanFlowBytes=131072,offeredLoad=0.15,hashMix='avalanche',checkEnergy=1))]
    for alg in ('ecmp','gff','sa','nonblocking'):
        cases.append(('persistent-'+alg,dict(algorithm=alg,workload='stride',trafficMode='sustained',
                      duration=1,measureStart=0.4,measureEnd=0.9,hashMix='avalanche',checkEnergy=1)))
    for demand in ('natural','measured'):
        cases.append(('persistent-gff-'+demand+'-diagnostic',dict(algorithm='gff',workload='stride',
                      trafficMode='sustained',duration=1,measureStart=0.4,measureEnd=0.9,
                      hashMix='avalanche',checkEnergy=1,diagnostics=1,demandMode=demand)))
    reference=None; unloaded={}
    for name,options in cases:
        out=a.output.resolve()/name
        if out.exists(): raise RuntimeError(f'Output exists: {out}')
        command=shlex.join(['hedera-sim']+[f'--{k}={v}' for k,v in (options|dict(output=str(out))).items()])
        result=subprocess.run([str(a.ns3_dir/'ns3'),'run',command,'--no-build'],cwd=a.ns3_dir,
                              text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300)
        out.mkdir(parents=True,exist_ok=True); (out/'run.log').write_text(result.stdout)
        print(result.stdout,flush=True)
        if result.returncode: raise RuntimeError(name)
        s=json.loads((out/'summary.json').read_text())
        if name.startswith('persistent-'):
            content=(out/'workload.csv').read_bytes()
            if reference is not None: assert content==reference
            reference=content
            assert s['completion_fraction'] is None and s['mean_fct_completed_s'] is None
            assert s['window_goodput_mbps']>0
            assert abs(s['window_goodput_mbps']-s['cut_payload_goodput_mbps'])<1e-6
        if name=='finite-reference':
            assert s['completed']==1
            with (out/'nodes.csv').open() as f: assert len(list(csv.DictReader(f)))==17
        if name.startswith('finite-'): unloaded[name]=s['mean_fct_completed_s']
        if name=='poisson':
            with (out/'workload.csv').open() as f: rows=list(csv.DictReader(f))
            assert all(0.2<float(r['start'])<0.6 and int(r['bytes'])>0 for r in rows)
            assert len({r['bytes'] for r in rows})>1
    subprocess.run(['python3',str(root/'scripts/validate-results.py'),str(a.output.resolve())],check=True)
    baseline=a.output.resolve()/'persistent-gff'
    instrumented=a.output.resolve()/'persistent-gff-natural-diagnostic'
    assert (baseline/'flows.csv').read_bytes()==(instrumented/'flows.csv').read_bytes(), 'diagnostics changed delivery'
    plain=json.loads((baseline/'summary.json').read_text()); traced=json.loads((instrumented/'summary.json').read_text())
    assert plain['window_goodput_mbps']==traced['window_goodput_mbps'], 'diagnostics changed window goodput'
    assert abs(unloaded['finite-reference']-unloaded['finite-fat'])<0.01*unloaded['finite-fat']
    print('PASS: reference / persistent / Poisson / measured-demand / passive diagnostics checks')

if __name__=='__main__': main()
