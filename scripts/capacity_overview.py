"""Plot existing coarse summaries, keeping each machine's timer units separate.

    python3 capacity_overview.py
"""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    root = Path('results/capacity-20260906')
    hosts = ['sunbird', 'thunderbird', 'skylark', 'artemisia',
             'charnwood', 'crux', 'ookay', 'upgrade']
    fig, axes = plt.subplots(4, 2, figsize=(13, 15))
    for host, ax in zip(hosts, axes.flat):
        directory = (Path('results/crux-new-core-20260906T235055Z/crux')
                     if host == 'crux' else root / host)
        with (directory / 'full/summary.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 35 and all(int(r['samples']) == 1_000_000 for r in rows)
        for mode in ('random', 'sequential'):
            series = sorted([r for r in rows if r['mode'] == mode], key=lambda r: float(r['size_kib']))
            assert len(series) == 17
            x = [float(r['size_kib']) for r in series]
            ax.plot(x, [float(r['median']) for r in series], 'o-', markersize=3, label=mode)
            ax.fill_between(x, [float(r['p5']) for r in series],
                            [float(r['p95']) for r in series], alpha=.15)
        ax.set(xscale='log', yscale='log', title=host.capitalize(),
               xlabel='Working-set span (KiB)', ylabel=series[0]['unit'])
        ax.grid(False)
        ax.legend(fontsize=8)
    fig.suptitle('Timing-only coarse capacity sweeps: medians and 5th–95th percentiles\n'
                 'Independent timer units/scales; curves do not establish exact cache capacities', fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .96))
    fig.savefig(root / 'capacity_overview.pdf')
    fig.savefig(root / 'capacity_overview.png', dpi=130)
    plt.close(fig)


if __name__ == '__main__':
    main()
