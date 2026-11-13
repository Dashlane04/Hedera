#!/usr/bin/env python3
"""Figures and acceptance checks for the architecture/workload upgrade."""
import argparse
import csv
import json
from pathlib import Path
import statistics
from metrics import read_rows, background_series, phase_metrics


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dynamic',type=Path,required=True)
    p.add_argument('--control',type=Path,required=True)
    p.add_argument('--oracle',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                         'axes.facecolor':'#faf8f3','figure.facecolor':'#faf8f3'})
    colors={'ecmp':'#a5b0ae','gff':'#277a70','sa':'#bd8754','nonblocking':'#52759f'}
    fig,axes=plt.subplots(2,1,figsize=(10,6.7),sharex=True,layout='constrained')
    checks=[]; phase_rows=[]
    for path in sorted(a.dynamic.rglob('summary.json')):
        directory=path.parent; s=json.loads(path.read_text())
        phase_rows.extend(dict(algorithm=s['algorithm'],seed=s['seed'])|r for r in phase_metrics(directory))
        if s['seed']!=1: continue
        rows=read_rows(directory/'goodput.csv'); bg=background_series(directory)
        axes[0].plot([float(r['time']) for r in rows],[float(r['payload_bps'])/1e6 for r in rows],label=s['algorithm'],color=colors[s['algorithm']])
        axes[1].plot([r['time'] for r in bg],[r['mbps'] for r in bg],label=s['algorithm'],color=colors[s['algorithm']])
    for ax in axes:
        for x in [3,6]: ax.axvline(x,color='#748481',ls='--',lw=1)
        ax.axvspan(3,6,color='#bd8754',alpha=.08); ax.grid(alpha=.15); ax.set_ylim(bottom=0)
    axes[0].set_ylabel('Aggregate goodput (Mbit/s)'); axes[1].set_ylabel('Background goodput (Mbit/s)')
    axes[1].set_xlabel('Simulation time (s)'); axes[0].legend(ncol=4)
    axes[0].set_title('Dynamic load | illustrative matched seed 1 | burst sources active 3–6 s')
    fig.savefig(a.output/'dynamic-timeline.png',dpi=180); plt.close(fig)
    # Measured wire utilization, not the scheduler demand/reservation model.
    fig,axes=plt.subplots(3,1,figsize=(10,8),sharex=True,layout='constrained')
    for ax,alg in zip(axes,['ecmp','gff','sa']):
        directory=a.dynamic/f'phased-load-s1-{alg}'
        rows=read_rows(directory/'links.csv'); ids=sorted({int(r['link_id']) for r in rows if int(r['from'])>=16 and int(r['to'])>=16})
        times=sorted({float(r['time']) for r in rows}); lookup={(int(r['link_id']),float(r['time'])):float(r['utilization']) for r in rows}
        matrix=np.array([[lookup[(i,t)] for t in times] for i in ids])
        image=ax.imshow(matrix,aspect='auto',origin='lower',extent=[times[0],times[-1],0,len(ids)],vmin=0,vmax=1,cmap='YlGnBu')
        ax.set_ylabel(alg.upper()+'\nfabric link index'); ax.axvline(3,color='#bd8754',ls='--'); ax.axvline(6,color='#bd8754',ls='--')
    axes[0].set_title('Measured directed fabric-link utilization | same seed and link order')
    axes[-1].set_xlabel('Simulation time (s)'); fig.colorbar(image,ax=axes,label='Wire utilization',shrink=.7)
    fig.savefig(a.output/'link-utilization.png',dpi=180); plt.close(fig)
    records=read_rows(a.oracle); groups={}
    for r in records: groups.setdefault(int(r['steps']),[]).append(r)
    fig,axes=plt.subplots(1,2,figsize=(9,3.6),layout='constrained')
    steps=sorted(groups)
    axes[0].plot(range(len(steps)),[statistics.mean(int(r['optimal']) for r in groups[n]) for n in steps],'-o',color='#277a70')
    axes[1].plot(range(len(steps)),[statistics.mean(float(r['absolute_gap']) for r in groups[n]) for n in steps],'-o',color='#bd8754')
    for ax in axes: ax.set_xticks(range(len(steps)),steps); ax.set_xlabel('SA iteration budget'); ax.grid(alpha=.15)
    axes[0].set_ylabel('Fraction matching exact minimum H'); axes[0].set_ylim(0,1.05); axes[1].set_ylabel('Mean absolute energy gap')
    fig.suptitle('Exact SA state-space comparison | 13 small cases × 5 seeds per budget')
    fig.savefig(a.output/'oracle-quality.png',dpi=180); plt.close(fig)
    summaries={p.parent.name:json.loads(p.read_text()) for p in a.control.rglob('summary.json')}
    checks.append(dict(check='coalescing_replaces_waiting',passed=all(summaries[f'delayed-coalesce-s1-{alg}']['plans_replaced']>0 for alg in ['gff','sa'])))
    checks.append(dict(check='fifo_preserves_waiting',passed=all(summaries[f'delayed-fifo-s1-{alg}']['plans_replaced']==0 for alg in ['gff','sa'])))
    checks.append(dict(check='age_limit_expires_plans',passed=summaries['aged-plans-s1-gff']['plans_expired']>0))
    checks.append(dict(check='finished_flow_not_installed',passed=summaries['finished-before-install-s1-gff']['inactive_install_skips']>0))
    checks.append(dict(check='SA_not_below_exact_minimum',passed=all(float(r['sa_energy'])+1e-8>=float(r['oracle_energy']) for r in records)))
    (a.output/'acceptance.json').write_text(json.dumps(dict(checks=checks,oracle_rows=len(records),dynamic_runs=len(list(a.dynamic.rglob('summary.json'))),control_runs=len(summaries)),indent=2))
    if not all(r['passed'] for r in checks): raise AssertionError(checks)
    with (a.output/'dynamic-phases.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(phase_rows[0])); writer.writeheader(); writer.writerows(phase_rows)
    for name,s in sorted(summaries.items()): print(name,{k:s[k] for k in ['plans_submitted','plans_installed','plans_replaced','plans_expired','inactive_install_skips','pending_plans_at_stop']})
    print('PASS: upgrade acceptance checks and figures')


if __name__=='__main__': main()
