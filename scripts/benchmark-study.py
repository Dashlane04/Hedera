#!/usr/bin/env python3
"""Matched 16-host research benchmark and a bounded 128-host supplement."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time
import concurrent.futures
import shutil

ALGORITHMS=['ecmp','gff','sa','nonblocking']


def make_plan(suite):
    common=dict(k=4,rate='20Mbps',hashMode='flow',hashMix='avalanche',
                duration=4,drain=1,measureStart=0.8,measureEnd=3.8,
                interval=0.1,threshold=0.1,iterations=1000,checkEnergy=0)
    plan=[]
    def group(name,options,seeds=range(1,6),algorithms=ALGORITHMS):
        plan.append(dict(name=name,options=common|options,seeds=list(seeds),algorithms=algorithms))
    if suite=='main16':
        group('persistent-stride',dict(workload='stride',trafficMode='sustained',stride=8))
        group('persistent-bijection',dict(workload='random-bijection',trafficMode='sustained'))
        group('persistent-locality',dict(workload='staggered',trafficMode='sustained',
                                         flows=16,edgeProbability=0.2,podProbability=0.3,onePerHost=1))
        group('finite-bijection',dict(workload='random-bijection',trafficMode='finite',
                                     flowBytes=1048576,duration=6,measureStart=0.2,measureEnd=6))
        group('poisson-cohort',dict(workload='poisson',trafficMode='finite',duration=6,
                                   arrivalStop=1.5,meanFlowBytes=262144,offeredLoad=0.4,
                                   measureStart=0.2,measureEnd=6))
    elif suite=='scale128':
        for k in [4,8]:
            group(f'scale-k{k}',dict(k=k,workload='stride',stride=(k**3)//8,
                                    trafficMode='sustained',duration=2,measureStart=0.5,measureEnd=1.8),[1,2])
    elif suite=='sensitivity':
        for interval in [0.05,0.2]:
            group(f'interval-{interval}',dict(workload='stride',trafficMode='sustained',stride=8,
                                            interval=interval),[1,2],['gff','sa','nonblocking'])
        for threshold in [0.02,0.2]:
            group(f'threshold-{threshold}',dict(workload='stride',trafficMode='sustained',stride=8,
                                              threshold=threshold),[1,2],['gff','sa','nonblocking'])
        group('sa-steps-100',dict(workload='stride',trafficMode='sustained',stride=8,
                                iterations=100),[1,2],['sa','nonblocking'])
        group('control-delay-20ms',dict(workload='stride',trafficMode='sustained',stride=8,
                                      controlDelay=0.02),[1,2],['gff','sa','nonblocking'])
        group('destination-hash',dict(workload='stride',trafficMode='sustained',stride=8,
                                      hashMode='destination'),[1,2])
    elif suite=='dynamic':
        group('phased-load',dict(workload='phased',trafficMode='sustained',duration=9,drain=2,
                                 measureStart=0.8,measureEnd=8.8,diagnostics=1,minRtoMs=300),[1,2,3])
    elif suite=='control-lifecycle':
        base=dict(workload='phased',trafficMode='sustained',duration=6,drain=2,
                  measureStart=0.8,measureEnd=5.8,diagnostics=1,minRtoMs=300,controlDelay=0.25)
        for policy in ['fifo','coalesce']:
            group('delayed-'+policy,base|dict(controlPolicy=policy),[1],['gff','sa'])
        group('aged-plans',base|dict(controlPolicy='fifo',maxPlanAge=0.3),[1],['gff'])
        group('finished-before-install',dict(workload='single',trafficMode='finite',flowBytes=262144,
                 duration=2,drain=2,measureStart=0.2,measureEnd=1.8,controlDelay=0.4,
                 diagnostics=1,minRtoMs=300),[1],['gff'])
    elif suite in ('paper16', 'paper16-scaled', 'paper16-compact'):
        options=dict(trafficMode='sustained',duration=60,measureStart=10,measureEnd=50,
                     rate='1Gbps' if suite=='paper16' else '20Mbps',hashMode='destination',
                     interval=5,idleTimeout=10,minRtoMs=200)
        if suite=='paper16-compact':
            options.update(duration=9,measureStart=2,measureEnd=8,interval=1,idleTimeout=2)
        for stride in ([8] if suite=='paper16' else [1,2,4,8]):
            group(f'paper-stride-{stride}',options|dict(workload='stride',stride=stride),[1])
        if suite!='paper16':
            group('paper-bijection',options|dict(workload='random-bijection'),[1,2,3])
            group('paper-hotspot',options|dict(workload='hotspot',flows=15,onePerHost=1),[1])
    elif suite=='paper-gigabit-bijection':
        group('gigabit-bijection',dict(workload='random-bijection',trafficMode='sustained',
              rate='1Gbps',hashMode='destination',duration=3,drain=.15,
              measureStart=.8,measureEnd=2.8,interval=.25,idleTimeout=1,
              minRtoMs=200,delAckCount=1),[1,2,3])
    elif suite=='paper-mechanisms':
        case=dict(workload='phased',trafficMode='sustained',duration=6,measureEnd=5.8,
                  schedulePeriod=1,diagnostics=1,minRtoMs=200,switchControl=1,controlComputeMs=100)
        group('gff-on-detection',case|dict(gffOnDetection=1),[1,2],['gff'])
        group('periodic',case,[1,2],['gff','sa'])
        failure=dict(workload='collision',trafficMode='sustained',duration=5,measureEnd=4.8,
                     minRtoMs=200,diagnostics=1)
        group('outage',failure|dict(failAt=2,failureNotice=0.05),[1,2],['ecmp','gff','sa'])
        group('healthy',failure,[1,2],['ecmp','gff','sa'])
        group('sequential-shuffle',dict(workload='shuffle',trafficMode='finite',flowBytes=1048576,
                     duration=30,measureEnd=29,minRtoMs=200),[1,2])
    elif suite in ('paper-gigabit-tcp-trace','paper-gigabit-tcp'):
        base=dict(workload='stride',stride=8,trafficMode='sustained',rate='1Gbps',
                  duration=60,measureStart=10,measureEnd=50,hashMode='destination',
                  interval=5,idleTimeout=10,minRtoMs=200,diagnostics=1)
        if suite=='paper-gigabit-tcp-trace':
            group('gigabit-reference',base,[1],['nonblocking'])
        else:
            base.update(duration=2.5,drain=.1,measureStart=1.2,measureEnd=2.4,interval=.1)
            for name,change in [('default',{}),('ack5',dict(delAckMs=5)),
                                ('ack1',dict(delAckCount=1)),('rto300',dict(minRtoMs=300))]:
                group('gigabit-'+name,base|change,[1],['nonblocking'])
    elif suite=='paper-shuffle-ack':
        group('sequential-shuffle-ack1',dict(workload='shuffle',trafficMode='finite',flowBytes=262144,
                     duration=20,measureEnd=19,minRtoMs=200,delAckCount=1,queuePackets=512),[1,2])
    elif suite=='paper60':
        # An opt-in protocol closer in duration/rate; still an independent ns-3
        # study, not a claim of reproducing unspecified original parameters.
        group('paper-duration-stride',dict(workload='stride',trafficMode='sustained',stride=8,
                                           duration=60,measureStart=10,measureEnd=50,
                                           rate='1Gbps',hashMode='destination'),[1,2,3])
    elif suite=='warmup-check':
        group('late-window-bijection',dict(workload='random-bijection',trafficMode='sustained',
                                           duration=12,measureStart=8,measureEnd=11),[1])
    elif suite=='diagnosis':
        base=dict(workload='random-bijection',trafficMode='sustained',diagnostics=1)
        group('diagnostic-persistent',base,[1])
        finite=base|dict(trafficMode='finite',flowBytes=1048576,duration=6,measureStart=0.2,measureEnd=6)
        group('diagnostic-finite',finite,[1],['nonblocking'])
        for name,change in [('no-delay',dict(matchReferenceDelay=0)),
                            ('rto100',dict(minRtoMs=100)),('queue1000',dict(queuePackets=1000))]:
            group('persistent-'+name,base|change,[1],['nonblocking'])
            group('finite-'+name,finite|change,[1],['nonblocking'])
        fixture=Path(__file__).resolve().parents[1]/'workloads/isolated-reference.csv'
        group('finite-isolated',finite|dict(workloadFile=str(fixture)),[1],['nonblocking'])
    elif suite=='ablation':
        # Same detector/GFF/order/threshold and source seeds; replace only demand.
        for workload,options in [('stride',dict(workload='stride',stride=8)),
                                 ('bijection',dict(workload='random-bijection'))]:
            for demand in ['natural','measured']:
                group(f'{workload}-{demand}',options|dict(trafficMode='sustained',demandMode=demand,
                                                        diagnostics=1,minRtoMs=300),range(1,6),['gff'])
    elif suite=='ack-check':
        base=dict(workload='random-bijection',trafficMode='sustained',diagnostics=1,packetTraceFlow=14)
        for name,change in [('legacy-ack',{}),('ack5',dict(delAckMs=5)),
                            ('ack-every1',dict(delAckCount=1)),('rto300',dict(minRtoMs=300))]:
            group('persistent-'+name,base|change,[1],['nonblocking'])
            group('finite-'+name,base|dict(trafficMode='finite',flowBytes=1048576,duration=6,
                                           measureStart=0.2,measureEnd=6)|change,[1],['nonblocking'])
    elif suite=='transport-check':
        group('bijection-rto300',dict(workload='random-bijection',trafficMode='sustained',
                                   diagnostics=1,minRtoMs=300),range(1,6))
        group('finite-rto300',dict(workload='random-bijection',trafficMode='finite',flowBytes=1048576,
                                duration=6,measureStart=0.2,measureEnd=6,diagnostics=1,
                                minRtoMs=300),range(1,6),['nonblocking'])
    elif suite=='demo':
        group('collision-demo',dict(workload='collision',trafficMode='sustained',diagnostics=1,
                                    duration=2.5,measureStart=0.2,measureEnd=2.3,
                                    minRtoMs=300,checkEnergy=1),[1],['ecmp','gff','sa'])
    return plan


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',choices=['main16','scale128','sensitivity','paper60','paper16','paper16-scaled','paper16-compact','paper-gigabit-bijection','paper-mechanisms','paper-shuffle-ack','paper-gigabit-tcp-trace','paper-gigabit-tcp','warmup-check',
                                     'diagnosis','ablation','demo','ack-check','transport-check','dynamic','control-lifecycle'],required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ns3-dir',type=Path,default=Path.home()/'network-perf/ns-3')
    p.add_argument('--paper-build',action='store_true',help='Use separate hedera-paper build')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--timeout',type=float,default=900)
    p.add_argument('--jobs',type=int,default=1,choices=[1,2,3,4])
    p.add_argument('--seeds',type=int,nargs='+',help='override suite seed list')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args(); root=Path(__file__).resolve().parents[1]
    plan=make_plan(a.suite)
    if a.seeds:
        for case in plan: case['seeds']=a.seeds
    if a.dry_run:
        print(json.dumps(plan,indent=2)); return
    a.output=a.output.resolve(); a.ns3_dir=a.ns3_dir.resolve()
    fingerprint={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'sim').glob('*')) if p.is_file()}
    # Refuse to compare outputs from a stale scratch copy with current source.
    scenario='hedera-paper' if a.paper_build else 'hedera'
    program='hedera-paper-sim' if a.paper_build else 'hedera-sim'
    for name,digest in fingerprint.items():
        copied=a.ns3_dir/'scratch'/scenario/name
        if a.paper_build and name=='CMakeLists.txt':
            expected=(root/'sim'/name).read_text().replace('EXECNAME hedera-sim','EXECNAME hedera-paper-sim').replace('/scratch/hedera\n','/scratch/hedera-paper\n')
            if copied.is_file() and copied.read_text()==expected:
                continue
        if not copied.is_file() or hashlib.sha256(copied.read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Scenario copy is stale. Run scripts/build-wsl.sh first.')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.ns3_dir,text=True).strip()
    error_bars = ('observed seed range, no confidence interval' if a.suite=='paper-gigabit-bijection'
                  else 'bootstrap percentile CI, exploratory for small n')
    manifest=dict(suite=a.suite,plan=plan,source_sha256=fingerprint,ns3_revision=revision,
                  error_bars=error_bars,
                  concurrency=a.jobs,
                  reference='single-switch; same NIC/queue/TCP and matched unloaded propagation+serialization')
    if a.paper_build: manifest['scenario']=program
    fixtures={c['options']['workloadFile'] for c in plan if 'workloadFile' in c['options']}
    if fixtures:
        manifest['input_sha256']={str(path):hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in sorted(fixtures)}
    manifest_path=a.output/'manifest.json'
    if manifest_path.exists():
        if not a.resume or json.loads(manifest_path.read_text())!=manifest:
            raise RuntimeError('Use a new output or --resume with the same plan and source.')
    else:
        if a.output.exists() and any(a.output.iterdir()): raise RuntimeError('Output must be empty')
        a.output.mkdir(parents=True,exist_ok=True); manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
        (a.output/'source').mkdir()
        for name in fingerprint: shutil.copy2(root/'sim'/name,a.output/'source'/name)
        if fixtures:
            (a.output/'inputs').mkdir()
            for path in fixtures: shutil.copy2(path,a.output/'inputs'/Path(path).name)
    total=sum(len(c['seeds'])*len(c['algorithms']) for c in plan); completed=0
    def run_one(case,seed,algorithm):
                out=a.output/f'{case["name"]}-s{seed}-{algorithm}'
                settings=case['options']|dict(seed=seed,run=1,algorithm=algorithm,output=str(out))
                summary_path=out/'summary.json'
                if summary_path.exists():
                    if not a.resume: raise RuntimeError(f'Output exists: {out}')
                else:
                    if out.exists(): raise RuntimeError(f'Incomplete output requires inspection: {out}')
                    command=shlex.join([program]+[f'--{k}={v}' for k,v in settings.items()])
                    started=time.monotonic()
                    result=subprocess.run([str(a.ns3_dir/'ns3'),'run',command,'--no-build'],cwd=a.ns3_dir,
                                          text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=a.timeout)
                    out.mkdir(parents=True,exist_ok=True); (out/'run.log').write_text(result.stdout)
                    if result.returncode: raise RuntimeError(f'Failed: {out}\n{result.stdout}')
                    summary=json.loads(summary_path.read_text())
                    summary.update(benchmark_case=case['name'],suite=a.suite,
                                   process_wall_s=time.monotonic()-started)
                    summary_path.write_text(json.dumps(summary,indent=2)+'\n')
                return out,json.loads(summary_path.read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        for case in plan:
            for seed in case['seeds']:
                reference=None
                futures=[pool.submit(run_one,case,seed,algorithm) for algorithm in case['algorithms']]
                for future in concurrent.futures.as_completed(futures):
                    out,s=future.result(); content=(out/'workload.csv').read_bytes()
                    if reference is not None and content!=reference: raise RuntimeError(f'Workload mismatch: {out}')
                    reference=content; completed+=1
                    print(f'[{completed}/{total}] {out.name}: goodput={s["window_goodput_mbps"]:.2f} Mbps, '
                          f'finite complete={s["completion_fraction"]}',flush=True)
    print(f'Finished {completed} matched runs: {a.output}',flush=True)


if __name__=='__main__': main()
