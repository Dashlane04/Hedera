#!/usr/bin/env python3
"""Check endpoint delivery, sticky ECMP, SA energies and matched workloads."""
import argparse
import csv
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def validate(root, require_complete=False, match_workloads=False):
    paths = sorted(root.rglob('summary.json'))
    if not paths:
        raise AssertionError(f'no summary.json under {root}')
    groups = {}
    # A study manifest declares matched inputs. A smoke-test directory contains
    # intentionally different configurations (e.g. locality=0 and locality=1).
    match_workloads = match_workloads or (root / 'manifest.json').is_file()
    for path in paths:
        summary = json.loads(path.read_text())
        directory = path.parent
        flows = rows(directory / 'flows.csv')
        assert len(flows) == summary['flows'], directory
        assert all(int(f['rx_bytes']) >= 0 and (int(f['bytes']) == 0 or int(f['rx_bytes']) <= int(f['bytes'])) for f in flows), directory
        zero_payload = sum(int(f['rx_bytes']) == 0 for f in flows)
        # A queue-dropped SYN/SYN-ACK may leave a legitimate censored flow
        # with zero payload at this finite stop time. Detect routing defects
        # using explicit ns-3.47 FlowProbe reasons, not payload completion.
        monitor = ET.parse(directory / 'flow-monitor.xml').getroot()
        for stat in monitor.find('FlowStats'):
            for drop in stat.findall('packetsDropped'):
                if int(drop.get('reasonCode')) in {0, 1, 2, 5, 6, 7}:
                    assert int(drop.get('number')) == 0, f'routing/checksum/interface defect: {directory}'
        complete = sum(int(f['completed']) for f in flows)
        assert complete == summary['completed'], directory
        if require_complete:
            assert complete == len(flows), f'incomplete: {directory}'
        for flow in flows:
            if int(flow['bytes'])==0:
                assert not int(flow['completed']) and float(flow['fct'])==-1, directory
            if int(flow['completed']):
                assert abs(float(flow['finish']) - float(flow['start']) - float(flow['fct'])) < 1e-8
        routes = rows(directory / 'routes.csv')
        assert sum(bool(route['old_path']) for route in routes) == summary['route_changes']
        failure_log = directory / 'failure.csv'
        if failure_log.is_file():
            outage, notice = rows(failure_log)
            assert outage['event'] == 'outage' and notice['event'] == 'routing_notified', directory
            assert float(notice['time']) >= float(outage['time']), directory
            blocked = {notice['from'], notice['to']}
            recovered = [r for r in routes if r['reason']=='failure_fallback']
            assert len(recovered)==int(notice['affected_flows']), directory
            for route in routes:
                if float(route['time']) >= float(notice['time'])-1e-9:
                    nodes = route['new_path'].split('-')
                    assert all({a,b}!=blocked for a,b in zip(nodes,nodes[1:])), directory
        if summary['algorithm'] in {'ecmp', 'nonblocking'}:
            assert all(not r['old_path'] or (failure_log.is_file() and r['reason']=='failure_fallback')
                       for r in routes), 'ECMP changed a healthy path'
        if summary.get('workload')=='shuffle':
            starts = {int(r['flow_id']):float(r['time']) for r in rows(directory/'workload-events.csv')
                      if r['event']=='source_start'}
            for current,following in zip(flows,flows[1:]):
                if current['src']==following['src'] and int(following['flow_id']) in starts:
                    assert int(current['completed']), directory
                    assert starts[int(following['flow_id'])] >= float(current['finish'])-1e-9, directory
        if summary['algorithm'] == 'sa':
            for tick in rows(directory / 'controller.csv'):
                assert float(tick['best_energy']) <= float(tick['initial_energy']) + 1e-8
        for link in rows(directory / 'links.csv'):
            assert math.isfinite(float(link['utilization']))
            # A packet's entire byte count is charged when serialization starts,
            # so one packet may straddle a sampling boundary.
            assert 0 <= float(link['utilization']) <= 1.05
        # Only demand identical workload content for an explicitly matched group.
        key = (summary['workload'], summary['seed'], summary['run'], summary['k'],
               summary['duration_s'], summary['interval_s'], summary['control_delay_s'],
               summary.get('traffic_mode','finite'),summary.get('hash_mode','flow'),
               summary.get('hash_mix','legacy'),summary.get('offered_load'),
               summary.get('edge_probability'),summary.get('pod_probability'),summary.get('stride'),
               summary.get('benchmark_case'))
        content = (directory / 'workload.csv').read_bytes()
        if match_workloads and key in groups:
            assert groups[key] == content, f'unmatched workloads: {directory}'
        groups[key] = content
        if summary.get('diagnostics'):
            samples=rows(directory/'tcp-samples.csv')
            assert samples and all(0<=int(r['flow_id'])<len(flows) for r in samples),directory
            assert all(float(r['rto_s'])>=0 and float(r['rtt_s'])>=0 for r in samples),directory
            if summary['algorithm'] in {'gff','sa'}:
                for row in rows(directory/'controller-flows.csv'):
                    demand=float(row['selected_demand']); measured=float(row['measured_fraction'])
                    assert math.isfinite(demand) and demand>=0,directory
                    if summary['demand_mode']=='measured': assert abs(demand-measured)<1e-9,directory
        if summary.get('schema_version',0)>=4:
            events=rows(directory/'control-events.csv')
            submits={int(e['plan_id']):float(e['snapshot_time']) for e in events if e['event']=='submit'}
            starts={int(e['plan_id']):float(e['time']) for e in events if e['event']=='start'}
            finals=[e for e in events if e['event'] in {'install','expired'}]
            ids=[int(e['plan_id']) for e in finals]
            assert ids==sorted(set(ids)),('non-monotone installation',directory)
            switch_log=directory/'switch-control.csv'
            ready={}
            if switch_log.is_file():
                ready={int(e['plan_id']):float(e['time']) for e in rows(switch_log)
                       if e['phase']=='ready_to_activate'}
            for e in finals:
                pid=int(e['plan_id'])
                assert pid in submits and pid in starts,directory
                assert abs(float(e['time'])-ready.get(pid,starts[pid])-summary['control_delay_s'])<1e-8,directory
            assert len(submits)==summary['plans_submitted'],directory
            assert summary['plans_submitted']==sum(summary[k] for k in
                ['plans_installed','plans_replaced','plans_expired','pending_plans_at_stop']),directory
            for f in flows:
                assert float(f['start'])<float(f['stop'])<=summary['duration_s'],directory
                detected=float(f['first_detected_s'])
                assert detected<0 or detected>=float(f['start']),directory
        completion=f'{complete}/{len(flows)} complete' if summary.get('traffic_mode','finite')=='finite' else f'{len(flows)} persistent (FCT N/A)'
        print(f'PASS {directory.name}: {completion}, '
              f'{summary["route_changes"]} reroutes, {zero_payload} zero-payload censored')
    print(f'Validated {len(paths)} scenarios.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--require-complete', action='store_true')
    parser.add_argument('--match-workloads', action='store_true', help='enforce matched inputs even without a study manifest')
    args = parser.parse_args()
    validate(args.root, args.require_complete, args.match_workloads)
