#!/usr/bin/env python3
"""Explain TCP reference anomalies, demand ablation and the teaching demo."""
import argparse
import csv
import json
import math
from pathlib import Path
import random
import statistics
import xml.etree.ElementTree as ET

COLORS={'ecmp':'#64748b','gff':'#0f766e','sa':'#d97706','nonblocking':'#2563eb'}


def read(path):
    with path.open(newline='') as f: return list(csv.DictReader(f))


def write(path, rows):
    if rows:
        with path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def ci(values):
    mean=statistics.mean(values)
    if len(values)<2: return mean,None,None
    rng=random.Random(8128)
    boot=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(5000))
    return mean,boot[125],boot[4875]


def runs(root):
    result=[]
    for p in sorted(root.glob('*/summary.json')):
        result.append((p.parent,json.loads(p.read_text())))
    manifest=json.loads((root/'manifest.json').read_text())
    assert len(result)==sum(len(c['seeds'])*len(c['algorithms']) for c in manifest['plan']),root
    return result


def flow_details(directory,s):
    flows=read(directory/'flows.csv'); samples=read(directory/'tcp-samples.csv')
    events=read(directory/'tcp-events.csv'); drops=read(directory/'queue-drops.csv')
    window=s['measurement_end_s']-s['measurement_start_s']
    ips={int(r['model_node']):r['host_ip'] for r in read(directory/'nodes.csv') if r['kind']=='host'}
    ports={i:int(r['port']) for i,r in enumerate(read(directory/'workload.csv'))}
    links=read(directory/'links.csv')
    monitor=ET.parse(directory/'flow-monitor.xml').getroot()
    classified={r.get('flowId'):r for r in monitor.find('Ipv4FlowClassifier')}
    ip_stats={r.get('flowId'):r for r in monitor.find('FlowStats')}
    details=[]
    for f in flows:
        fid=int(f['flow_id'])
        ss=[r for r in samples if int(r['flow_id'])==fid]
        ee=[r for r in events if int(r['flow_id'])==fid]
        dd=[r for r in drops if int(r['flow_id'])==fid]
        link_window=[r for r in links if int(r['to'])==int(f['dst'])
                     and float(r['time'])>s['measurement_start_s']+1e-7
                     and float(r['time'])<=s['measurement_end_s']+1e-7]
        data_drops=ack_drops=0
        for flowid,cl in classified.items():
            port=ports[fid]
            data=(cl.get('sourceAddress')==ips[int(f['src'])] and cl.get('destinationAddress')==ips[int(f['dst'])]
                  and int(cl.get('destinationPort'))==port)
            ack=(cl.get('sourceAddress')==ips[int(f['dst'])] and cl.get('destinationAddress')==ips[int(f['src'])]
                 and int(cl.get('sourcePort'))==port)
            dropped=sum(int(r.get('number')) for r in ip_stats[flowid].findall('packetsDropped'))
            if data: data_drops+=dropped
            if ack: ack_drops+=dropped
        details.append(dict(run=directory.name,algorithm=s['algorithm'],mode=s['traffic_mode'],
            flow_id=fid,src=int(f['src']),dst=int(f['dst']),completed=int(f['completed']),
            rx_bytes=int(f['rx_bytes']),window_mbps=int(f['window_rx_bytes'])*8/window/1e6,
            destination_link_wire_mbps=sum(int(r['tx_bytes']) for r in link_window)*8/window/1e6,
            data_qdisc_drops=sum(r['direction']=='data' for r in dd),
            ack_qdisc_drops=sum(r['direction']=='ack' for r in dd),
            data_ip_explicit_drops=data_drops,ack_ip_explicit_drops=ack_drops,
            retransmissions=sum(r['event']=='retransmission' for r in ee),
            loss_entries=sum(r['event']=='congestion' and r['new_value']=='4' for r in ee),
            max_rto_s=max([float(r['rto_s']) for r in ss]+[0]),
            min_sample_cwnd_bytes=min([int(r['cwnd_bytes']) for r in ss if float(r['time'])>=0.5]+[4*1024*1024]),
            single_mss_sample_fraction=(sum(int(r['cwnd_bytes'])==1448 for r in ss if float(r['time'])>=0.5)
                                       /max(1,sum(float(r['time'])>=0.5 for r in ss)))))
    return details


def diagnose(roots,out,plt):
    records=[r for root in roots for r in runs(root)]
    matched={}
    for directory,s in records:
        if s['benchmark_case']=='finite-isolated': continue
        content=(directory/'workload.csv').read_bytes()
        mode=s['traffic_mode']
        if mode in matched: assert matched[mode]==content,('diagnostic workload mismatch',directory)
        matched[mode]=content
    details=[]; aggregate=[]
    for directory,s in records:
        fs=flow_details(directory,s); details.extend(fs)
        rates=[f['window_mbps'] for f in fs]
        aggregate.append(dict(run=directory.name,algorithm=s['algorithm'],mode=s['traffic_mode'],
            goodput_mbps=s['window_goodput_mbps'],completion_fraction=s['completion_fraction'],
            data_qdisc_drops=sum(f['data_qdisc_drops'] for f in fs),
            ack_qdisc_drops=sum(f['ack_qdisc_drops'] for f in fs),
            retransmissions=sum(f['retransmissions'] for f in fs),
            loss_entries=sum(f['loss_entries'] for f in fs),
            jain_window_goodput=sum(rates)**2/(len(rates)*sum(x*x for x in rates)) if sum(rates) else 0))
    write(out/'diagnostic-flows.csv',details); write(out/'diagnostic-summary.csv',aggregate)
    packet_cycles=[]
    for directory,s in records:
        trace=directory/'tcp-packets.csv'
        if not trace.is_file(): continue
        packets=read(trace); sent={}
        for r in packets:
            t=float(r['time'])
            if r['direction']=='tx' and int(r['packet_trace_bytes'])>0:
                seq=int(r['sequence']); sent.setdefault(seq,[]).append((t,int(r['packet_trace_bytes'])))
        acks=[(float(r['time']),int(r['ack'])) for r in packets if r['direction']=='rx']
        for seq,txs in sent.items():
            first,bytecount=txs[0]
            ack=next((t for t,a in acks if t>=first and a>=seq+bytecount),None)
            retx=txs[1][0] if len(txs)>1 else None
            packet_cycles.append(dict(run=directory.name,sequence=seq,payload_bytes=bytecount,
                first_tx_s=first,first_retx_s=retx,first_cumulative_ack_s=ack,
                ack_after_first_retx=retx is not None and ack is not None and ack>retx))
    write(out/'sender-packet-cycles.csv',packet_cycles)
    baseline=[(d,s) for d,s in records if s['benchmark_case']=='diagnostic-persistent']
    fig,ax=plt.subplots(figsize=(11,4.2),layout='constrained')
    for i,(directory,s) in enumerate(baseline):
        selected=[r for r in details if r['run']==directory.name]
        ax.bar([r['flow_id']+(i-1.5)*0.2 for r in selected],[r['window_mbps'] for r in selected],
               width=0.19,label=s['algorithm'].upper(),color=COLORS[s['algorithm']])
    ax.set(xticks=range(16),xlabel='Flow ID',ylabel='Window payload goodput (Mbit/s)',
           title='Random bijection, seed 1 | legacy TCP: MinRTO 20 ms, delayed ACK 200 ms')
    ax.legend(ncol=4); ax.grid(axis='y',alpha=0.2); ax.set_axisbelow(True)
    fig.savefig(out/'reference-per-flow.png',dpi=170); plt.close(fig)
    ref=next(d for d,s in baseline if s['algorithm']=='nonblocking')
    ss=read(ref/'tcp-samples.csv')
    fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True,layout='constrained')
    for fid in [10,14]:
        values=[r for r in ss if int(r['flow_id'])==fid]
        axes[0].step([float(r['time']) for r in values],[int(r['cwnd_bytes'])/1448 for r in values],where='post',label=f'flow {fid}')
        axes[1].step([float(r['time']) for r in values],[float(r['rto_s'])*1000 for r in values],where='post',label=f'flow {fid}')
    axes[0].set(ylabel='Congestion window (MSS)',title='Reference slow flows | samples every 100 ms, seed 1')
    axes[0].axhline(1,color='black',ls=':',lw=1); axes[0].legend()
    axes[1].set(xlabel='Simulation time (s)',ylabel='Sender RTO (ms)')
    for ax in axes: ax.grid(alpha=0.2)
    fig.savefig(out/'reference-tcp.png',dpi=170); plt.close(fig)
    variants=['diagnostic-persistent','persistent-no-delay','persistent-rto100','persistent-queue1000',
              'persistent-ack5','persistent-ack-every1','persistent-rto300']
    names=['Legacy','No virtual delay','MinRTO 100 ms','Queue 1000 p','Delayed ACK 5 ms','ACK every packet','MinRTO 300 ms']
    selected=[next((s for d,s in records if s['benchmark_case']==name and s['algorithm']=='nonblocking'),None) for name in variants]
    fig,ax=plt.subplots(figsize=(10,4.6),layout='constrained')
    for i,s in enumerate(selected):
        if s: ax.bar(i,s['window_goodput_mbps'],color='#2563eb' if i==0 else '#0f766e')
    ax.set(xticks=range(len(names)),xticklabels=names,ylabel='Payload goodput (Mbit/s)',
           title='Reference sensitivity | one matched bijection seed, no error bars')
    ax.tick_params(axis='x',rotation=18); ax.grid(axis='y',alpha=0.2); ax.set_axisbelow(True)
    fig.savefig(out/'reference-variants.png',dpi=170); plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4.2),layout='constrained')
    for name,label in [('diagnostic-finite','Legacy'),('finite-rto100','MinRTO 100 ms'),
                       ('finite-queue1000','Queue 1000 p'),('finite-ack5','Delayed ACK 5 ms')]:
        directory,s=next((d,s) for d,s in records if s['benchmark_case']==name)
        flows=read(directory/'flows.csv'); times=sorted(float(f['finish']) for f in flows if int(f['completed']))
        xs=[0.2]+times+[s['duration_s']+s['drain_s']]
        ys=[0]+[(i+1)/len(flows) for i in range(len(times))]+[len(times)/len(flows)]
        ax.step(xs,ys,where='post',label=label)
    ax.set(xlabel='Simulation time (s)',ylabel='Fraction of original cohort completed',ylim=(0,1.05),
           title='Finite reference, seed 1 | denominator includes unfinished flows')
    ax.legend(); ax.grid(alpha=0.2); fig.savefig(out/'reference-completion.png',dpi=170); plt.close(fig)
    return aggregate,details


def ablation(root,out,plt):
    records=runs(root); lookup={(s['benchmark_case'],s['seed']):(d,s) for d,s in records}
    paired=[]; aggregate=[]
    for workload in ['stride','bijection']:
        for seed in sorted({s['seed'] for d,s in records}):
            natural,ns=lookup[(workload+'-natural',seed)]; measured,ms=lookup[(workload+'-measured',seed)]
            assert (natural/'workload.csv').read_bytes()==(measured/'workload.csv').read_bytes()
            paired.append(dict(workload=workload,seed=seed,natural_mbps=ns['window_goodput_mbps'],
                measured_mbps=ms['window_goodput_mbps'],natural_over_measured=ns['window_goodput_mbps']/ms['window_goodput_mbps'],
                natural_reroutes=ns['route_changes'],measured_reroutes=ms['route_changes']))
        selected=[r for r in paired if r['workload']==workload]
        mean,lo,hi=ci([r['natural_over_measured'] for r in selected])
        aggregate.append(dict(workload=workload,natural_mbps=statistics.mean(r['natural_mbps'] for r in selected),
            measured_mbps=statistics.mean(r['measured_mbps'] for r in selected),ratio_mean=mean,ci_low=lo,ci_high=hi,n=len(selected)))
    write(out/'ablation-pairs.csv',paired); write(out/'ablation-aggregate.csv',aggregate)
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for i,workload in enumerate(['stride','bijection']):
        subset=[r for r in paired if r['workload']==workload]
        for row in subset:
            axes[0].plot([i-0.18,i+0.18],[row['measured_mbps'],row['natural_mbps']],color='#94a3b8',alpha=.6,lw=1)
        axes[0].scatter([i-0.18]*len(subset),[r['measured_mbps'] for r in subset],label='Measured rate' if i==0 else None,color='#64748b')
        axes[0].scatter([i+0.18]*len(subset),[r['natural_mbps'] for r in subset],label='Natural demand' if i==0 else None,color='#0f766e')
        r=aggregate[i]; axes[1].bar(i,r['ratio_mean'],color='#0f766e',
            yerr=[[max(0,r['ratio_mean']-r['ci_low'])],[max(0,r['ci_high']-r['ratio_mean'])]],capsize=4,width=.5)
    axes[0].set(xticks=[0,1],xticklabels=['Stride','Bijection'],ylabel='Payload goodput (Mbit/s)',title='Paired seeds; lines join the same seed')
    axes[0].legend(); axes[1].set(xticks=[0,1],xticklabels=['Stride','Bijection'],ylabel='Natural / measured goodput',title='Mean paired ratio and exploratory 95% CI')
    axes[1].axhline(1,color='#64748b',ls=':')
    for ax in axes: ax.grid(axis='y',alpha=.2); ax.set_axisbelow(True)
    fig.suptitle('Demand ablation | same GFF/detector; MinRTO 300 ms in both modes')
    fig.savefig(out/'demand-ablation.png',dpi=170); plt.close(fig)
    return aggregate


def demo(root,out,plt):
    records=runs(root); gff=next(d for d,s in records if s['algorithm']=='gff')
    ref=(gff/'workload.csv').read_bytes()
    assert all((d/'workload.csv').read_bytes()==ref for d,s in records)
    fig,axes=plt.subplots(3,1,figsize=(10,9),layout='constrained',sharex=True)
    for directory,s in records:
        rows=read(directory/'goodput.csv')
        axes[0].stairs([float(r['payload_bps'])/1e6 for r in rows],[0]+[float(r['time']) for r in rows],
                       label=s['algorithm'].upper(),color=COLORS[s['algorithm']])
    axes[0].set(ylabel='Total payload (Mbit/s)',title='Adversarial collision fixture | 8 persistent flows, seed 1')
    axes[0].legend(ncol=3)
    ds=read(gff/'controller-flows.csv')
    for field,label,color in [('measured_fraction','Observed source-edge rate / NIC','#64748b'),
                              ('selected_demand','Natural demand','#0f766e')]:
        data=[r for r in ds if int(r['flow_id'])==1]
        axes[1].step([float(r['time']) for r in data],[float(r[field]) for r in data],where='post',label=label,color=color)
    axes[1].set(ylabel='Flow 1 demand / rate',title='GFF flow 1 | detection and scheduler input')
    axes[1].legend()
    links=read(gff/'links.csv'); nodes={int(r['model_node']):r['kind'] for r in read(gff/'nodes.csv')}
    uplinks=sorted({(int(r['link_id']),int(r['from']),int(r['to'])) for r in links
                    if nodes[int(r['from'])]=='aggregation' and nodes[int(r['to'])]=='core' and int(r['from']) in (24,25)})
    for lid,src,dst in uplinks:
        data=[r for r in links if int(r['link_id'])==lid]
        axes[2].step([float(r['time']) for r in data],[float(r['utilization']) for r in data],where='post',label=f'{src}->{dst}')
    routes=[r for r in read(gff/'routes.csv') if r['old_path']]
    for t in sorted({float(r['time']) for r in routes}):
        for ax in axes: ax.axvline(t,color='#d97706',alpha=.3,lw=.8)
    axes[2].set(xlabel='Simulation time (s)',ylabel='Link utilization',title='GFF pod 0 aggregation-to-core links; vertical lines mark route changes')
    axes[2].legend(ncol=4)
    for ax in axes: ax.grid(alpha=.2)
    fig.savefig(out/'demo-timeline.png',dpi=170); plt.close(fig)
    events=[]
    for directory,s in records:
        for r in read(directory/'routes.csv'):
            events.append(dict(algorithm=s['algorithm'],time=float(r['time']),flow_id=int(r['flow_id']),
                               reason=r['reason'],old_path=r['old_path'],new_path=r['new_path']))
    write(out/'demo-routes.csv',events)
    write(out/'demo-summary.csv',[dict(algorithm=s['algorithm'],goodput_mbps=s['window_goodput_mbps'],
           reroutes=s['route_changes'],detected_large=s['detected_large']) for d,s in records])
    first=sorted([r for r in events if r['algorithm']=='gff' and r['old_path']],key=lambda r:(r['time'],r['flow_id']))
    return first


def transport(root,baseline,out,plt):
    records=runs(root); original=runs(baseline); pairs=[]; summary=[]
    for directory,s in records:
        if s['benchmark_case']!='bijection-rto300': continue
        old,os=next((d,b) for d,b in original if b['benchmark_case']=='persistent-bijection'
                    and b['algorithm']==s['algorithm'] and b['seed']==s['seed'])
        assert (directory/'workload.csv').read_bytes()==(old/'workload.csv').read_bytes()
        pairs.append(dict(algorithm=s['algorithm'],seed=s['seed'],rto20_mbps=os['window_goodput_mbps'],
                          rto300_mbps=s['window_goodput_mbps'],ratio=s['window_goodput_mbps']/os['window_goodput_mbps']))
    fig,ax=plt.subplots(figsize=(9,4.4),layout='constrained')
    order=['ecmp','gff','sa','nonblocking']
    for i,algorithm in enumerate(order):
        subset=[r for r in pairs if r['algorithm']==algorithm]
        assert len(subset)==5
        row=dict(algorithm=algorithm,n=len(subset))
        for field in ['rto20_mbps','rto300_mbps','ratio']:
            avg,lo,hi=ci([r[field] for r in subset]); row.update({field:avg,field+'_lo':lo,field+'_hi':hi})
        summary.append(row)
        for offset,field,label,color in [(-.18,'rto20_mbps','MinRTO 20 ms','#94a3b8'),
                                         (.18,'rto300_mbps','MinRTO 300 ms','#0f766e')]:
            ax.bar(i+offset,row[field],width=.32,label=label if i==0 else None,color=color,
                   yerr=[[max(0,row[field]-row[field+'_lo'])],[max(0,row[field+'_hi']-row[field])]],capsize=3)
    ax.set(xticks=range(4),xticklabels=[v.upper() for v in order],ylabel='Payload goodput (Mbit/s)',
           title='Transport sensitivity | same 5 bijection seeds; exploratory 95% CI')
    ax.legend(); ax.grid(axis='y',alpha=.2); ax.set_axisbelow(True)
    fig.savefig(out/'transport-comparison.png',dpi=170); plt.close(fig)
    write(out/'transport-pairs.csv',pairs); write(out/'transport-aggregate.csv',summary)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--diagnosis',type=Path); p.add_argument('--ack-check',type=Path)
    p.add_argument('--ablation',type=Path); p.add_argument('--demo',type=Path,required=True)
    p.add_argument('--transport',type=Path); p.add_argument('--baseline',type=Path)
    p.add_argument('--demo-only',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if bool(a.transport)!=bool(a.baseline): p.error('--transport and --baseline must be provided together')
    a.output.mkdir(parents=True,exist_ok=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10})
    if a.demo_only:
        demo(a.demo,a.output,plt)
        print('Wrote teaching demo figures and CSV:',a.output); return
    if not all([a.diagnosis,a.ack_check,a.ablation]): p.error('Full analysis needs --diagnosis, --ack-check and --ablation')
    summaries,details=diagnose([a.diagnosis,a.ack_check],a.output,plt)
    effects=ablation(a.ablation,a.output,plt); changes=demo(a.demo,a.output,plt)
    transports=transport(a.transport,a.baseline,a.output,plt) if a.transport and a.baseline else []
    lines=['# Follow-up data summary','',
           'Single-seed transport diagnostics are causal probes for this fixture, not population statistics.','',
           '| Run | Goodput Mbit/s | Completion | Retransmissions | CA_LOSS entries |','|---|---:|---:|---:|---:|']
    for r in summaries:
        completion='N/A' if r['completion_fraction'] is None else f'{r["completion_fraction"]:.3f}'
        lines.append(f'| {r["run"]} | {r["goodput_mbps"]:.2f} | {completion} | {r["retransmissions"]} | {r["loss_entries"]} |')
    lines+=['','## Paired demand ablation','','| Workload | Natural | Measured | Mean ratio | 95% exploratory CI |','|---|---:|---:|---:|---|']
    for r in effects:
        lines.append(f'| {r["workload"]} | {r["natural_mbps"]:.2f} | {r["measured_mbps"]:.2f} | {r["ratio_mean"]:.3f} | [{r["ci_low"]:.3f}, {r["ci_high"]:.3f}] |')
    if transports:
        lines+=['','## Transport sensitivity across five matched seeds','','| Algorithm | MinRTO 20 ms | MinRTO 300 ms |','|---|---:|---:|']
        for r in transports: lines.append(f'| {r["algorithm"]} | {r["rto20_mbps"]:.2f} | {r["rto300_mbps"]:.2f} |')
    lines+=['','## First GFF route changes in demo','']
    for r in changes[:8]: lines.append(f'- t={r["time"]:.3f}s, flow {r["flow_id"]}: {r["old_path"]} -> {r["new_path"]}')
    (a.output/'results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Wrote follow-up figures, CSV and summary:',a.output)


if __name__=='__main__': main()
