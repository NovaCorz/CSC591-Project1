"""Compare saved capacity summaries without pooling runs or changing raw data.

Run after `python3 capacity.py plot DIRECTORY` for each full/refinement directory:
    python3 capacity_refinement_analysis.py
Requires the same NumPy/Matplotlib environment as capacity.py plot.
"""
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent
CAMPAIGN = ROOT / 'results/capacity-20260906'
CRUX = ROOT / 'results/crux-new-core-20260906T235055Z/crux'
GROUPS = ('small', 'middle', 'large')


def read_run(directory, sizes):
    assert (directory / 'COMPLETE').exists(), directory
    env = json.loads((directory / 'environment.json').read_text())
    args = env['arguments']
    assert not args['pilot']
    assert (args['samples'], args['steps'], args['spacing'], args['seed']) == (1000000, 4096, 8, 592)
    assert sorted(args['sizes_kib']) == sizes
    with (directory / 'summary.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    expected = {(mode, n) for mode in ('random', 'sequential') for n in sizes}
    expected.add(('empty', min(sizes)))
    assert len(rows) == len(expected)
    assert {(r['mode'], float(r['size_kib'])) for r in rows} == expected
    assert len(list(directory.glob('*.bin'))) == len(expected)
    for row in rows:
        mode, size = row['mode'], int(float(row['size_kib']))
        assert (int(row['samples']), int(row['steps']), int(row['spacing'])) == (1000000, 4096, 8)
        assert float(row['p5']) <= float(row['q1']) <= float(row['median']) <= float(row['q3']) <= float(row['p95'])
        assert float(row['stddev']) >= 0 and 0 <= int(row['outliers']) <= 1000000
        if mode != 'empty':
            assert int(row['zeros']) == 0 and float(row['median']) > 0
        stem = directory / f'{mode}_{size}KiB'
        meta = json.loads(stem.with_suffix('.json').read_text())
        assert meta['cpu'] == args['cpu'] and meta['bytes'] == size * 1024
        assert (meta['samples'], meta['steps'], meta['spacing'], meta['seed']) == (1000000, 4096, 8, 592)
        assert meta['mode'] == mode
        assert row['unit'] == meta['unit'] + ('/timer pair' if mode == 'empty' else '/access')
        assert stem.with_suffix('.bin').stat().st_size == 8000000
    return env, rows


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    plans = json.loads((ROOT / 'refinement_plan.json').read_text())
    output = CAMPAIGN / 'refinement-analysis'
    output.mkdir(exist_ok=True)
    all_rows, overlaps, manifest, runs = [], [], {}, {}
    for host, plan in plans.items():
        directory = CRUX if host == 'crux' else CAMPAIGN / host
        sizes = {'full': [2**i for i in range(2, 19)],
                 'small': plan['small_kib'], 'middle': plan['middle_kib'],
                 'large': [n * 1024 for n in plan['large_mib']]}
        full_env = None
        manifest[host] = {}
        for group, points in sizes.items():
            path = directory / ('full' if group == 'full' else 'refine-' + group)
            env, rows = read_run(path, points)
            if full_env is None:
                full_env = env
            assert env['hostname'] == full_env['hostname']
            assert env['arguments']['cpu'] == full_env['arguments']['cpu']
            assert env['binary_sha256'] == full_env['binary_sha256']
            assert env['source_sha256'] == full_env['source_sha256']
            manifest[host][group] = {'directory': str(path.relative_to(ROOT)),
                                   'cpu': env['arguments']['cpu'],
                                   'binary_sha256': env['binary_sha256'],
                                   'started_utc': env['started_utc'], 'points': len(rows)}
            runs[host, group] = rows
            all_rows.extend(dict(host=host, group=group, directory=str(path.relative_to(ROOT)), **r) for r in rows)
        coarse = {(r['mode'], r['size_kib']): r for r in runs[host, 'full'] if r['mode'] != 'empty'}
        for group in GROUPS:
            for row in runs[host, group]:
                key = row['mode'], row['size_kib']
                if key not in coarse:
                    continue
                old = coarse[key]
                assert old['unit'] == row['unit']
                delta = 100 * (float(row['median']) / float(old['median']) - 1)
                overlap = max(float(old['p5']), float(row['p5'])) <= min(float(old['p95']), float(row['p95']))
                record = dict(host=host, group=group, mode=row['mode'], size_kib=row['size_kib'],
                              unit=row['unit'], median_change_percent=delta,
                              percentile_bands_overlap=overlap)
                for field in ('mean', 'median', 'stddev', 'q1', 'q3', 'p5', 'p95', 'outliers', 'zeros'):
                    record['coarse_' + field] = old[field]
                    record['refinement_' + field] = row[field]
                overlaps.append(record)
    assert len(all_rows) == 918  # 280 coarse + 638 refinement distributions.
    write_csv(output / 'all_summaries.csv', all_rows)
    write_csv(output / 'overlap_comparison.csv', overlaps)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for group in GROUPS:
        fig, axes = plt.subplots(4, 2, figsize=(13, 15))
        for host, ax in zip(plans, axes.flat):
            dense = [r for r in runs[host, group] if r['mode'] == 'random']
            lo, hi = min(float(r['size_kib']) for r in dense), max(float(r['size_kib']) for r in dense)
            for label, series, color in (
                    ('coarse', [r for r in runs[host, 'full'] if r['mode'] == 'random' and lo <= float(r['size_kib']) <= hi], '0.4'),
                    ('refinement', dense, 'tab:blue')):
                series = sorted(series, key=lambda r: float(r['size_kib']))
                x = [float(r['size_kib']) for r in series]
                ax.plot(x, [float(r['median']) for r in series], 'o-' if label == 'refinement' else 's--',
                        color=color, markersize=3, label=label)
                ax.fill_between(x, [float(r['p5']) for r in series], [float(r['p95']) for r in series], color=color, alpha=.12)
            ax.set(title=f"{host.capitalize()} — CPU {manifest[host][group]['cpu']}",
                   xlabel='Working-set span (KiB)', ylabel=dense[0]['unit'])
            ax.grid(False)
            ax.legend(fontsize=8)
        fig.suptitle(f'{group.capitalize()} region: randomized traversal, separate runs\n'
                     'Medians and 5th–95th percentile distributions (not confidence intervals); independent axes', fontsize=12)
        fig.tight_layout(rect=(0, 0, 1, .96))
        fig.savefig(output / f'{group}_comparison.pdf')
        fig.savefig(output / f'{group}_comparison.png', dpi=120)
        plt.close(fig)
    print(f'Validated {len(all_rows)} distributions; wrote {len(overlaps)} overlap comparisons to {output}')
    for host in plans:
        rows = [r for r in overlaps if r['host'] == host and r['mode'] == 'random']
        worst = max(rows, key=lambda r: abs(r['median_change_percent']))
        print(host, f"{sum(abs(r['median_change_percent']) <= 5 for r in rows)}/{len(rows)} within 5%; "
              f"largest median shift {worst['median_change_percent']:+.2f}% at {worst['size_kib']} KiB")


if __name__ == '__main__':
    main()
