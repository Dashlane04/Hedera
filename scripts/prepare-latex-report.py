#!/usr/bin/env python3
"""Build self-contained publication figures and data tables from verified CSVs."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'report/hedera-ns3'
ORDER=['ecmp','gff','sa','nonblocking']
LABELS=['ECMP','GFF','SA','Tham chiếu']
COLORS=['#64748b','#0f766e','#d97706','#2563eb']


def read(path):
    with path.open(newline='') as f: return list(csv.DictReader(f))


def table(name,columns,head,rows):
    lines=[r'\begin{tabular}{'+columns+'}',r'\toprule',head+r' \\',r'\midrule']
    lines += [' & '.join(str(v) for v in row)+r' \\' for row in rows]
    lines += [r'\bottomrule',r'\end{tabular}']
    (OUT/'tables'/f'{name}.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def num(x,n=2): return f'{float(x):.{n}f}'


def main():
    for name in ['sections','figures','tables','data']: (OUT/name).mkdir(parents=True,exist_ok=True)
    sources=['results/main16-study/benchmark-aggregate.csv','results/main16-study/paired-effects.csv',
             'results/scale128-study/benchmark-aggregate.csv','results/scheduler-v2.csv',
             'results/followup-analysis/ablation-aggregate.csv','results/followup-analysis/ablation-pairs.csv',
             'results/followup-analysis/transport-aggregate.csv','results/followup-analysis/transport-pairs.csv',
             'results/followup-analysis/diagnostic-summary.csv','results/followup-analysis/diagnostic-flows.csv',
             'results/sensitivity-study/benchmark-aggregate.csv']
    provenance={'date':'2026-10-26','inputs':{},'studies':{}}
    for name in sources:
        p=ROOT/name; target=name.replace('results/','').replace('/','__')
        shutil.copy2(p,OUT/'data'/target)
        provenance['inputs'][name]=hashlib.sha256(p.read_bytes()).hexdigest()
    for name,count in [('main16-study',100),('scale128-study',16),('sensitivity-study',42),('warmup-study',4),
                       ('diagnosis-study',12),('ack-check-study',8),('demand-ablation-study',20),
                       ('defense-demo',3),('transport-check-study',25)]:
        folder=ROOT/'results'/name; manifest=json.loads((folder/'manifest.json').read_text())
        assert len(list(folder.glob('*/summary.json')))==count
        shutil.copy2(folder/'manifest.json',OUT/'data'/f'{name}__manifest.json')
        provenance['studies'][name]={'runs':count,'ns3_revision':manifest['ns3_revision'],
                                    'source_sha256':manifest['source_sha256']}
    assert sum(x['runs'] for x in provenance['studies'].values())==230
    (OUT/'data/provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    mainrows=read(ROOT/sources[0]); get=lambda case,alg:next(r for r in mainrows if r['case']==case and r['algorithm']==alg)
    cases=['persistent-stride','persistent-bijection','persistent-locality']
    names=['Stride','Bijection','Locality']
    table('persistent','lrrrr','Workload & ECMP & GFF & SA & Tham chiếu',
          [[label]+[num(get(case,alg)['goodput_mbps_mean']) for alg in ORDER] for label,case in zip(names,cases)])
    finite=[]
    for case,label in [('finite-bijection','Bijection hữu hạn'),('poisson-cohort','Poisson cohort')]:
        for alg,method in zip(ORDER,LABELS):
            r=get(case,alg); finite.append([label,method,num(100*float(r['completion_fraction_mean'])),num(r['conditional_mean_fct_s_mean'],4)])
    table('finite','llrr',r'Workload & Phương pháp & Hoàn thành (\%) & FCT (s)',finite)
    pairs=read(ROOT/sources[1]); rows=[]
    for case,label in zip(cases,names):
        for alg in ['gff','sa']:
            r=next(r for r in pairs if r['case']==case and r['algorithm']==alg)
            rows.append([label,alg.upper(),num(r['goodput_ratio_ecmp_mean'],3),
                         '['+num(r['goodput_ratio_ecmp_ci_low'],3)+'; '+num(r['goodput_ratio_ecmp_ci_high'],3)+']'])
    table('paired','llrc',r'Workload & Phương pháp & Tỷ lệ với ECMP & CI 95\%',rows)
    scale=read(ROOT/sources[2])
    table('scale','rrrrr','Host & ECMP & GFF & SA & Tham chiếu',
          [[n]+[num(next(r for r in scale if r['hosts']==str(n) and r['algorithm']==alg)['goodput_mbps_mean']) for alg in ORDER] for n in [16,128]])
    sched=read(ROOT/sources[3])
    table('runtime','rrr','Host & GFF (ms) & SA (ms)',[[n]+[num(statistics.median(float(r['placement_us']) for r in sched if int(r['hosts'])==n and int(r['flows'])==1024 and r['algorithm']==alg)/1000,3) for alg in ['gff','sa']] for n in [16,54,128]])
    ablation=read(ROOT/sources[4])
    table('ablation','lrrrc',r'Workload & Natural & Measured & Tỷ lệ & CI 95\%',
          [[r['workload'].capitalize(),num(r['natural_mbps']),num(r['measured_mbps']),num(r['ratio_mean'],3),
            '['+num(r['ci_low'],3)+'; '+num(r['ci_high'],3)+']'] for r in ablation])
    transport=read(ROOT/sources[6])
    table('transport','lrr','Phương pháp & MinRTO 20 ms & MinRTO 300 ms',
          [[LABELS[ORDER.index(r['algorithm'])],num(r['rto20_mbps']),num(r['rto300_mbps'])] for r in transport])
    diag=read(ROOT/sources[8]); dlookup={r['run']:r for r in diag}
    variants=[('Cấu hình cũ','diagnostic-persistent','diagnostic-finite'),
              ('Bỏ virtual delay','persistent-no-delay','finite-no-delay'),
              ('MinRTO 100 ms','persistent-rto100','finite-rto100'),
              ('Queue 1.000 packet','persistent-queue1000','finite-queue1000'),
              ('Delayed ACK 5 ms','persistent-ack5','finite-ack5'),
              ('ACK mỗi packet','persistent-ack-every1','finite-ack-every1'),
              ('MinRTO 300 ms','persistent-rto300','finite-rto300')]
    table('diagnostics','lrr','Biến thể reference & Goodput & Hoàn thành (flow)',
          [[label,num(dlookup[p+'-s1-nonblocking']['goodput_mbps']),str(round(float(dlookup[f+'-s1-nonblocking']['completion_fraction'])*16))+'/16'] for label,p,f in variants])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,
                         'axes.spines.right':False,'pdf.fonttype':42,'savefig.bbox':'tight'})
    def save(fig,name):
        fig.savefig(OUT/'figures'/f'{name}.pdf'); fig.savefig(OUT/'figures'/f'{name}.png',dpi=190); plt.close(fig)
    fig,ax=plt.subplots(figsize=(6.6,3),layout='constrained')
    for j,alg in enumerate(ORDER):
        means=[float(get(c,alg)['goodput_mbps_mean']) for c in cases]
        lows=[float(get(c,alg)['goodput_mbps_ci_low']) for c in cases]
        highs=[float(get(c,alg)['goodput_mbps_ci_high']) for c in cases]
        ax.bar([i+(j-1.5)*.19 for i in range(3)],means,width=.18,color=COLORS[j],label=LABELS[j],
               yerr=[[m-l for m,l in zip(means,lows)],[h-m for m,h in zip(means,highs)]],capsize=2)
    ax.set(xticks=range(3),xticklabels=names,ylabel='Goodput ứng dụng (Mbit/s)'); ax.legend(ncol=4,fontsize=8)
    ax.grid(axis='y',alpha=.2); ax.set_axisbelow(True); save(fig,'main-goodput')
    fig,ax=plt.subplots(figsize=(6.6,3),layout='constrained')
    for j,mode in enumerate(['measured','natural']):
        values=[float(r[mode+'_mbps']) for r in ablation]
        ax.bar([i+(j-.5)*.32 for i in range(2)],values,width=.3,color=['#64748b','#0f766e'][j],
               label=['Tốc độ đo trực tiếp','Natural demand'][j])
    ax.set(xticks=[0,1],xticklabels=['Stride','Bijection'],ylabel='Goodput ứng dụng (Mbit/s)'); ax.legend(fontsize=8)
    ax.grid(axis='y',alpha=.2); ax.set_axisbelow(True); save(fig,'ablation')
    fig,ax=plt.subplots(figsize=(6.6,3),layout='constrained')
    for j,field in enumerate(['rto20_mbps','rto300_mbps']):
        vals=[float(r[field]) for r in transport]
        err=[[float(r[field])-float(r[field+'_lo']) for r in transport],
             [float(r[field+'_hi'])-float(r[field]) for r in transport]]
        ax.bar([i+(j-.5)*.32 for i in range(4)],vals,width=.3,color=['#94a3b8','#0f766e'][j],yerr=err,
               label=['MinRTO 20 ms','MinRTO 300 ms'][j],capsize=2)
    ax.set(xticks=range(4),xticklabels=LABELS,ylabel='Goodput ứng dụng (Mbit/s)'); ax.legend(fontsize=8)
    ax.grid(axis='y',alpha=.2); ax.set_axisbelow(True); save(fig,'transport')
    fig,axes=plt.subplots(1,2,figsize=(6.6,2.6),layout='constrained')
    for ax,alg in zip(axes,['gff','sa']):
        for n in [16,54,128]:
            sizes=[16,64,256,1024]; values=[statistics.median(float(r['placement_us']) for r in sched if int(r['hosts'])==n and int(r['flows'])==f and r['algorithm']==alg)/1000 for f in sizes]
            ax.plot(sizes,values,marker='o',ms=3,label=f'{n} host')
        ax.set_xscale('log',base=2); ax.set_yscale('log'); ax.set(title=alg.upper(),xlabel='Số flow',ylabel='Placement (ms)')
        ax.set_xticks([16,64,256,1024],[16,64,256,1024]); ax.grid(alpha=.2); ax.legend(fontsize=7)
    save(fig,'runtime')
    # A faithful k=4 topology, using the simulator's actual model-node numbering.
    fig,ax=plt.subplots(figsize=(6.8,3),layout='constrained')
    positions={}
    for h in range(16): positions[h]=(h,0)
    for e in range(8): positions[16+e]=(e*2+.5,1)
    for p in range(4):
        for a in range(2): positions[24+p*2+a]=(p*4+.7+a*1.6,2)
    for c in range(4): positions[32+c]=(2+c*3.5,3.2)
    edges=[]
    for h in range(16): edges.append((h,16+h//2))
    for p in range(4):
        for e in range(2):
            for a in range(2): edges.append((16+p*2+e,24+p*2+a))
        for a in range(2):
            for c in range(2): edges.append((24+p*2+a,32+a*2+c))
    for u,v in edges: ax.plot([positions[u][0],positions[v][0]],[positions[u][1],positions[v][1]],color='#94a3b8',lw=.6,zorder=1)
    for node,(x,y) in positions.items():
        ax.scatter([x],[y],marker='s' if node>=16 else 'o',s=110 if node>=16 else 78,
                   color='#17354a' if node>=16 else '#0f766e',zorder=2)
        ax.text(x,y,str(node),ha='center',va='center',color='white',fontsize=5.3,zorder=3)
    for p in range(4): ax.text(p*4+1.5,-.42,f'Pod {p}',ha='center',fontsize=8)
    for y,label in [(3.2,'Core'),(2,'Aggregation'),(1,'Edge'),(0,'Host')]: ax.text(-1.1,y,label,ha='right',va='center',fontsize=8)
    ax.set(xlim=(-3,16),ylim=(-.7,3.65)); ax.axis('off'); save(fig,'topology')
    # Re-render selected TCP and demonstration traces as vector figures.
    ref=ROOT/'results/diagnosis-study/diagnostic-persistent-s1-nonblocking'
    samples=read(ref/'tcp-samples.csv'); fig,axes=plt.subplots(2,1,figsize=(6.6,3.5),sharex=True,layout='constrained')
    for fid in [10,14]:
        s=[r for r in samples if int(r['flow_id'])==fid]
        axes[0].step([float(r['time']) for r in s],[int(r['cwnd_bytes'])/1448 for r in s],where='post',label=f'Flow {fid}')
        axes[1].step([float(r['time']) for r in s],[float(r['rto_s'])*1000 for r in s],where='post')
    axes[0].set(ylabel='cwnd (MSS)'); axes[0].legend(fontsize=8); axes[0].axhline(1,color='black',ls=':',lw=.7)
    axes[1].set(xlabel='Thời gian mô phỏng (s)',ylabel='RTO (ms)')
    for ax in axes: ax.grid(alpha=.2)
    save(fig,'tcp-reference')
    fig,axes=plt.subplots(2,1,figsize=(6.6,3.7),sharex=True,layout='constrained')
    for alg in ['ecmp','gff','sa']:
        folder=ROOT/'results/defense-demo'/f'collision-demo-s1-{alg}'; rows=read(folder/'goodput.csv')
        axes[0].stairs([float(r['payload_bps'])/1e6 for r in rows],[0]+[float(r['time']) for r in rows],
                       label=alg.upper(),color=COLORS[ORDER.index(alg)])
    ds=read(ROOT/'results/defense-demo/collision-demo-s1-gff/controller-flows.csv'); ds=[r for r in ds if int(r['flow_id'])==1]
    for field,label,color in [('measured_fraction','Tốc độ source edge / NIC','#64748b'),('selected_demand','Natural demand','#0f766e')]:
        axes[1].step([float(r['time']) for r in ds],[float(r[field]) for r in ds],where='post',label=label,color=color)
    axes[0].set(ylabel='Goodput (Mbit/s)'); axes[0].legend(ncol=3,fontsize=8)
    axes[1].set(xlabel='Thời gian mô phỏng (s)',ylabel='Flow 1: tỷ phần NIC'); axes[1].legend(fontsize=8)
    for ax in axes: ax.axvline(.3,color='#d97706',ls=':',lw=1); ax.grid(alpha=.2)
    save(fig,'demo')
    print('Prepared 230-run provenance, 8 tables and 7 vector figures:',OUT)


if __name__=='__main__': main()
