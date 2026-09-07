"""Analyze completed targeted repeats; never launches benchmarks.

First run capacity.py plot for all nine repeat directories, then:
    python3 diagnostic_capacity_analysis.py
Uses the same NumPy/Matplotlib environment as capacity.py.
"""
import json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from capacity_refinement_analysis import ROOT, read_run, write_csv


def change(value, baseline):
    if baseline <= 0:
        raise ValueError('Positive baseline required')
    return 100 * (value / baseline - 1)


def spread(values):
    return change(max(values), min(values))


def key(row):
    return row['mode'], float(row['size_kib'])


def main():
    campaign = ROOT / 'results/capacity-diagnostic-20260907'
    output = campaign / 'analysis'
    output.mkdir(exist_ok=True)
    summaries, comparisons, spreads, chunks, activity, manifest = [], [], [], [], [], {}
    fields = ('mean', 'median', 'stddev', 'q1', 'q3', 'p5', 'p95', 'outliers', 'zeros')
    for host in ('charnwood', 'crux', 'artemisia'):
        directory = (ROOT / 'results/capacity-diagnostic-20260907-retry1' if host == 'artemisia' else campaign) / host
        assert (directory / 'COMPLETE').exists()
        plan = json.loads((directory / 'plan.json').read_text())
        # Resolve the archived campaign under this workspace, not its old absolute mount path.
        source = ROOT / ('results/crux-new-core-20260906T235055Z/crux' if host == 'crux'
                         else 'results/capacity-20260906/' + host)
        runs, paths = {}, {}
        for name in ('full', 'refine-small', 'refine-middle', 'refine-large', 'repeat1', 'repeat2', 'repeat3'):
            diagnostic = name.startswith('repeat')
            path = (directory if diagnostic else source) / name
            sizes = plan['sizes_kib'] if diagnostic else sorted(json.loads((path / 'environment.json').read_text())['arguments']['sizes_kib'])
            env, rows = read_run(path, sizes)
            assert env['hostname'].split('.')[0] == host
            assert env['arguments']['cpu'] == plan['selected']['cpu']
            assert all(env[f] == plan[f] for f in ('binary_sha256', 'source_sha256'))
            runs[name], paths[name] = rows, str(path.relative_to(ROOT))
            for row in rows:
                if diagnostic:
                    summaries.append(dict(host=host, run=name, directory=paths[name], **row))
                if row['mode'] == 'empty' or float(row['size_kib']) not in plan['sizes_kib']:
                    continue
                raw = path / f"{row['mode']}_{int(float(row['size_kib']))}KiB.bin"
                meta = json.loads(raw.with_suffix('.json').read_text())
                values = np.memmap(raw, dtype='<u8' if meta['byte_order'] == 'little' else '>u8', mode='r')
                assert values.size == 1000000
                for i, block in enumerate(np.array_split(values, 10), 1):
                    chunks.append(dict(host=host, run=name, mode=row['mode'], size_kib=row['size_kib'],
                                       chunk=i, samples=len(block), unit=row['unit'],
                                       median=float(np.median(block)) / 4096, raw_file=str(raw.relative_to(ROOT))))
            if diagnostic:
                pre = json.loads((directory / f'{name}-preflight.json').read_text())
                act = json.loads((directory / f'{name}-activity.json').read_text())
                for cpu in plan['selected']['siblings']:
                    activity.append(dict(host=host, run=name, cpu=cpu, selected_cpu=cpu == plan['selected']['cpu'],
                                         preflight_busy_percent=pre['all_cpu_busy_percent'][str(cpu)],
                                         whole_repeat_busy_percent=act['all_cpu_busy_percent'][str(cpu)],
                                         elapsed_seconds=act['elapsed_seconds']))
        indexed = {name: {key(row): row for row in rows} for name, rows in runs.items()}
        for k, row in indexed['repeat1'].items():
            values = [float(indexed[f'repeat{n}'][k]['median']) for n in (1, 2, 3)]
            spreads.append(dict(host=host, mode=k[0], size_kib=k[1], unit=row['unit'],
                                repeat1=values[0], repeat2=values[1], repeat3=values[2],
                                median_spread_percent=spread(values)))
            if k[0] == 'empty':
                continue  # Empty controls have different footprint/setup across historical groups.
            for name in ('full', 'refine-small', 'refine-middle', 'refine-large'):
                if k not in indexed[name]:
                    continue
                old = indexed[name][k]
                for n in (1, 2, 3):
                    current = indexed[f'repeat{n}'][k]
                    assert old['unit'] == current['unit']
                    record = dict(host=host, baseline=name, repeat=n, mode=k[0], size_kib=k[1],
                                  unit=row['unit'], median_change_percent=change(float(current['median']), float(old['median'])))
                    for field in fields:
                        record['baseline_' + field], record['repeat_' + field] = old[field], current[field]
                    comparisons.append(record)
        manifest[host] = dict(runs=paths, selected=plan['selected'], binary_sha256=plan['binary_sha256'],
                              source_sha256=plan['source_sha256'])
        fig, axes = plt.subplots(1, 2, figsize=(13, 5))
        for ax, small in zip(axes, (True, False)):
            for name, rows in runs.items():
                series = sorted([r for r in rows if r['mode'] == 'random'
                                 and float(r['size_kib']) in plan['sizes_kib']
                                 and (float(r['size_kib']) <= 256) == small], key=lambda r: float(r['size_kib']))
                if not series:
                    continue
                x = [float(r['size_kib']) for r in series]
                line, = ax.plot(x, [float(r['median']) for r in series], 'o-' if name.startswith('repeat') else 's--',
                                markersize=4, label=name)
                ax.fill_between(x, [float(r['p5']) for r in series], [float(r['p95']) for r in series],
                                color=line.get_color(), alpha=.08)
                if len(series) == 1:
                    row = series[0]
                    median = float(row['median'])
                    ax.errorbar(x, [median], yerr=[[median - float(row['p5'])],
                                                  [float(row['p95']) - median]],
                                fmt='none', color=line.get_color(), capsize=3)
            ax.set(title='Small/control region' if small else 'Larger disputed region',
                   xlabel='Footprint (KiB)', ylabel='TSC ticks/access')
            ax.grid(False)
            ax.legend(fontsize=7)
        fig.suptitle(f"{host.capitalize()}, CPU {plan['selected']['cpu']}: randomized medians, separate runs\n"
                     'Shading: p5–p95 distributions, not confidence intervals; no pooling')
        fig.tight_layout()
        fig.savefig(output / f'{host}_comparison.pdf')
        fig.savefig(output / f'{host}_comparison.png', dpi=120)
        plt.close(fig)
    assert len(summaries) == 153
    assert sum(r['run'].startswith('repeat') for r in chunks) == 1440
    for name, rows in [('summaries', summaries), ('historical_comparison', comparisons),
                       ('repeat_spread', spreads), ('chunk_medians', chunks), ('activity', activity)]:
        write_csv(output / (name + '.csv'), rows)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'PASS: 153 diagnostic distributions, {len(comparisons)} historical comparisons, {len(chunks)} chunks')
    for row in spreads:
        if row['mode'] == 'random':
            print(row)


if __name__ == '__main__':
    main()
