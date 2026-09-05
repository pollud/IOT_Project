# Phase-gate verification

The former phase scripts only checked HTTP acknowledgements and contained several
non-failing assertions. They have been replaced by two executable layers:

1. `python -m pytest` validates shared contracts, SenML, FSM behavior and recovery,
   Catalog CRUD/correlation, SQLite isolation, analytics math and dashboard caching.
2. `python tests/integration/verify_stack.py` validates the running Docker stack,
   including two-room isolation, real MQTT delivery, FSM completion, persistence,
   analytics, SSE delivery and the independent safety override.

These commands are also available as `make test` and `make verify`.

