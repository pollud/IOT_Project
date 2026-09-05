# Verification gates

| Area | Deterministic gate |
| --- | --- |
| Shared library | SenML encode/decode and canonical topic unit tests |
| Catalog | CRUD, duplicate handling, persistence and room/device correlation tests |
| MQTT | unique client IDs, QoS contract, retained FSM/config/presence topics |
| Environment | natural temperature/humidity/CO2/VOC SenML observed |
| Badges | natural position/battery/heartbeat plus forced safety event observed |
| Props | configured health/heartbeat and exact interaction observed |
| Safety | fall produces both alert and room-specific actuator override |
| Room Control | two strategies validate; event/timed transitions and recovery tested |
| TimeSeries | filters, ordering, pagination, prune, reset and queue drain tested |
| Analytics | known fixture produces exact session/environment/heatmap/bottleneck math |
| Dashboard | SenML live cache, real SSE event, controls, alert banner and proxies tested |
| Multi-room | completing room1 leaves reset room2 in its independent initial state |

Run static/unit gates:

```bash
python -m pytest
ruff check .
npm --prefix services/web_dashboard run build
```

Run the observable full-stack gate:

```bash
docker compose up --build -d
python tests/integration/verify_stack.py
```

The integration gate requires downstream evidence. For example, a successful
Dashboard HTTP response is insufficient: the test waits for the resulting FSM
state, persisted session, Analytics result and SSE event.

