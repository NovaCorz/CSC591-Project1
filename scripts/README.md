# Capacity scripts

Restore the selected data layout with `restore_capacity_workspace.py`, then run
`capacity.py plot`, `capacity_overview.py`, and `capacity_refinement_analysis.py`
from that restored directory. The active manifest contains only the selected eight
full/refinement sets, and the overview uses Crux CPU 2. See the root README.

Collectors and snapshot code are preserved without rewriting measured kernels.
Historical diagnostic drivers/analyses remain as code only; running them requires
their excluded datasets from the original archive. They are not part of the
selected-data reproduction commands. `package_capacity.py` is the historical
import-all utility, not a command to apply to this already-curated checkout.

Python 3.9+ and NumPy/Matplotlib are needed for analysis. The restoration helper
uses only the standard library, refuses existing destinations, validates paths
and verifies checksums. `test_capacity_package.py` tests its safety without any
benchmark. `test_capacity.py` does execute a small benchmark and belongs only on
an authorized ECE compute host, never a Hazel/login node.
