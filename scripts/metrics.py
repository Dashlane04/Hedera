"""Shared metrics: exact window byte counters; explicit conditional populations."""
import csv
import json
import math
import statistics
from collections import defaultdict


def read_rows(path):
    if not path.is_file():
        return []
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def quantile(values, p):
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)] if values else None


def jain(values):
    # Zero-throughput members stay in the population; undefined if all are zero.
    return sum(values) ** 2 / (len(values) * sum(x*x for x in values)) if values and any(values) else None


def run_metrics(directory, summary=None):
    s = summary or json.loads((directory/'summary.json').read_text())
    lo, hi = s['measurement_start_s'], s['measurement_end_s']
    fs = read_rows(directory/'flows.csv')
    finite = [f for f in fs if int(f['bytes']) > 0]
    done = [f for f in finite if int(f['completed'])]
    fcts = [float(f['fct']) for f in done]
    detail = []
    for f in fs:
        start, stop = float(f['start']), float(f.get('stop', s['duration_s']))
        detail.append(dict(flow_id=int(f['flow_id']), src=int(f['src']), dst=int(f['dst']),
                           cohort=f.get('cohort', 'default'), start=start, stop=stop,
                           goodput_mbps=int(f['window_rx_bytes'])*8/(hi-lo)/1e6,
                           completed=int(f['completed']), fct_s=float(f['fct']) if int(f['completed']) else None,
                           route_changes=int(f['route_changes']),
                           window_overlap=start < hi and stop > lo,
                           full_window_persistent=int(f['bytes']) == 0 and start <= lo and stop >= hi))
    common = [f['goodput_mbps'] for f in detail if f['full_window_persistent']]
    cohorts = []
    for name in sorted({f['cohort'] for f in detail}):
        members = [f for f in detail if f['cohort'] == name]
        eligible = [f['goodput_mbps'] for f in members if f['full_window_persistent']]
        cohorts.append(dict(cohort=name, flows=len(members), goodput_mbps=sum(f['goodput_mbps'] for f in members),
                            jain_common_active=jain(eligible), fairness_population=len(eligible)))
    events_path = directory/'tcp-events.csv'
    drop_path = directory/'queue-drops.csv'
    events = read_rows(events_path)
    drops = read_rows(drop_path)
    window = lambda r: lo <= float(r['time']) <= hi
    retx = [r for r in events if window(r) and r['event'] == 'retransmission']
    control = read_rows(directory/'control-events.csv')
    ages = [float(r['age_s']) for r in control if r['event'] == 'install']
    result = dict(conditional_p95_fct_s=quantile(fcts, .95),
                  finite_cohort_size=len(finite), completed_finite=len(done),
                  jain_goodput_common_active=jain(common), fairness_population=len(common),
                  per_flow_goodput_p10_mbps=quantile([f['goodput_mbps'] for f in detail if f['window_overlap']], .1),
                  window_retransmissions=len(retx) if events_path.is_file() else None,
                  window_retransmitted_trace_bytes=sum(int(r['payload_bytes']) for r in retx) if events_path.is_file() else None,
                  window_data_qdisc_drops=sum(window(r) and r['direction']=='data' for r in drops) if drop_path.is_file() else None,
                  window_ack_qdisc_drops=sum(window(r) and r['direction']=='ack' for r in drops) if drop_path.is_file() else None,
                  route_changes=s['route_changes'],
                  plans_submitted=s.get('plans_submitted'), plans_replaced=s.get('plans_replaced'),
                  plans_expired=s.get('plans_expired'), inactive_install_skips=s.get('inactive_install_skips'),
                  mean_install_age_s=statistics.mean(ages) if ages else None,
                  p95_install_age_s=quantile(ages,.95))
    return result, detail, cohorts


def background_series(directory):
    fs=read_rows(directory/'flows.csv')
    ids={int(f['flow_id']) for f in fs if f.get('cohort')=='background'}
    if not ids:
        return []
    samples=defaultdict(dict)
    for r in read_rows(directory/'tcp-samples.csv'):
        fid=int(r['flow_id'])
        if fid in ids:
            samples[float(r['time'])][fid]=int(r['rx_bytes'])
    previous, time = 0, 0
    series=[]
    for t, rows in sorted(samples.items()):
        if len(rows)!=len(ids):
            raise ValueError('background sample population changed')
        total=sum(rows.values())
        series.append(dict(time=t,mbps=(total-previous)*8/(t-time)/1e6))
        previous,time=total,t
    return series


def phase_metrics(directory):
    phases=read_rows(directory/'phases.csv')
    if not phases:
        return []
    series=background_series(directory)
    fs=read_rows(directory/'flows.csv')
    routes=read_rows(directory/'routes.csv')
    result=[]
    baseline=None; burst_mean=None
    for phase in phases:
        start,end=float(phase['start']),float(phase['end'])
        # Tick buckets entirely inside the phase; exclude boundary-straddling buckets.
        s=json.loads((directory/'summary.json').read_text())
        interval=s['interval_s']
        samples=[r for r in series if r['time']-interval >= start-1e-8 and r['time'] <= end+1e-8]
        mean=statistics.mean(r['mbps'] for r in samples) if samples else None
        if phase['name']=='baseline':
            steady=[r['mbps'] for r in samples if r['time'] >= start+0.5]
            baseline=statistics.mean(steady) if steady else mean
        if phase['name']=='burst': burst_mean=mean
        recovery=None; status='not_recovery_phase'
        if phase['name']=='recovery' and baseline and burst_mean is not None and burst_mean>=.95*baseline:
            status='no_preceding_mean_degradation'
        elif phase['name']=='recovery' and baseline:
            status='not_observed'
            for i in range(len(samples)-2):
                if all(r['mbps']>=.95*baseline for r in samples[i:i+3]):
                    recovery=samples[i+2]['time']-start; status='three_consecutive_buckets'; break
        born=[f for f in fs if start-1e-8 <= float(f['start']) < end-1e-8]
        detected=[float(f['first_detected_s'])-float(f['start']) for f in born if float(f.get('first_detected_s',-1))>=0]
        ids={int(f['flow_id']) for f in born}
        changes=[float(r['time'])-start for r in routes if r['old_path'] and int(r['flow_id']) in ids and start <= float(r['time']) < end]
        result.append(dict(phase=phase['name'],start=start,end=end,background_goodput_mbps=mean,
                           sampled_buckets=len(samples),baseline_background_mbps=baseline,
                           preceding_burst_background_mbps=burst_mean,
                           recovery_95pct_s=recovery,recovery_status=status,
                           mean_new_flow_detection_s=statistics.mean(detected) if detected else None,
                           first_new_flow_reroute_s=min(changes) if changes else None))
    return result
