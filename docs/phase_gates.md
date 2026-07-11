# Phase Gates Verify Commands

| Phase | Verify Command (`tests/phase_gates/verify_phase_*.py`) | Description |
|---|---|---|
| Phase 1 | `python -m pytest tests/phase_gates/verify_phase_01.py` | Verify shared library models can be serialized/deserialized |
| Phase 2 | `python tests/phase_gates/verify_phase_02.py` | Check `docker-compose up` status and mosquitto roundtrip |
| Phase 3 | `python tests/phase_gates/verify_phase_03.py` | Register fake device, edit config, assert config-update MQTT message |
| Phase 4 | `python tests/phase_gates/verify_phase_04.py` | MQTT client reconnects on broker bounce, last-will message delivery |
| Phase 5 | `python tests/phase_gates/verify_phase_05.py` | Room Connector logs unlock command and emergency override |
| Phase 6 | `python tests/phase_gates/verify_phase_06.py` | Badge connector emits position, battery, heartbeat, safety topics |
| Phase 7 | `python tests/phase_gates/verify_phase_07.py` | Prop connector emits interaction, health, heartbeat topics |
| Phase 8 | `python tests/phase_gates/verify_phase_08.py` | Synthetic fall event triggers emergency unlock and system alerts |
| Phase 9 | `python tests/phase_gates/verify_phase_09.py` | FSM demo strategy runs to completion; hot-swaps config mid-run |
| Phase 10 | `python tests/phase_gates/verify_phase_10.py` | TimeSeriesDB persists telemetry and retrieves via `/events` REST API |
| Phase 11 | `python tests/phase_gates/verify_phase_11.py` | Analytics Engine generates consistent output across restarts |
| Phase 12 | `python tests/phase_gates/verify_phase_12.py` | ThingSpeak Adapter serves local `/history` without talking to internet |
| Phase 13 | `python tests/phase_gates/verify_phase_13.py` | Telegram Bot responds in <1s with status; manual commands hit bus |
| Phase 14 | `python tests/phase_gates/verify_phase_14.py` | Node-RED dashboard widget refresh logic |
| Phase 15 | `python tests/phase_gates/verify_phase_15.py` | End-to-end integration: 2 rooms concurrently with no data leakage |
| Phase 16 | `python tests/phase_gates/verify_phase_16.py` | Full test suite execution and stress metrics validation |
