#!/usr/bin/env python3
"""Validate completed studies and create the paper's vector figures and TeX numbers."""
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import shutil
import statistics as stat

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np


ALGS = ("ecmp", "gff", "sa", "nonblocking")
LABEL = dict(ecmp="ECMP", gff="GFF", sa="SA", nonblocking="Nonblocking")
COLORS = dict(ecmp="#64748b", gff="#138475", sa="#bd7325", nonblocking="#466fbb")
STYLES = dict(ecmp="--", gff="-", sa="-.", nonblocking=":")
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.labelcolor": "#243849",
                     "xtick.color": "#243849", "ytick.color": "#243849",
                     "axes.grid": True, "grid.alpha": .2, "pdf.fonttype": 42})


def read(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def packet_runs(directory):
    if not (directory/"manifest.json").is_file():
        return []
    manifest = json.loads((directory/"manifest.json").read_text())
    result = []
    for case in manifest["plan"]:
        for seed in case["seeds"]:
            paired = []
            for alg in case["algorithms"]:
                path = directory/f'{case["name"]}-s{seed}-{alg}'
                if not (path/"summary.json").is_file():
                    continue
                s = json.loads((path/"summary.json").read_text())
                assert s["seed"]==seed and s["algorithm"]==alg
                paired.append((path/"workload.csv").read_bytes())
                result.append((case["name"], seed, alg, path, s))
            assert len(set(paired))<=1, (directory, case["name"], seed)
    return result


def grouped_bars(ax, cases, rows, metric, xlabel, ylabel):
    x = np.arange(len(cases))
    for i, alg in enumerate(ALGS):
        vals, error_x, error_y, ranges = [], [], [], []
        offsets = x+(i-1.5)*.19
        for case in cases:
            v = [r[metric] for r in rows if r["case"]==case and r["algorithm"]==alg]
            average = stat.mean(v) if v else math.nan
            if len(v)>1 and min(v)!=max(v):
                error_x.append(offsets[len(vals)])
                error_y.append(average)
                ranges.append((average-min(v), max(v)-average))
            vals.append(average)
        ax.bar(offsets, vals, width=.18, color=COLORS[alg], label=LABEL[alg])
        if ranges:
            ax.errorbar(error_x, error_y, yerr=np.array(ranges).T, fmt="none", ecolor="#243849",
                        elinewidth=.8, capsize=2)
    ax.set_xticks(x, [xlabel.get(k, k) for k in cases])
    ax.set_ylabel(ylabel)
    ax.set_axisbelow(True)


def architecture(save):
    fig, ax = plt.subplots(figsize=(7.2, 2.1))
    ax.set(xlim=(0, 10), ylim=(0, 3))
    ax.axis("off")
    layers = [
        (0.08, 1.62, 2.8, 1.05, "#edf3fb", "#466fbb", "Data plane", "Host → edge → agg → core"),
        (3.54, 1.62, 2.85, 1.05, "#eaf6f4", "#138475", "Giám sát tại edge", "Đếm byte, phát hiện luồng lớn"),
        (7.02, 1.62, 2.9, 1.05, "#fbf1e5", "#bd7325", "Control plane", "Ước lượng demand → GFF / SA"),
        (3.54, .18, 2.85, .88, "#f0f3f6", "#64748b", "Phân phối rule", "Kích hoạt phiên bản đường"),
    ]
    for x, y, w, h, fill, accent, title, sub in layers:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=.03,rounding_size=.09",
                                   facecolor=fill, edgecolor=accent, linewidth=.85))
        ax.text(x+w/2, y+h*.65, title, ha="center", va="center", weight="bold", color=accent)
        ax.text(x+w/2, y+h*.29, sub, ha="center", va="center", fontsize=8)
    for start, stop in [((2.91, 2.14), (3.49, 2.14)), ((6.42, 2.14), (6.97, 2.14)),
                        ((8.47, 1.58), (6.44, .62)), ((3.48, .62), (1.49, 1.56))]:
        ax.annotate("", xy=stop, xytext=start, arrowprops=dict(arrowstyle="-|>", color="#516778"))
    save(fig, "architecture")


def packet_analysis(base, data, save):
    runs = packet_runs(base/"compact16")
    assert len(runs)==32, len(runs)
    exact = packet_runs(base/"gigabit16")
    extended = packet_runs(base/"scaled16")
    rows = []
    for profile, rate, source in [("compact",20,runs), ("gigabit",1000,exact), ("extended",20,extended)]:
        for case, seed, alg, _, s in source:
            rows.append(dict(profile=profile, rate_mbps=rate, case=case, seed=seed, algorithm=alg,
                             window_start=s["measurement_start_s"],window_end=s["measurement_end_s"],
                             total=float(s["window_goodput_mbps"]), cut=float(s["cut_payload_goodput_mbps"])))
    write(data/"packet16.csv", rows)
    labels = {f"paper-stride-{i}":f"Stride {i}" for i in (1,2,4,8)}
    labels.update({"paper-bijection":"Song ánh","paper-hotspot":"Hotspot"})
    cases = list(labels)
    for profile, filename in [("compact", "packet16"), ("extended", "packet16-long")]:
        selected = [r for r in rows if r["profile"]==profile]
        if not selected:
            continue
        fig, ax = plt.subplots(2, 1, figsize=(7.2, 4.25), sharex=True)
        grouped_bars(ax[0], cases, selected, "total", labels, "Goodput tổng (Mbit/s)")
        grouped_bars(ax[1], cases, selected, "cut", labels, "Qua lát cắt (Mbit/s)")
        ax[0].legend(ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(.5,1.23))
        save(fig, filename)
    if exact:
        traces = []
        fig, ax = plt.subplots(figsize=(3.45,2.4))
        ax.axvspan(10, 50, color="#cbd5e1", alpha=.3, zorder=-2)
        for _, seed, alg, path, _ in exact:
            trace = read(path/"goodput.csv")
            traces.extend(dict(algorithm=alg, seed=seed, **r) for r in trace)
            t = [float(r["time"]) for r in trace if float(r["time"])<=60]
            y = [float(r["payload_bps"])/1e9 for r in trace[:len(t)]]
            ax.stairs(y, [0]+t, color=COLORS[alg], linestyle=STYLES[alg], label=LABEL[alg], baseline=None)
        ax.set(xlabel="Thời gian (s)", ylabel="Goodput (Gbit/s)", xlim=(0,60))
        ax.legend(ncol=2,frameon=False,fontsize=7,loc="upper center",bbox_to_anchor=(.5,1.28))
        write(data/"gigabit16-trace.csv", traces)
        save(fig,"gigabit16")
    return rows


def tcp_analysis(base, data, save):
    runs = [r for r in packet_runs(base/"gigabit-tcp") if r[0]=="gigabit-reference"]
    runs.extend(packet_runs(base/"gigabit-tcp-short"))
    if not runs:
        return [], []
    initial = packet_runs(base/"gigabit16")
    assert len(initial)==4
    reference = next(r for r in initial if r[2]=="nonblocking")
    labels = {"gigabit-default": "Gốc", "gigabit-ack5": "ACK 5 ms",
              "gigabit-ack1": "ACK mỗi gói", "gigabit-rto300": "RTO 300 ms"}
    colors = dict(zip(labels, [COLORS["ecmp"],COLORS["gff"],COLORS["sa"],COLORS["nonblocking"]]))
    results, series = [], []
    fig, (curves, bars) = plt.subplots(1, 2, figsize=(7.2, 2.65))
    curves.axvspan(1.2, 2.4, color="#cbd5e1", alpha=.3, zorder=-2)
    original_workload = read(reference[3]/"workload.csv")
    endpoint_fields = ["src", "dst", "start", "bytes", "port", "cohort"]
    original_keys = [tuple(r[k] for k in endpoint_fields) for r in original_workload]
    for case, seed, alg, path, s in runs:
        start, end = s["measurement_start_s"], s["measurement_end_s"]
        workload = read(path/"workload.csv")
        assert original_keys==[tuple(r[k] for k in endpoint_fields) for r in workload]
        assert all(float(r["stop"])>=end for r in workload)
        if case=="gigabit-reference":
            assert s["window_goodput_mbps"]==reference[4]["window_goodput_mbps"]
        tcp = [r for r in read(path/"tcp-samples.csv") if start<float(r["time"])<=end]
        assert len(tcp)==s["flows"]*round((end-start)/s["interval_s"])
        loss = sum(r["event"]=="congestion" and r["new_value"]=="4" and start<float(r["time"])<=end
                   for r in read(path/"tcp-events.csv"))
        drops = sum(start<float(r["time"])<=end for r in read(path/"queue-drops.csv"))
        results.append(dict(case=case, seed=seed, algorithm=alg, goodput_gbps=s["window_goodput_mbps"]/1000,
                            window_start=start, window_end=end, tcp_sample_count=len(tcp),
                            median_cwnd_bytes=stat.median(int(r["cwnd_bytes"]) for r in tcp),
                            cwnd_at_one_mss_fraction=stat.mean(int(r["cwnd_bytes"])==1448 for r in tcp),
                            loss_state_transitions=loss, queue_disc_drops=drops))
        if case not in labels:
            continue
        trace = [r for r in read(path/"goodput.csv") if float(r["time"])<=s["duration_s"]]
        time = [float(r["time"]) for r in trace]
        values = [float(r["payload_bps"])/1e9 for r in trace]
        series.extend(dict(case=case, time_s=t, goodput_gbps=y) for t,y in zip(time,values))
        curves.stairs(values, [0]+time, baseline=None, color=colors[case], label=labels[case], linewidth=1.1)
    write(data/"gigabit-tcp.csv", results)
    if series:
        for i, case in enumerate(labels):
            row = next((r for r in results if r["case"]==case), None)
            if row:
                bars.bar(i, 100*row["cwnd_at_one_mss_fraction"], color=colors[case])
        curves.set(xlabel="Thời gian (s)", ylabel="Goodput (Gbit/s)", xlim=(0,2.5))
        curves.legend(frameon=False, fontsize=7, loc="upper center", bbox_to_anchor=(.5,1.22), ncol=2)
        bars.set_xticks(range(len(labels)), labels.values(), rotation=12, ha="right")
        bars.set(ylabel="Cwnd bằng một MSS (%)", ylim=(0,105))
        write(data/"gigabit-tcp-trace.csv", series)
        save(fig, "gigabit-tcp")
    else:
        plt.close(fig)
    return runs, results


def gigabit_bijection_analysis(base, data, save):
    directory = base/"gigabit-bijection"
    if not (directory/"manifest.json").is_file():
        return {}
    runs = packet_runs(directory)
    expected = {(seed, algorithm) for seed in (1, 2, 3) for algorithm in ALGS}
    if len(runs) != len(expected) or {(seed, algorithm) for _, seed, algorithm, _, _ in runs} != expected:
        raise ValueError("Gigabit bijection requires four completed methods for each of the three seeds.")

    goodput = {}
    for _, seed, algorithm, path, summary in runs:
        workload = read(path/"workload.csv")
        sources = {int(row["src"]) for row in workload}
        destinations = {int(row["dst"]) for row in workload}
        if (len(workload)!=16 or sources!=set(range(16)) or destinations!=sources
                or any(row["src"]==row["dst"] for row in workload)):
            raise ValueError(f"Expected a derangement of 16 endpoints: {path}")
        goodput[seed, algorithm] = float(summary["window_goodput_mbps"])/1000

    rows = []
    stats = {}
    for algorithm in ALGS:
        values = [goodput[seed, algorithm] for seed in (1, 2, 3)]
        changes = [100*(value/goodput[seed, "ecmp"]-1) for seed, value in enumerate(values, 1)]
        stats[algorithm] = dict(mean=stat.mean(values), low=min(values), high=max(values),
                                mean_gain=stat.mean(changes), low_gain=min(changes), high_gain=max(changes),
                                wins=sum(change>0 for change in changes))
        rows.extend(dict(seed=seed, algorithm=algorithm, goodput_gbps=value, relative_to_ecmp_pct=change)
                    for seed, (value, change) in enumerate(zip(values, changes), 1))
    write(data/"gigabit-bijection.csv", rows)
    write(data/"gigabit-bijection-summary.csv",
          [dict(algorithm=algorithm, **metrics) for algorithm, metrics in stats.items()])

    fig, ax = plt.subplots(figsize=(3.5, 2.55))
    for seed, color, marker in [(1,"#36678e","o"), (2,"#138475","s"), (3,"#ad641e","^")]:
        ax.plot(range(len(ALGS)), [goodput[seed, algorithm] for algorithm in ALGS],
                color=color, marker=marker, markersize=4, linewidth=1.1, label=f"Seed {seed}")
    ax.set_xticks(range(len(ALGS)), [LABEL[algorithm] for algorithm in ALGS])
    ax.set_ylabel("Goodput tổng (Gbit/s)")
    ax.legend(frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(.5,1.0), fontsize=8)
    save(fig, "gigabit-bijection")
    return stats


def flow_analysis(base, data, save):
    source = base/"flow"
    rows = read(source/"summary.csv")
    assert len(rows)==56
    if not any(r["pattern"]=="stag50pod0" for r in rows):
        corrected = read(base/"flow-figure10-stag50"/"summary.csv")
        assert len(corrected)==4 and all(r["pattern"]=="stag50pod0" for r in corrected)
        rows.extend(corrected)
    for r in rows:
        for k in ("k","seed","steps","warm"): r[k]=int(r[k])
        for k in ("total_gbps","cut_gbps"): r[k]=float(r[k])
        r["case"]=r["pattern"]
    write(data/"flow-summary.csv", rows)
    fig, ax = plt.subplots(2,1,figsize=(7.2,4.2),sharex=True)
    time_rows = []
    for alg in ALGS:
        matched=[r for r in rows if r["k"]==16 and r["pattern"]=="randbij" and r["algorithm"]==alg]
        traces=[read(source/(r["name"]+".csv")) for r in matched]
        time=np.array([float(x["time_s"]) for x in traces[0]])
        for panel, metric in zip(ax,("total_gbps","cut_gbps")):
            values=np.mean([[float(x[metric]) for x in trace] for trace in traces],axis=0)
            per_second = values.reshape(-1,50).mean(axis=1)
            time_rows.extend(dict(algorithm=alg, time_s=t, metric=metric, goodput_gbps=v)
                             for t,v in zip(time[49::50],per_second))
            panel.plot(time[49::50],per_second,color=COLORS[alg],
                       linestyle=STYLES[alg],label=LABEL[alg],linewidth=1.25)
    for panel in ax:
        panel.axvspan(10,50,color="#cbd5e1",alpha=.22,zorder=-2)
    ax[0].set_ylabel("Tổng (Gbit/s)")
    ax[1].set(ylabel="Qua lát cắt (Gbit/s)",xlabel="Thời gian (s)")
    ax[0].legend(ncol=4,frameon=False,loc="upper center",bbox_to_anchor=(.5,1.2))
    write(data/"flow-timeseries-1024.csv", time_rows)
    save(fig,"flow1024")
    cases=["stag100","stag50pod0","stag20","stride1","stride16","stride256","randbij","rand"]
    large=[r for r in rows if r["k"]==32]
    fig, ax = plt.subplots(2,1,figsize=(7.2,4.6),sharex=True)
    labels={"stag100":"Stag 1/0","stag50pod0":"Stag .5/0","stag20":"Stag .2/.3",
            "stride1":"Stride 1","stride16":"Stride 16","stride256":"Stride 256","randbij":"Song ánh","rand":"Random"}
    grouped_bars(ax[0],cases,large,"total_gbps",labels,"Tổng (Gbit/s)")
    grouped_bars(ax[1],cases,large,"cut_gbps",labels,"Qua lát cắt (Gbit/s)")
    ax[0].legend(ncol=4,frameon=False,loc="upper center",bbox_to_anchor=(.5,1.23))
    save(fig,"flow8192")
    sweep=[r for r in rows if r["k"]==16 and r["pattern"]=="rand"]
    fig, ax=plt.subplots(figsize=(3.45,2.25))
    for warm,color in [(0,"#64748b"),(1,"#138475")]:
        steps=sorted({r["steps"] for r in sweep})
        vals=[stat.mean(r["total_gbps"] for r in sweep if r["steps"]==s and r["warm"]==warm) for s in steps]
        ax.plot(steps, vals, "o-", color=color,label="Giữ nghiệm trước" if warm else "Khởi tạo lại")
    ax.set(xscale="log",xlabel="Số vòng SA",ylabel="Goodput tổng (Gbit/s)")
    ax.legend(frameon=False,fontsize=8)
    save(fig,"budget")
    return rows


def restriction_fixture(save):
    fig, ax = plt.subplots(figsize=(3.45,2.12))
    ax.set(xlim=(0,4), ylim=(.1,2.82))
    ax.axis("off")
    points = {8: (.85,1.7), 9: (3.15,1.7), 10: (2,.45)}
    for src, dst in [(8,9),(8,10),(9,10)]:
        x, y = zip(points[src], points[dst])
        ax.plot(x, y, color="#64748b", linewidth=1.2)
    for dest, (x,y) in points.items():
        ax.text(x,y,f"Host {dest}",ha="center",va="center",weight="bold",fontsize=8,
                bbox=dict(boxstyle="round,pad=.29",facecolor="#edf3fb",edgecolor="#466fbb"))
    ax.text(2,1.95,"Cạnh xuống đích · 1,6",ha="center",fontsize=8,color="#17354a")
    ax.text(.02,.94,"Cạnh lên\nnguồn · 1,1",ha="left",va="center",fontsize=7.5,color="#17354a")
    ax.text(3.98,.94,"Cạnh lên\nnguồn · 1,1",ha="right",va="center",fontsize=7.5,color="#17354a")
    ax.text(2,2.54,"Hai aggregation · ba cặp xung đột",ha="center",weight="bold",fontsize=9,color="#17354a")
    save(fig,"restriction-fixture")


def core_analysis(base,data,save):
    estimate=read(base/"core-verified/scheduler-estimate.csv")
    runtime=read(base/"core-verified/scheduler-runtime.csv")
    quality=read(base/"core-verified/scheduler-quality.csv")
    assert (len(estimate),len(runtime),len(quality))==(40,120,720)
    for name,rs in [("estimator",estimate),("runtime",runtime),("oracle",quality)]:write(data/(name+".csv"),rs)
    # Published values, Table 4 and Table 5. These use the authors' machine and implementation.
    paper4={1024:{1024:1.45,5000:4.14},8192:{8192:2.71,25000:9.23,50000:26.31},
            27648:{27648:6.91,100000:51.30,250000:199.43}}
    paper5={3215:[2.997,12.209,23.447],6250:[5.042,20.848,40.255],
            25000:[6.898,19.091,32.912],50000:[11.573,32.079,55.741]}
    fig,ax=plt.subplots(1,2,figsize=(7.2,2.9))
    palette=["#466fbb","#138475","#bd7325","#7a5397"]
    for (hosts,points),color in zip(paper4.items(),palette):
        x=list(points)
        local=[stat.median(float(r["runtime_ms"]) for r in estimate if int(r["hosts"])==hosts and int(r["flows"])==n) for n in x]
        ax[0].plot(x,local,"o-",color=color,label=f"{hosts:,} host")
        ax[0].plot(x,list(points.values()),"x--",color=color,alpha=.65)
    for (n,points),color in zip(paper5.items(),palette):
        steps=[1000,5000,10000]
        local=[stat.median(float(r["runtime_ms"]) for r in runtime if int(r["flows"])==n and int(r["iterations"])==s
                           and r["variant"]=="destination") for s in steps]
        ax[1].plot(steps,local,"o-",color=color,label=f"{n:,} flow")
        ax[1].plot(steps,points,"x--",color=color,alpha=.65)
    ax[0].set(xscale="log",yscale="log",xlabel="Số flow",ylabel="Ước lượng demand (ms)")
    ax[1].set(xlabel="Số vòng SA",ylabel="SA theo đích (ms)",yscale="log")
    ax[1].set_xticks([1000,5000,10000], ["1.000","5.000","10.000"])
    for panel in ax:panel.legend(frameon=False,fontsize=7)
    save(fig,"runtime")
    fig,ax=plt.subplots(figsize=(3.45,2.25))
    for (n,_),color in zip(paper5.items(),palette):
        steps=[1000,5000,10000]
        ratios=[]
        for step in steps:
            matches=[r for r in runtime if int(r["flows"])==n and int(r["iterations"])==step]
            medians={v:stat.median(float(r["runtime_ms"]) for r in matches if r["variant"]==v)
                     for v in ("flow","destination")}
            ratios.append(medians["flow"]/medians["destination"])
        ax.plot(steps,ratios,"o-",color=color,label=f"{n:,} flow")
    ax.axhline(1,color="#64748b",linestyle="--",linewidth=.7)
    ax.set(xlabel="Số vòng SA",ylabel="Tỷ lệ runtime")
    ax.set_xticks([1000,5000,10000], ["1.000","5.000","10.000"])
    ax.legend(frameon=False,fontsize=7,ncol=2)
    save(fig,"variants")
    bounds=defaultdict(dict)
    for r in quality:
        bounds[r["snapshot"]][r["variant"]]=float(r["oracle_energy"])
    losses=[v["destination"]-v["flow"] for v in bounds.values()]
    assert min(losses)>=-1e-8
    fig,ax=plt.subplots(1,2,figsize=(7.2,2.55))
    for variant,color in [("destination","#138475"),("flow","#466fbb")]:
        steps=[10,100,1000]
        vals=[]
        fractions=[]
        for s in steps:
            error=[max(0,float(r["sa_energy"])-float(r["oracle_energy"])) for r in quality
                   if int(r["steps"])==s and r["variant"]==variant]
            vals.append(stat.mean(error))
            fractions.append(stat.mean(e<1e-8 for e in error)*100)
        label="Theo đích" if variant=="destination" else "Theo flow"
        ax[0].plot(steps,vals,"o-",color=color,label=label)
        ax[1].plot(steps,fractions,"o-",color=color,label=label)
    ax[0].set(ylabel="Gap trung bình so với oracle")
    ax[1].set(ylabel="Chạm nghiệm exact (%)",ylim=(0,105))
    for panel in ax:panel.set(xscale="log",xlabel="Số vòng SA")
    ax[0].legend(frameon=False,fontsize=8)
    save(fig,"oracle")
    return sum(x>1e-8 for x in losses),max(losses)


def mechanism_analysis(base,data,save):
    runs=packet_runs(base/"mechanisms")
    assert len(runs)==26
    latency=[]
    control=[]
    for case,seed,alg,path,s in runs:
        if case not in {"gff-on-detection","periodic"}:continue
        flows={r["flow_id"]:float(r["first_detected_s"]) for r in read(path/"flows.csv")
               if r["cohort"]=="burst" and float(r["first_detected_s"])>=0}
        installs=read(path/"control-events.csv")
        phases=read(path/"switch-control.csv")
        routes=read(path/"routes.csv")
        for f,detection in flows.items():
            eligible=[r for r in installs if r["event"]=="flow_install" and r["flow_id"]==f and float(r["time"])>=detection]
            assert eligible, (path,f)
            event=eligible[0]
            install=float(event["time"])
            changed=any(r["flow_id"]==f and r["old_path"] and abs(float(r["time"])-install)<1e-5
                        for r in routes)
            latency.append(dict(case=case,seed=seed,algorithm=alg,flow=f,detection=detection,
                                install=install,latency_ms=1000*(install-detection),path_changed=bool(changed)))
        for plan in {r["plan_id"] for r in phases}:
            pr=[r for r in phases if r["plan_id"]==plan]
            assert all(int(r["bytes"])==int(r["entries"])*72 for r in pr)
            start=next(float(r["time"]) for r in installs if r["event"]=="start" and r["plan_id"]==plan)
            compute=next(float(r["time"]) for r in pr if r["phase"]=="compute_done")
            ready=next(float(r["time"]) for r in pr if r["phase"]=="ready_to_activate")
            assert start<=compute<=ready
            control.append(dict(case=case,seed=seed,algorithm=alg,plan=plan,
                                stats_ms=1000*(compute-start)-100,compute_ms=100,
                                install_ms=1000*(ready-compute),
                                stats_bytes=sum(int(r["bytes"]) for r in pr if r["phase"]=="stats_arrive"),
                                rule_bytes=sum(int(r["bytes"]) for r in pr if r["phase"]=="rule_staged")))
    write(data/"detection-install.csv",latency)
    write(data/"switch-service.csv",control)
    fig,ax=plt.subplots(1,2,figsize=(7.2,2.7))
    variants=[("gff-on-detection","gff","GFF theo sự kiện"),("periodic","gff","GFF định kỳ"),("periodic","sa","SA định kỳ")]
    for i,(case,alg,label) in enumerate(variants):
        vals=[r["latency_ms"] for r in latency if r["case"]==case and r["algorithm"]==alg]
        ax[0].scatter(np.linspace(i-.07,i+.07,len(vals)),vals,s=14,color=COLORS[alg],alpha=.75)
    ax[0].set_xticks(range(3),[v[2] for v in variants],rotation=11,ha="right")
    ax[0].set_ylabel("Phát hiện → cài đường (ms)")
    paper={1024:[100.2,100.9,101.7],8192:[101.4,106.8,113.5],27648:[104.6,122.8,145.5]}
    projection=[]
    for (hosts,observed),color in zip(paper.items(),["#466fbb","#138475","#bd7325"]):
        k=round((4*hosts)**(1/3))
        edge_count=k*k//2
        local=[]
        for per_host,benchmark in zip([1,5,10],observed):
            per_edge=k//2*per_host
            per_aggregation=per_edge
            # Same serialized controller uplink as SwitchService, with one stats entry
            # and two update entries per flow; uniform groups on both switch layers.
            uplink_time=.00001+per_edge*576/1e9+hosts*per_host*576/10e9
            downstream=.00001+max(per_edge,per_aggregation)*576/1e9+2*hosts*per_host*576/10e9
            value=100+1000*(uplink_time+downstream)
            local.append(value)
            projection.append(dict(hosts=hosts,flows_per_host=per_host,model_ms=value,paper_ms=benchmark,
                                   stats_bytes=72*edge_count*per_edge,rules_bytes=144*hosts*per_host))
        ax[1].plot([1,5,10],local,"o-",color=color,label=f"{hosts:,}")
        ax[1].plot([1,5,10],observed,"x--",color=color,alpha=.65)
    write(data/"control-projection.csv",projection)
    ax[1].set(xlabel="Flow lớn mỗi host",ylabel="Vòng điều khiển (ms)")
    ax[1].legend(frameon=False,fontsize=7,title="Số host")
    save(fig,"control")
    fig,axs=plt.subplots(1,3,figsize=(7.2,2.35),sharey=True)
    recovery=[]
    outage_series=[]
    for ax,alg in zip(axs,ALGS[:3]):
        for case in ["healthy","outage"]:
            selected=[(seed,p) for c,seed,a,p,_ in runs if c==case and a==alg]
            series=[]
            for seed,path in selected:
                trace=read(path/"goodput.csv")
                t=np.array([float(r["time"]) for r in trace])
                y=np.array([float(r["payload_bps"])/1e6 for r in trace])
                series.append(y)
                outage_series.extend(dict(case=case, seed=seed, algorithm=alg, time_s=x, goodput_mbps=v)
                                     for x,v in zip(t,y))
                if case=="outage":
                    event=read(path/"failure.csv")[1]
                    reference=y[(t>1)&(t<=2)].mean()
                    eligible=[i for i in range(len(t)-2) if t[i]>=2.15 and t[i+2]<=4.8 and min(y[i:i+3])>=.9*reference]
                    recovery.append(dict(seed=seed,algorithm=alg,affected=int(event["affected_flows"]),
                                         notice_ms=1000*(float(event["time"])-2),
                                         recovery_confirmed_s=round(t[eligible[0]+2]-2,6) if eligible else ""))
            ax.plot(t,np.mean(series,axis=0),color=COLORS[alg],linestyle="-" if case=="outage" else "--",linewidth=1)
        ax.axvline(2,color="#8b3c48",linewidth=.85)
        ax.set(title=LABEL[alg],xlim=(1,4.8),xlabel="Thời gian (s)")
    axs[0].set_ylabel("Goodput tổng (Mbit/s)")
    save(fig,"outage")
    write(data/"recovery.csv",recovery)
    write(data/"outage-timeseries.csv",outage_series)
    shuffle=[]
    shuffle_metrics=[]
    fig,ax=plt.subplots(1,2,figsize=(7.2,2.45),sharey=True)
    relaxed=packet_runs(base/"shuffle-ack")
    assert len(relaxed)==8
    for panel,profile,sample,horizon in [
        (ax[0],"1MiB",[r for r in runs if r[0]=="sequential-shuffle"],31),
        (ax[1],"256KiB",relaxed,21)]:
        for _,seed,alg,path,_ in sample:
            fs=read(path/"flows.csv")
            assert len(fs)==240
            elapsed=(max(float(f["finish"]) for f in fs)-min(float(f["start"]) for f in fs)
                     if all(int(f["completed"]) for f in fs) else None)
            host_times, host_rates = [], []
            for src in range(16):
                subset=[f for f in fs if int(f["src"])==src]
                completed=sum(int(f["completed"]) for f in subset)
                finish=max(float(f["finish"]) for f in subset)-min(float(f["start"]) for f in subset) if completed==15 else None
                if finish is not None:
                    host_times.append(finish)
                    host_rates.append(sum(int(f["rx_bytes"]) for f in subset)/finish/1e6)
                shuffle.append(dict(profile=profile,seed=seed,algorithm=alg,source=src,
                                    completed_transfers=completed,host_s=finish,shuffle_s=elapsed))
            cut_bytes = sum(int(f["rx_bytes"]) for f in fs if (int(f["src"])<8)!=(int(f["dst"])<8))
            shuffle_metrics.append(dict(profile=profile,seed=seed,algorithm=alg,hosts_completed=len(host_times),
                                        transfers_completed=sum(int(f["completed"]) for f in fs),
                                        shuffle_s=elapsed, mean_host_s=stat.mean(host_times) if elapsed else None,
                                        cut_payload_mbps=8*cut_bytes/elapsed/1e6 if elapsed else None,
                                        mean_host_payload_MBps=stat.mean(host_rates) if elapsed else None))
        for alg in ALGS:
            selected=[r for r in shuffle if r["profile"]==profile and r["algorithm"]==alg]
            times=sorted(r["host_s"] for r in selected if r["host_s"] is not None)
            y=np.arange(len(times)+1)/len(selected)
            panel.step([0]+times+[horizon],np.r_[y,y[-1]],where="post",color=COLORS[alg],
                       linestyle=STYLES[alg],label=LABEL[alg])
        panel.set(title=profile+" mỗi cặp",xlabel="Thời gian từ khi bắt đầu (s)",ylim=(0,1.05))
    ax[0].set_ylabel("Tỷ lệ host đã hoàn thành")
    ax[1].legend(frameon=False,fontsize=7,loc="lower right")
    write(data/"shuffle.csv",shuffle)
    write(data/"shuffle-table2.csv",shuffle_metrics)
    save(fig,"shuffle")
    return latency,recovery,shuffle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results",type=Path)
    parser.add_argument("project",type=Path)
    parser.add_argument("--allow-partial-gigabit",action="store_true")
    a=parser.parse_args()
    figures=a.project/"figures"
    data=a.project/"data"
    figures.mkdir(parents=True,exist_ok=True)
    data.mkdir(parents=True,exist_ok=True)
    provenance=data/"provenance"
    provenance.mkdir(exist_ok=True)
    for suite in ("compact16","scaled16","gigabit16","gigabit-tcp","gigabit-tcp-short","gigabit-bijection","mechanisms","shuffle-ack",
                  "flow","flow-figure10-stag50"):
        manifest=a.results/suite/"manifest.json"
        if manifest.is_file():
            shutil.copyfile(manifest,provenance/(suite+".json"))
    for name in ("machine.txt","ctest.log"):
        local=a.results/"core-verified"/name
        if local.is_file():
            shutil.copyfile(local,provenance/name)
    for log in sorted(a.results.glob("*-validation.log")):
        shutil.copyfile(log,provenance/log.name)

    def save(fig,name):
        fig.tight_layout()
        fig.savefig(figures/(name+".pdf"),bbox_inches="tight",pad_inches=.04)
        plt.close(fig)

    architecture(save)
    restriction_fixture(save)
    packet=packet_analysis(a.results,data,save)
    tcp, tcp_metrics=tcp_analysis(a.results,data,save)
    bijection=gigabit_bijection_analysis(a.results,data,save)
    flow=flow_analysis(a.results,data,save)
    restricted,max_gap=core_analysis(a.results,data,save)
    latency,recovery,shuffle=mechanism_analysis(a.results,data,save)
    exact=[r for r in packet if r["rate_mbps"]==1000]
    extended_count=sum(r["profile"]=="extended" for r in packet)
    if (len(exact),extended_count,len(tcp))!=(4,32,5) and not a.allow_partial_gigabit:
        raise RuntimeError("Long-window or TCP suite incomplete. Use --allow-partial-gigabit for a draft.")
    index=dict(packet_profiles={p:sum(r["profile"]==p for r in packet)
                                for p in ("compact","extended","gigabit")},
               tcp_cases=[r[0] for r in tcp], gigabit_bijection_runs=3*len(bijection), mechanisms=26, shuffle_ack=8,
               flow_cases=len(flow), flow_cases_for_figures=sum(r["pattern"]!="stag50" for r in flow),
               estimator_timings=40, sa_timings=120, sa_oracle_comparisons=720)
    (provenance/"study-index.json").write_text(json.dumps(index,indent=2)+"\n",encoding="utf-8")
    defs={}

    def number(name,value,digits=2):
        defs[name]=f"{value:.{digits}f}".replace(".","{,}")

    number("GigabitCount",len(exact),0)
    number("ExtendedCount",extended_count,0)
    defs["GigabitRevisionNote"]=""
    if exact:
        gigabit_manifest=json.loads((a.results/"gigabit16"/"manifest.json").read_text())
        compact_manifest=json.loads((a.results/"compact16"/"manifest.json").read_text())
        if gigabit_manifest["source_sha256"]!=compact_manifest["source_sha256"]:
            defs["GigabitRevisionNote"]=(" Các lượt này dùng phiên bản mô phỏng trước khi bổ sung "
                                         "lỗi liên kết, shuffle và mô hình cài luật chuyển tiếp.")
    for alg in ALGS:
        suffix={"ecmp":"Ecmp","gff":"Gff","sa":"Sa","nonblocking":"Nb"}[alg]
        if bijection:
            number("Bijection"+suffix+"Mean",bijection[alg]["mean"])
            if alg in {"gff","sa"}:
                number("Bijection"+suffix+"Gain",bijection[alg]["mean_gain"],1)
                number("Bijection"+suffix+"Low",bijection[alg]["low_gain"],1)
                number("Bijection"+suffix+"High",bijection[alg]["high_gain"],1)
                number("Bijection"+suffix+"Wins",bijection[alg]["wins"],0)
        selected=[r for r in exact if r["algorithm"]==alg]
        if selected:number("Gigabit"+suffix,selected[0]["total"])
        else:defs["Gigabit"+suffix]="--"
        number("Compact"+suffix,stat.mean(r["total"] for r in packet if r["profile"]=="compact"
               and r["case"]=="paper-stride-8" and r["algorithm"]==alg))
        extended=[r["total"] for r in packet if r["profile"]=="extended"
                  and r["case"]=="paper-stride-8" and r["algorithm"]==alg]
        if extended:number("Extended"+suffix,stat.mean(extended))
        else:defs["Extended"+suffix]="--"
        number("Flow"+suffix,stat.mean(r["total_gbps"] for r in flow if r["k"]==16 and
               r["pattern"]=="randbij" and r["algorithm"]==alg))
        subset=[r for r in shuffle if r["algorithm"]==alg and r["profile"]=="256KiB"]
        finished=[r["shuffle_s"] for r in subset if r["shuffle_s"] is not None]
        if len(finished)==len(subset): number("Shuffle"+suffix,stat.mean(finished))
        else: defs["Shuffle"+suffix]="--"
        number("ShuffleHosts"+suffix,sum(r["host_s"] is not None for r in subset),0)
    baseline=next((r for r in tcp_metrics if r["case"]=="gigabit-reference"),None)
    if baseline:
        number("TcpOneMss",100*baseline["cwnd_at_one_mss_fraction"],1)
        number("TcpLossEvents",baseline["loss_state_transitions"],0)
        number("TcpQueueDrops",baseline["queue_disc_drops"],0)
    else:
        defs["TcpOneMss"]="--"
        defs["TcpLossEvents"]=defs["TcpQueueDrops"]="--"
    for case, label in [("default","TcpDefault"),("ack5","TcpAckFive"),("ack1","TcpAckOne"),("rto300","TcpRtoThree")]:
        row=next((r for r in tcp_metrics if r["case"]=="gigabit-"+case),None)
        if row:number(label,row["goodput_gbps"],4)
        else:defs[label]="--"
    sweep=[r for r in flow if r["k"]==16 and r["pattern"]=="rand" and r["steps"]==100]
    for state, label in [(0,"Cold"),(1,"Warm")]:
        number("Sweep"+label,stat.mean(r["total_gbps"] for r in sweep if r["warm"]==state),1)
    runtime=read(data/"runtime.csv")
    number("RuntimeSaLarge",stat.median(float(r["runtime_ms"]) for r in runtime if
           r["variant"]=="destination" and int(r["flows"])==50000 and int(r["iterations"])==10000),1)
    for name,case,alg in [("EventGff","gff-on-detection","gff"),("PeriodicGff","periodic","gff"),("PeriodicSa","periodic","sa")]:
        number(name,stat.median(r["latency_ms"] for r in latency if r["case"]==case and r["algorithm"]==alg),1)
    number("RestrictionCases",restricted,0)
    number("RestrictionGap",max_gap,4)
    quality=read(data/"oracle.csv")
    for variant,suffix in [("flow","Flow"),("destination","Dst")]:
        outcomes=[r for r in quality if r["variant"]==variant and int(r["steps"])==1000]
        number("Solved"+suffix,sum(abs(float(r["sa_energy"])-float(r["oracle_energy"]))<1e-8 for r in outcomes),0)
    number("RecoveryCount",sum(r["recovery_confirmed_s"]!="" for r in recovery),0)
    number("RecoveryTotal",len(recovery),0)
    (a.project/"numbers.tex").write_text("".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k,v in defs.items()),encoding="utf-8")
    print("Figures and derived data written to", a.project)


if __name__=="__main__":
    main()
