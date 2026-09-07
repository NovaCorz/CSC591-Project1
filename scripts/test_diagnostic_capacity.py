"""Check diagnostic settings/activity calculations without running a benchmark."""
from pathlib import Path
from unittest.mock import patch
from diagnostic_capacity import SIZES, busy_percent, invocation


def main():
    assert busy_percent({2: (100, 70), 6: (100, 70)},
                        {2: (300, 270), 6: (300, 70)}) == {2: 0.0, 6: 100.0}
    assert sum(3 * (2 * len(sizes) + 1) for sizes in SIZES.values()) == 153
    for host, sizes in SIZES.items():
        assert sizes == sorted(set(sizes)) and all(n > 0 for n in sizes)
        with patch.object(Path, 'read_text', return_value='gcc -O0 saved-source'):
            args = invocation(Path('/source'), Path('/output'), host, 2)
        assert args[1] == '/source/capacity.py' and '--pilot' not in args
        for flag, value in [('--cpu', '2'), ('--samples', '1000000'), ('--steps', '4096'),
                            ('--spacing', '8'), ('--seed', '592'),
                            ('--binary', '/source/cache_capacity'), ('--out', '/output')]:
            assert args[args.index(flag) + 1] == value
        assert list(map(int, args[args.index('--sizes-kib') + 1:args.index('--build-command')])) == sizes
    print('PASS: quiet/busy calculation, fixed settings, planned sizes, saved binary/collector')


if __name__ == '__main__':
    main()
