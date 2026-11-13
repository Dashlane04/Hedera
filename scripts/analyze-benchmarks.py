#!/usr/bin/env python3
"""Analyze matched benchmark cases, preserving censoring and reference ratios."""
import argparse
import csv
import json
import math
from pathlib import Path
import random
import statistics
import xml.etree.ElementTree as ET
from metrics import run_metrics, phase_metrics

ORDER=['ecmp','gff','sa','nonblocking']
COLORS=['#64748b','#0f766e','#d97706','#2563eb']


def ci(values):
    values=[float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not values: return None,None,None,0
    mean=statistics.mean(values)
    if len(values)<2: return mean,None,None,len(values)
    if min(values)==max(values): return mean,mean,mean,len(values)
    rng=random.Random(8128)
    samples=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(5000))
    return mean,samples[int(0.025*len(samples))],samples[int(0.975*len(samples))],len(values)


def write_csv(path,rows):
    if not rows: return
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def read_csv(path):
    with path.open(newline='') as f: return list(csv.DictReader(f))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path)
    p.add_argument('--scheduler-csv',type=Path)
    p.add_argument('--output',type=Path,help='Write derived tables/plots elsewhere; raw runs stay unchanged')
    a=p.parse_args(); records=[]
    out_root=a.output or a.root; out_root.mkdir(parents=True,exist_ok=True)
    for path in sorted(a.root.rglob('summary.json')):
        summary=json.loads(path.read_text())
        if 'benchmark_case' in summary: records.append((path.parent,summary))
    if not records: p.error('No benchmark-study output found')
    manifest_path=a.root/'manifest.json'
    if manifest_path.is_file():
        manifest=json.loads(manifest_path.read_text())
        expected=sum(len(c['seeds'])*len(c['algorithms']) for c in manifest['plan'])
        if len(records)!=expected: p.error(f'Study incomplete: {len(records)}/{expected} runs; finish or resume first')
    lookup={(s['benchmark_case'],s['seed'],s['algorithm']):s for _,s in records}
    groups={}; per_run=[]; flow_metrics=[]; cohort_metrics=[]; phase_rows=[]
    for directory,s in records:
        case=s['benchmark_case']; reference=lookup.get((case,s['seed'],'nonblocking'))
        drops=sum(int(d.get('number')) for f in ET.parse(directory/'flow-monitor.xml').getroot().find('FlowStats')
                  for d in f.findall('packetsDropped') if int(d.get('reasonCode')) in (3,4))
        norm=s['window_goodput_mbps']/reference['window_goodput_mbps'] if reference and reference['window_goodput_mbps'] else None
        row=dict(case=case,algorithm=s['algorithm'],seed=s['seed'],hosts=s['hosts'],mode=s['traffic_mode'],
                 flows=s['flows'],completed=s['completed'],completion_fraction=s['completion_fraction'],
                 goodput_mbps=s['window_goodput_mbps'],cut_goodput_mbps=s['cut_payload_goodput_mbps'],
                 relative_to_nonblocking=norm,fraction_nic_capacity=s['window_goodput_mbps']/(s['hosts']*s['link_rate_bps']/1e6),
                 conditional_mean_fct_s=s['mean_fct_completed_s'],
                 scheduler_wall_us=s['mean_scheduler_wall_us'],queue_drops=drops)
        extra,details,cohorts=run_metrics(directory,s); row.update(extra)
        tag=dict(case=case,algorithm=s['algorithm'],seed=s['seed'],run=s.get('run',1))
        flow_metrics.extend(tag|r for r in details)
        cohort_metrics.extend(tag|r for r in cohorts)
        phase_rows.extend(tag|r for r in phase_metrics(directory))
        per_run.append(row); groups.setdefault((case,s['algorithm']),[]).append((directory,s,row))
    aggregate=[]
    for (case,alg),group in sorted(groups.items()):
        row=dict(case=case,algorithm=alg,hosts=group[0][1]['hosts'],mode=group[0][1]['traffic_mode'])
        for metric in ['goodput_mbps','cut_goodput_mbps','relative_to_nonblocking','fraction_nic_capacity','conditional_mean_fct_s','completion_fraction','scheduler_wall_us','queue_drops',
                       'conditional_p95_fct_s','jain_goodput_common_active','per_flow_goodput_p10_mbps',
                       'window_retransmissions','window_data_qdisc_drops','window_ack_qdisc_drops',
                       'route_changes','mean_install_age_s','p95_install_age_s','plans_expired','plans_replaced','inactive_install_skips']:
            mean,low,high,n=ci([entry[2][metric] for entry in group])
            row.update({metric+'_mean':mean,metric+'_ci_low':low,metric+'_ci_high':high,metric+'_n':n})
        aggregate.append(row)
    write_csv(out_root/'benchmark-runs.csv',per_run); write_csv(out_root/'benchmark-aggregate.csv',aggregate)
    write_csv(out_root/'flow-metrics.csv',flow_metrics); write_csv(out_root/'cohort-metrics.csv',cohort_metrics)
    write_csv(out_root/'phase-metrics.csv',phase_rows)
    effects=[]
    for case in sorted({s['benchmark_case'] for _,s in records}):
        for algorithm in ORDER[1:]:
            ratios=[]; completion_delta=[]; fct_speedups=[]
            seeds=sorted({s['seed'] for _,s in records if s['benchmark_case']==case})
            for seed in seeds:
                baseline=lookup.get((case,seed,'ecmp')); other=lookup.get((case,seed,algorithm))
                if not baseline or not other: continue
                if baseline['window_goodput_mbps']>0:
                    ratios.append(other['window_goodput_mbps']/baseline['window_goodput_mbps'])
                if baseline['completion_fraction'] is not None and other['completion_fraction'] is not None:
                    completion_delta.append(other['completion_fraction']-baseline['completion_fraction'])
                if baseline['completion_fraction']==1 and other['completion_fraction']==1 and other['mean_fct_completed_s']:
                    fct_speedups.append(baseline['mean_fct_completed_s']/other['mean_fct_completed_s'])
            if not ratios: continue
            row=dict(case=case,algorithm=algorithm)
            for metric,values in [('goodput_ratio_ecmp',ratios),('completion_delta_ecmp',completion_delta),
                                  ('fct_speedup_fully_completed_pairs',fct_speedups)]:
                mean,low,high,n=ci(values)
                row.update({metric+'_mean':mean,metric+'_ci_low':low,metric+'_ci_high':high,metric+'_n':n})
            effects.append(row)
    write_csv(out_root/'paired-effects.csv',effects)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':9})
    # ECDFs keep zero-goodput members. FCT ECDFs remain conditional on completion.
    for case in sorted({r['case'] for r in flow_metrics}):
        selected=[r for r in flow_metrics if r['case']==case]
        seed=min(r['seed'] for r in selected)
        fig,axes=plt.subplots(1,2,figsize=(10,3.4))
        for alg,color in zip(ORDER,COLORS):
            members=[r for r in selected if r['seed']==seed and r['algorithm']==alg]
            for ax,key in zip(axes,['goodput_mbps','fct_s']):
                values=sorted(r[key] for r in members if r[key] is not None and (key!='goodput_mbps' or r['window_overlap']))
                if values: ax.step(values,[(i+1)/len(values) for i in range(len(values))],where='post',color=color,label=alg)
        axes[0].set_xlabel('Per-flow window goodput (Mbit/s)'); axes[1].set_xlabel('FCT of completed flows (s)')
        for ax in axes: ax.set_ylabel('ECDF'); ax.set_ylim(0,1.03); ax.grid(alpha=.18)
        axes[0].legend(fontsize=8); fig.suptitle(f'{case} | illustrative seed {seed}; FCT excludes unfinished flows')
        fig.tight_layout(); fig.savefig(out_root/(case+'-flow-distribution.png'),dpi=170); plt.close(fig)
    cases=sorted({s['benchmark_case'] for _,s in records})
    for case in cases:
        selected=sorted([r for r in aggregate if r['case']==case],key=lambda r:ORDER.index(r['algorithm']))
        mode=selected[0]['mode']
        metrics=[('relative_to_nonblocking','Goodput / matched nonblocking reference'),
                 ('goodput_mbps','Payload goodput (Mbit/s)'),
                 ('scheduler_wall_us','Controller computation (wall microseconds)')]
        if mode=='finite': metrics=[metrics[0],('completion_fraction','Fraction of finite flows completed'),
                                     ('conditional_mean_fct_s','Mean FCT of completed flows (s)')]
        fig,axes=plt.subplots(1,3,figsize=(12,3.8),layout='constrained')
        for ax,(metric,title) in zip(axes,metrics):
            for index,row in enumerate(selected):
                mean=row[metric+'_mean']
                if mean is None: continue
                low,high=row[metric+'_ci_low'],row[metric+'_ci_high']
                error=None if low is None else [[max(0,mean-low)],[max(0,high-mean)]]
                ax.bar(index,mean,width=0.6,color=COLORS[ORDER.index(row['algorithm'])],yerr=error,capsize=3)
            ax.set_xticks(range(len(selected)),[r['algorithm'].upper() for r in selected],rotation=12)
            ax.set_title(title); ax.set_ylim(bottom=0); ax.grid(axis='y',alpha=0.2); ax.set_axisbelow(True)
            if metric=='relative_to_nonblocking': ax.axhline(1,color='#2563eb',linestyle=':',linewidth=1)
            if metric=='completion_fraction': ax.set_ylim(0,1.1)
        fig.suptitle(f'{case} | {selected[0]["hosts"]} hosts | {mode}\n'
                     '95% percentile bootstrap CI across matched seeds (exploratory with small n)',fontsize=11)
        fig.savefig(out_root/f'{case}.png',dpi=160); plt.close(fig)
        # One illustrative matched seed: never present it as an ensemble mean.
        seed=min(s['seed'] for _,s in records if s['benchmark_case']==case)
        fig,ax=plt.subplots(figsize=(9,3.8),layout='constrained')
        for directory,s in records:
            if s['benchmark_case']!=case or s['seed']!=seed: continue
            samples=read_csv(directory/'goodput.csv')
            ax.stairs([float(r['cut_payload_bps'])/1e6 for r in samples],
                      [0]+[float(r['time']) for r in samples],label=s['algorithm'].upper(),
                      color=COLORS[ORDER.index(s['algorithm'])],linewidth=1.2)
        example=next(s for _,s in records if s['benchmark_case']==case)
        ax.axvspan(example['measurement_start_s'],example['measurement_end_s'],color='#0f766e',alpha=0.08)
        ax.set(xlabel='Simulation time (s)',ylabel='Bidirectional host-half-cut payload (Mbit/s)',
               title=f'{case} | illustrative seed {seed}; shaded measurement window')
        ax.set_ylim(bottom=0); ax.legend(ncol=4,fontsize=8); ax.grid(alpha=0.2)
        fig.savefig(out_root/f'{case}-timeline.png',dpi=160); plt.close(fig)
    if a.scheduler_csv:
        data=read_csv(a.scheduler_csv)
        fig,axes=plt.subplots(1,3,figsize=(12,3.5),layout='constrained')
        for ax,(name,metric) in zip(axes,[('Demand estimation','estimate_us'),('GFF placement','placement_us'),('SA placement, 1000 steps','placement_us')]):
            algorithm='sa' if name.startswith('SA') else 'gff'
            for hosts in sorted({int(r['hosts']) for r in data}):
                points=[]
                for count in sorted({int(r['flows']) for r in data}):
                    values=[float(r[metric]) for r in data if r['algorithm']==algorithm and int(r['hosts'])==hosts and int(r['flows'])==count]
                    points.append((count,statistics.median(values)/1000))
                ax.plot([p[0] for p in points],[p[1] for p in points],marker='o',label=f'{hosts} hosts')
            ax.set(xlabel='Active flows',ylabel='Median wall time (ms)',title=name)
            ax.set_xscale('log',base=2); ax.set_yscale('log'); ax.grid(alpha=0.2); ax.legend(fontsize=8)
        fig.savefig(out_root/'scheduler-scaling.png',dpi=160); plt.close(fig)
    report=['# Benchmark results','',
            'These are independent ns-3 experiments, not a numerical reproduction of the 2010 paper.',
            'The single-switch reference matches NIC, TCP, queues and unloaded path delay (propagation plus serialization). Internal contention is removed. It remains a model reference, not a proven mathematical bound.',
            'Ratios use the matching seed. Bootstrap intervals with 2-5 seeds are exploratory. Conditional FCT must be read with completion fraction.',
            '', '| Case | Algorithm | Seeds | Goodput Mbps | / reference | Finite completion | Conditional FCT s |',
            '|---|---|---:|---:|---:|---:|---:|']
    def fmt(v): return 'n/a' if v is None else f'{v:.4g}'
    for r in aggregate:
        report.append(f'| {r["case"]} | {r["algorithm"]} | {r["goodput_mbps_n"]} | {fmt(r["goodput_mbps_mean"])} | '
                      f'{fmt(r["relative_to_nonblocking_mean"])} | {fmt(r["completion_fraction_mean"])} | {fmt(r["conditional_mean_fct_s_mean"])} |')
    report += ['', '## Interpretation checks', '',
               '- Persistent connections have no completion-time target: completion fraction and FCT are not applicable.',
               '- Finite cohorts preserve unfinished flows. A smaller conditional mean FCT alone does not imply improvement.',
               '- Scheduler measurements exclude energy verification in these studies, but ns-3 controller logging and load maintenance are included.',
               '- Workload identity is checked byte-for-byte by the runner. Old prototype runs are retained separately.',
               '- The green timeline band is the measurement window. The timeline is one seed, not a confidence interval.', '']
    report += ['- fraction_nic_capacity is measured goodput divided by N times NIC rate, before header/ACK overhead; it is a resource ceiling, not a workload-specific optimal schedule.',
               '- Relative-to-nonblocking values above one are retained: TCP/queue feedback can make the measured model reference lower. Do not call that exceeding a theoretical optimum.', '']
    (out_root/'results.md').write_text('\n'.join(report),encoding='utf-8')
    print(f'Wrote benchmark CSVs, per-case PNGs and results.md under {out_root}')


if __name__=='__main__': main()
