# Architecture-specific implementation

The implementation for this architecture is included in
[`../common/cache_capacity.c`](../common/cache_capacity.c), selected by the
`__x86_64__` or `__aarch64__` compilation branch. Build natively on the target host.
The one shared source avoids inconsistent duplicate implementations; retain both
branches in the final report's complete main-code listing. See the repository
README for the recorded native build/disassembly and data traceability.
