"""Known-value arithmetic checks; no benchmarks or file changes."""
import math
from diagnostic_capacity_analysis import change, spread, key

assert math.isclose(change(125, 100), 25)
assert math.isclose(change(80, 100), -20)
assert math.isclose(spread([110, 100, 105]), 10)
assert spread([5, 5, 5]) == 0
assert key({'mode': 'random', 'size_kib': '32.0'}) == ('random', 32)
try:
    change(1, 0)
except ValueError:
    pass
else:
    raise AssertionError('Zero baseline must be rejected')
print('PASS: signed changes, repeat spread, numeric footprint matching, zero-baseline rejection')
