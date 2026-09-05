import './style.css';

const API = '/api';
const model = {
  definitions: {},
  strategies: {},
  rooms: {},
  presence: {},
  alerts: [],
  history: {},
  heatmaps: {},
};

const elements = {
  rooms: document.querySelector('#rooms-grid'),
  alerts: document.querySelector('#alert-center'),
  presence: document.querySelector('#presence-grid'),
  log: document.querySelector('#event-log'),
  connection: document.querySelector('#connection-state'),
  period: document.querySelector('#period-select'),
  center: document.querySelector('#center-kpis'),
  safety: document.querySelector('#safety-kpis'),
  bottlenecks: document.querySelector('#bottlenecks'),
  maintenance: document.querySelector('#maintenance'),
};

let renderQueued = false;

function create(tag, className = '', text = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== '') element.textContent = String(text);
  return element;
}

async function getJson(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${response.status}: ${message || response.statusText}`);
  }
  return response.json();
}

function scheduleRender() {
  if (renderQueued) return;
  renderQueued = true;
  window.requestAnimationFrame(() => {
    renderQueued = false;
    renderRooms();
    renderPresence();
    renderAlerts();
  });
}

function logEvent(message, kind = 'info') {
  const item = create('li', kind);
  const timestamp = create('time', '', new Date().toLocaleTimeString());
  item.append(timestamp, document.createTextNode(message));
  elements.log.prepend(item);
  while (elements.log.children.length > 100) elements.log.lastElementChild.remove();
}

function mergeSnapshot(snapshot) {
  if (!snapshot) return;
  model.rooms = snapshot.rooms || model.rooms;
  model.presence = snapshot.presence || model.presence;
  model.alerts = snapshot.alerts || model.alerts;
  scheduleRender();
}

function handleLiveEvent(event) {
  const message = JSON.parse(event.data);
  const { room_id: roomId, event_type: eventType, decoded, topic } = message;
  if (topic.startsWith('status/')) {
    model.presence[topic.split('/')[1]] = decoded;
  } else if (topic === 'system/alerts') {
    model.alerts.unshift(decoded);
    model.alerts = model.alerts.slice(0, 50);
    logEvent(` CRITICAL ${decoded.room_id}: ${decoded.message}`, 'critical');
  } else if (roomId && model.rooms[roomId]) {
    const room = model.rooms[roomId];
    const parts = topic.split('/');
    if (eventType === 'environment') room.environment = { ...decoded, timestamp: message.received_at };
    if (eventType.startsWith('badge_')) {
      const badgeId = parts[3];
      room.badges[badgeId] = { ...(room.badges[badgeId] || {}), ...decoded, timestamp: message.received_at };
    }
    if (eventType.startsWith('prop_')) {
      const propId = parts[3];
      room.props[propId] = { ...(room.props[propId] || {}), ...decoded, timestamp: message.received_at };
    }
    if (eventType === 'game_status') room.status = decoded;
    if (eventType === 'game_transition') {
      room.last_transition = decoded;
      logEvent(` ${roomId}: ${decoded.from_state} → ${decoded.to_state} (${decoded.trigger})`, 'transition');
    }
  }
  scheduleRender();
}

function connectLiveStream() {
  const stream = new EventSource(`${API}/stream`);
  stream.addEventListener('snapshot', (event) => mergeSnapshot(JSON.parse(event.data)));
  stream.addEventListener('mqtt', handleLiveEvent);
  stream.onopen = () => {
    elements.connection.className = 'connection online';
    elements.connection.lastChild.textContent = 'Live SSE connected';
    logEvent(' Live Server-Sent Events channel connected.', 'success');
  };
  stream.onerror = () => {
    elements.connection.className = 'connection offline';
    elements.connection.lastChild.textContent = 'Reconnecting live stream';
  };
}

function metric(label, value, unit = '') {
  const wrapper = create('div', 'metric');
  wrapper.append(create('strong', '', `${value}${unit}`), create('span', '', label));
  return wrapper;
}

function roomStrategyProps(strategy) {
  const props = new Map();
  Object.values(strategy?.states || {}).forEach((state) => {
    (state.transitions || []).forEach((transition) => {
      if (transition.trigger === 'event') {
        props.set(transition.prop_id, {
          prop_id: transition.prop_id,
          interaction_type: transition.interaction_type,
          value: String(transition.value),
        });
      }
    });
  });
  return [...props.values()];
}

function commandButton(label, command, roomId, className = '') {
  const button = create('button', `command-button ${className}`, label);
  button.dataset.command = command;
  button.dataset.room = roomId;
  return button;
}

function renderRooms() {
  const fragment = document.createDocumentFragment();
  Object.entries(model.definitions).forEach(([roomId, definition]) => {
    const live = model.rooms[roomId] || { badges: {}, props: {} };
    const status = live.status || {};
    const environment = live.environment || {};
    const card = create('article', 'room-card');

    const heading = create('header', 'room-heading');
    const title = create('div');
    title.append(create('p', 'eyebrow', definition.theme), create('h2', '', definition.name));
    const state = create('div', `state-pill ${status.completed ? 'completed' : ''}`, status.current_state || 'Waiting for FSM');
    heading.append(title, state);

    const environmentGrid = create('div', 'environment-grid');
    environmentGrid.append(
      metric('Temperature', environment.temperature?.toFixed?.(1) ?? '—', ' °C'),
      metric('Humidity', environment.humidity?.toFixed?.(1) ?? '—', ' %'),
      metric('CO₂', environment.co2?.toFixed?.(0) ?? '—', ' ppm'),
      metric('VOC', environment.voc?.toFixed?.(2) ?? '—', ' mg/m³'),
    );

    const workflow = create('div', 'workflow');
    Object.keys(model.strategies[roomId]?.states || {}).forEach((stateName) => {
      workflow.append(create('span', stateName === status.current_state ? 'active' : '', stateName));
    });

    const people = create('section', 'room-subpanel');
    people.append(create('h3', '', 'Live player badges'));
    const badgeList = create('div', 'badge-list');
    Object.entries(live.badges || {}).forEach(([badgeId, badgeState]) => {
      const badgeRow = create('div', 'badge-row');
      badgeRow.append(
        create('strong', '', badgeId),
        create('span', '', `x ${Number(badgeState.x || 0).toFixed(1)} m · y ${Number(badgeState.y || 0).toFixed(1)} m`),
        create('span', badgeState.battery < 20 ? 'low' : '', `${Number(badgeState.battery || 0).toFixed(0)}% battery`),
      );
      badgeList.append(badgeRow);
    });
    if (!badgeList.children.length) badgeList.append(create('p', 'muted', 'Waiting for badge telemetry…'));
    people.append(badgeList);

    const controls = create('section', 'room-subpanel controls');
    controls.append(create('h3', '', 'Game Master controls'));
    const buttonRow = create('div', 'button-row');
    buttonRow.append(
      commandButton('Unlock door', 'unlock', roomId, 'primary'),
      commandButton('Lock door', 'lock', roomId),
      commandButton('Reset session', 'reset', roomId, 'warning'),
    );
    controls.append(buttonRow);

    const propRow = create('div', 'control-row');
    const propSelect = create('select');
    propSelect.dataset.propSelect = roomId;
    roomStrategyProps(model.strategies[roomId]).forEach((item) => {
      const option = create('option', '', `${item.prop_id}: ${item.interaction_type} = ${item.value}`);
      option.value = JSON.stringify(item);
      propSelect.append(option);
    });
    const trigger = commandButton('Trigger selected prop', 'trigger_prop', roomId, 'accent');
    propRow.append(propSelect, trigger);
    controls.append(propRow);

    const effects = create('div', 'control-row');
    const light = create('select');
    light.dataset.lightSelect = roomId;
    ['vault_blue', 'mansion_dim', 'warning_amber', 'success_green', 'emergency_white'].forEach((color) => {
      const option = create('option', '', color);
      option.value = color;
      light.append(option);
    });
    effects.append(light, commandButton('Set lights', 'set_lights', roomId));
    const track = create('input');
    track.dataset.audioInput = roomId;
    track.value = 'operator_message.mp3';
    track.setAttribute('aria-label', 'Audio track');
    effects.append(track, commandButton('Play audio', 'play_audio', roomId));
    controls.append(effects);

    const visuals = create('div', 'visual-grid');
    const historyPanel = create('section', 'room-subpanel');
    historyPanel.append(create('h3', '', 'Environment history'));
    const historyCanvas = create('canvas');
    historyCanvas.dataset.history = roomId;
    historyPanel.append(historyCanvas);
    const heatmapPanel = create('section', 'room-subpanel');
    heatmapPanel.append(create('h3', '', 'Player heatmap and latest positions'));
    const heatmapCanvas = create('canvas');
    heatmapCanvas.dataset.heatmap = roomId;
    heatmapPanel.append(heatmapCanvas);
    visuals.append(historyPanel, heatmapPanel);

    card.append(heading, environmentGrid, workflow, people, controls, visuals);
    fragment.append(card);
  });
  elements.rooms.replaceChildren(fragment);
  window.requestAnimationFrame(drawRoomVisuals);
}

function prepareCanvas(canvas, height = 180) {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(280, canvas.clientWidth);
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const context = canvas.getContext('2d');
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

function drawHistory(canvas, history) {
  const { context, width, height } = prepareCanvas(canvas);
  context.clearRect(0, 0, width, height);
  context.fillStyle = '#0d111b';
  context.fillRect(0, 0, width, height);
  const points = history || [];
  if (points.length < 2) {
    context.fillStyle = '#8792a6';
    context.fillText('Historical samples will appear here', 16, 28);
    return;
  }
  const plot = (key, color) => {
    const values = points.map((point) => Number(point[key])).filter(Number.isFinite);
    if (values.length < 2) return;
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const span = maximum - minimum || 1;
    context.beginPath();
    context.strokeStyle = color;
    context.lineWidth = 2;
    values.forEach((value, index) => {
      const x = 12 + (index / (values.length - 1)) * (width - 24);
      const y = height - 16 - ((value - minimum) / span) * (height - 32);
      if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
    });
    context.stroke();
  };
  plot('temperature', '#23d5ff');
  plot('humidity', '#a970ff');
}

function drawHeatmap(canvas, heatmap) {
  const { context, width, height } = prepareCanvas(canvas);
  context.fillStyle = '#0d111b';
  context.fillRect(0, 0, width, height);
  if (!heatmap?.cells) {
    context.fillStyle = '#8792a6';
    context.fillText('Position samples will appear here', 16, 28);
    return;
  }
  const rows = heatmap.cells.length;
  const columns = heatmap.cells[0]?.length || 1;
  const max = Math.max(1, ...heatmap.cells.flat());
  const cellWidth = width / columns;
  const cellHeight = height / rows;
  heatmap.cells.forEach((row, rowIndex) => row.forEach((count, columnIndex) => {
    const intensity = count / max;
    context.fillStyle = `rgba(35, 213, 255, ${0.05 + intensity * 0.75})`;
    context.fillRect(columnIndex * cellWidth, rowIndex * cellHeight, cellWidth - 1, cellHeight - 1);
  }));
  (heatmap.latest_positions || []).forEach((point) => {
    const x = (point.x / heatmap.dimensions.width_m) * width;
    const y = (point.y / heatmap.dimensions.height_m) * height;
    context.beginPath();
    context.fillStyle = '#ffcf4a';
    context.arc(x, y, 5, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = '#ffffff';
    context.fillText(point.badge_id, x + 8, y + 4);
  });
}

function drawRoomVisuals() {
  document.querySelectorAll('canvas[data-history]').forEach((canvas) => drawHistory(canvas, model.history[canvas.dataset.history]));
  document.querySelectorAll('canvas[data-heatmap]').forEach((canvas) => drawHeatmap(canvas, model.heatmaps[canvas.dataset.heatmap]));
}

function renderAlerts() {
  elements.alerts.replaceChildren();
  const active = model.alerts.slice(0, 3);
  elements.alerts.hidden = active.length === 0;
  active.forEach((alert) => {
    const item = create('div', 'alert-item');
    item.append(create('strong', '', `${alert.severity || 'critical'} · ${alert.room_id}`), create('span', '', alert.message));
    elements.alerts.append(item);
  });
}

function renderPresence() {
  const fragment = document.createDocumentFragment();
  Object.entries(model.presence).sort(([a], [b]) => a.localeCompare(b)).forEach(([name, data]) => {
    const online = data.status === 'online';
    const card = create('article', `presence-card ${online ? 'online' : 'offline'}`);
    card.append(
      create('strong', '', name),
      create('span', 'presence-state', online ? 'ONLINE' : String(data.status || 'UNKNOWN').toUpperCase()),
      create('small', '', data.timestamp ? `Last seen ${new Date(data.timestamp * 1000).toLocaleTimeString()}` : 'No timestamp'),
    );
    fragment.append(card);
  });
  if (!fragment.children?.length && !Object.keys(model.presence).length) fragment.append(create('p', 'loading', 'Waiting for service heartbeats…'));
  elements.presence.replaceChildren(fragment);
}

async function sendCommand(roomId, command) {
  const payload = { room_id: roomId, command };
  if (command === 'trigger_prop') {
    const select = document.querySelector(`select[data-prop-select="${roomId}"]`);
    if (!select?.value) throw new Error('No configured prop transition');
    Object.assign(payload, JSON.parse(select.value));
  }
  if (command === 'set_lights') payload.color = document.querySelector(`select[data-light-select="${roomId}"]`).value;
  if (command === 'play_audio') payload.track = document.querySelector(`input[data-audio-input="${roomId}"]`).value;
  const result = await getJson(`${API}/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  logEvent(` ${roomId}: accepted ${command} on ${result.topic}`, 'command');
}

async function refreshHistorical() {
  const period = elements.period.value;
  const roomIds = Object.keys(model.definitions);
  await Promise.all(roomIds.flatMap((roomId) => [
    getJson(`${API}/stats/history?room_id=${encodeURIComponent(roomId)}&period=${period}&limit=300`)
      .then((data) => { model.history[roomId] = data.history; }),
    getJson(`${API}/stats/heatmap?room_id=${encodeURIComponent(roomId)}&period=${period}`)
      .then((data) => { model.heatmaps[roomId] = data; }),
  ]));
  await refreshAnalytics();
  scheduleRender();
}

function renderMetricSet(container, metrics) {
  const fragment = document.createDocumentFragment();
  metrics.forEach(([label, value, unit]) => fragment.append(metric(label, value, unit)));
  container.replaceChildren(fragment);
}

async function refreshAnalytics() {
  const period = elements.period.value;
  const [center, safety, bottlenecks, maintenance] = await Promise.all([
    getJson(`${API}/stats/game_center?period=${period}`),
    getJson(`${API}/stats/safety?period=${period}`),
    getJson(`${API}/stats/bottlenecks?period=${period}`),
    getJson(`${API}/stats/maintenance?period=${period}`),
  ]);
  renderMetricSet(elements.center, [
    ['Sessions', center.kpis.total_sessions, ''],
    ['Completion rate', center.kpis.completion_rate_percent, '%'],
    ['Average duration', Math.round(center.kpis.overall_avg_duration_seconds / 60), ' min'],
    ['Estimated throughput', center.kpis.estimated_players_per_hour, ' players/h'],
  ]);
  renderMetricSet(elements.safety, [
    ['Safety index', safety.safety_score_percent, '%'],
    ['Comfort samples', safety.environment_samples, ''],
    ['Critical alerts', safety.total_alerts, ''],
  ]);

  const table = create('table');
  const head = create('tr');
  ['Room', 'Puzzle/state', 'Samples', 'Average', 'Maximum'].forEach((label) => head.append(create('th', '', label)));
  table.append(head);
  (bottlenecks.bottlenecks || []).forEach((entry) => {
    const row = create('tr');
    [entry.room_id, entry.puzzle, entry.samples, `${entry.avg_solve_seconds}s`, `${entry.max_solve_seconds}s`]
      .forEach((value) => row.append(create('td', '', value)));
    table.append(row);
  });
  if ((bottlenecks.bottlenecks || []).length) elements.bottlenecks.replaceChildren(table);
  else elements.bottlenecks.replaceChildren(create('p', 'muted', 'Complete a room to calculate historical solve-time bottlenecks.'));

  const warnings = maintenance.maintenance_required || [];
  if (!warnings.length) elements.maintenance.replaceChildren(create('p', 'healthy', 'All reporting badges and props are healthy.'));
  else {
    const list = create('ul');
    warnings.forEach((warning) => list.append(create('li', '', `${warning.component_id}: ${warning.reason} (${warning.value})`)));
    elements.maintenance.replaceChildren(list);
  }
}

async function initialize() {
  try {
    const roomResponse = await getJson(`${API}/rooms`);
    roomResponse.rooms.forEach((room) => {
      model.definitions[room.room_id] = room;
      model.rooms[room.room_id] = { definition: room, status: null, environment: null, badges: {}, props: {} };
    });
    await Promise.all(roomResponse.rooms.map(async (room) => {
      model.strategies[room.room_id] = await getJson(`${API}/strategy/${room.room_id}`);
    }));
    mergeSnapshot(await getJson(`${API}/status`));
    connectLiveStream();
    await refreshHistorical();
  } catch (error) {
    logEvent(` Dashboard initialization failed: ${error.message}`, 'critical');
    elements.rooms.replaceChildren(create('p', 'error-message', `Dashboard unavailable: ${error.message}`));
  }
}

document.addEventListener('click', async (event) => {
  const commandTarget = event.target.closest('button[data-command]');
  if (commandTarget) {
    commandTarget.disabled = true;
    try {
      await sendCommand(commandTarget.dataset.room, commandTarget.dataset.command);
    } catch (error) {
      logEvent(` Command failed: ${error.message}`, 'critical');
    } finally {
      commandTarget.disabled = false;
    }
  }
});

document.querySelectorAll('.tab').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach((item) => item.classList.toggle('active', item === button));
  document.querySelectorAll('.tab-panel').forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${button.dataset.tab}`));
  window.requestAnimationFrame(drawRoomVisuals);
}));

elements.period.addEventListener('change', () => refreshHistorical().catch((error) => logEvent(` Analytics refresh failed: ${error.message}`, 'critical')));
document.querySelector('#clear-log').addEventListener('click', () => elements.log.replaceChildren());
document.querySelector('#reset-database').addEventListener('click', async () => {
  if (!window.confirm('Reset all historical demo events? Live services will immediately start filling the database again.')) return;
  try {
    await getJson(`${API}/stats/reset`, { method: 'POST' });
    model.history = {};
    model.heatmaps = {};
    await refreshHistorical();
    logEvent(' Historical database reset completed.', 'success');
  } catch (error) {
    logEvent(` Database reset failed: ${error.message}`, 'critical');
  }
});

window.addEventListener('resize', () => window.requestAnimationFrame(drawRoomVisuals));
initialize();
window.setInterval(() => refreshHistorical().catch((error) => logEvent(` Analytics refresh failed: ${error.message}`, 'critical')), 15000);

