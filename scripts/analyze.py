#!/usr/bin/env python3
"""Aggregate independent runs; plot mean +/- sample standard deviation (not CI)."""
import argparse
import csv
import json
from pathlib import Path
import statistics


COLORS = {'ecmp': '#64748b', 'gff': '#0f766e', 'sa': '#d97706', 'nonblocking': '#2563eb'}


def read_csv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def plot_time_series(directory, summary, plt):
    """Plot recorded interval samples; do not synthesize extra traffic points."""
    goodput = read_csv(directory / 'goodput.csv')
    flows = read_csv(directory / 'flows.csv')
    links = read_csv(directory / 'links.csv')
    nodes = read_csv(directory / 'nodes.csv')
    if not goodput:
        print(f'No time samples in {directory}; skipping time-series plot.')
        return
    times = [float(row['time']) for row in goodput]
    end = times[-1]
    color = COLORS[summary['algorithm']]
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout='constrained')

    ax = axes[0, 0]
    ax.stairs([float(row['payload_bps']) / 1e6 for row in goodput],
              [0] + times, color=color, linewidth=1.8)
    ax.set_title('Aggregate application goodput')
    ax.set_ylabel('Mbit/s')

    ax = axes[0, 1]
    ax.plot([0] + times,
            [0] + [int(row['cumulative_payload_bytes']) / (1024 ** 2) for row in goodput],
            color=color, linewidth=1.8)
    ax.set_title('Cumulative application payload received')
    ax.set_ylabel('MiB')

    core_ids = {int(row['model_node']) for row in nodes if row['kind'] == 'core'}
    core_rates = {core: {} for core in core_ids}
    for row in links:
        core = int(row['from'])
        if core in core_ids:
            t = float(row['time'])
            rates = core_rates[core]
            rates[t] = rates.get(t, 0) + float(row['utilization']) * summary['link_rate_bps'] / 1e6
    ax = axes[1, 0]
    # Keep large topologies readable. Plot the busiest eight cores, counting
    # recorded samples, rather than selecting based on the routing algorithm.
    selected = sorted(core_rates, key=lambda core: (-sum(core_rates[core].values()), core))[:8]
    for core in selected:
        ax.stairs([core_rates[core].get(t, 0) for t in times], [0] + times,
                  linewidth=1.3, label=f'Core node {core}')
    ax.set_title('Core egress traffic (includes headers and ACKs)')
    ax.set_ylabel('Mbit/s summed over core egress links')
    if selected:
        ax.legend(fontsize=8, loc='upper right')
    else:
        ax.text(0.5,0.5,'Single-switch reference: no core tier',ha='center',transform=ax.transAxes)

    finishes = sorted(float(row['finish']) for row in flows if int(row['completed']))
    ax = axes[1, 1]
    # Exact completion events are recorded separately from periodic counters.
    completion_end = max([end] + finishes)
    ax.step([0] + finishes + [completion_end],
            [0] + list(range(1, len(finishes) + 1)) + [len(finishes)],
            where='post', color=color, linewidth=1.8)
    ax.axhline(len(flows), color='#94a3b8', linestyle=':', label=f'{len(flows)} offered flows')
    ax.set_title('Completed flows over time')
    if summary.get('traffic_mode')=='sustained':
        ax.set_title('Persistent connections: completion is not measured')
    ax.set_ylabel('Flow count')
    ax.set_ylim(0, max(1, len(flows) * 1.12))
    ax.legend(fontsize=8, loc='lower right')

    for ax in axes.flat:
        stop = summary['duration_s']
        if stop <= completion_end:
            ax.axvline(stop, color='#b91c1c', linestyle='--', linewidth=1)
        ax.set_xlabel('Simulation time (s)')
        ax.set_xlim(0, completion_end)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.22)
        ax.set_axisbelow(True)
    fig.suptitle(f'{summary["algorithm"].upper()} | {summary["workload"]} | '
                 f'k={summary["k"]}, seed={summary["seed"]}, run={summary["run"]}\n'
                 f'Red dashed line: source stop; interval rates are averages over {summary["interval_s"]:g} s',
                 fontsize=12)
    target = directory / 'timeseries.png'
    fig.savefig(target, dpi=160)
    plt.close(fig)
    print(f'Wrote {target}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--no-plot', action='store_true')
    parser.add_argument('--time-series', action='store_true',
                        help='also plot each run over time; automatic for a single run')
    args = parser.parse_args()
    summary_paths = sorted(args.root.rglob('summary.json'))
    summaries = [json.loads(p.read_text()) for p in summary_paths]
    if not summaries:
        parser.error('no summaries found')
    columns = ['workload', 'algorithm', 'seed', 'run', 'k', 'flows', 'completed',
               'completion_fraction', 'window_goodput_mbps', 'mean_fct_completed_s',
               'p95_fct_completed_s', 'mean_scheduler_wall_us', 'route_changes']
    with (args.root / 'comparison.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({c: row[c] for c in columns} for row in summaries)
    groups = {}
    for summary in summaries:
        groups.setdefault((summary.get('benchmark_case',summary['workload']), summary['algorithm']), []).append(summary)
    aggregate = []
    metrics = ['window_goodput_mbps', 'mean_fct_completed_s', 'completion_fraction', 'mean_scheduler_wall_us']
    for (workload, algorithm), group in sorted(groups.items()):
        row = dict(workload=workload, algorithm=algorithm, n=len(group))
        for metric in metrics:
            values = [s[metric] for s in group if s[metric] is not None]
            row[metric + '_mean'] = statistics.mean(values) if values else None
            row[metric + '_std'] = statistics.stdev(values) if len(values) > 1 else 0
            row[metric + '_n'] = len(values)
        aggregate.append(row)
    with (args.root / 'aggregate.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(aggregate[0]))
        writer.writeheader()
        writer.writerows(aggregate)
    print(f'Wrote comparison.csv and aggregate.csv for {len(summaries)} runs.')
    if args.no_plot:
        return
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('matplotlib unavailable; CSV results are ready. Install matplotlib to plot.')
        return
    workloads = sorted({r['workload'] for r in aggregate})
    fig, axes = plt.subplots(len(workloads), 3, figsize=(12, 3.6 * len(workloads)), squeeze=False)
    for row_index, workload in enumerate(workloads):
        for col, (metric, title) in enumerate([
            ('window_goodput_mbps', 'Payload goodput (Mbit/s)'),
            ('mean_fct_completed_s', 'Mean FCT of completed flows (s)'),
            ('completion_fraction', 'Fraction completed')]):
            selected = sorted((r for r in aggregate if r['workload'] == workload),
                              key=lambda r: ['ecmp', 'gff', 'sa', 'nonblocking'].index(r['algorithm']))
            ax = axes[row_index, col]
            values = [r[metric + '_mean'] if r[metric + '_mean'] is not None else float('nan') for r in selected]
            # A single run cannot estimate variability. Omit its error bar.
            errors = [r[metric + '_std'] if r[metric + '_n'] > 1 else float('nan') for r in selected]
            ax.bar([r['algorithm'].upper() for r in selected], values,
                   yerr=errors if any(r[metric + '_n'] > 1 for r in selected) else None,
                   capsize=4, width=0.55,
                   color=[COLORS[r['algorithm']] for r in selected])
            if len(selected) == 1:
                ax.set_xlim(-0.8, 0.8)
            for index, value in enumerate(values):
                if value == value:
                    ax.annotate(f'{value:.3g}', (index, value), xytext=(0, 5),
                                textcoords='offset points', ha='center', fontsize=9)
            if not any(value==value for value in values):
                ax.text(0.5,0.5,'Not applicable to persistent traffic',ha='center',transform=ax.transAxes,fontsize=9)
            ax.set_title(f'{workload}: {title}')
            tops = [r[metric + '_mean'] + r[metric + '_std'] for r in selected
                    if r[metric + '_mean'] is not None]
            ax.set_ylim(0, max(tops) * 1.18 if tops and max(tops) > 0 else 1)
            if metric == 'completion_fraction':
                ax.set_ylim(0, 1.12)
            ax.grid(axis='y', alpha=0.25)
            ax.set_axisbelow(True)
    fig.suptitle('Hedera ns-3 prototype | aggregate bars; error bars: sample SD only when n >= 2\n'
                 'FCT excludes unfinished flows; interpret with completion fraction', fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(args.root / 'comparison.png', dpi=160)
    plt.close(fig)
    print('Wrote comparison.png.')
    if args.time_series or len(summary_paths) == 1:
        for path, summary in zip(summary_paths, summaries):
            plot_time_series(path.parent, summary, plt)


if __name__ == '__main__':
    main()
