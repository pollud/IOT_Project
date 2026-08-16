/**
 * Main Web Dashboard Application Script handling state management, SSE live telemetry streams, Chart.js graphs, and interactive room control.
 */

import './style.css'

const roomsWrapper = document.getElementById('rooms-wrapper');
const presenceWrapper = document.getElementById('presence-wrapper');
const periodSelect = document.getElementById('time-period');
const btnResetDb = document.getElementById('btn-reset-db');
const terminalLog = document.getElementById('terminal-log');

const API_BASE = 'http://localhost:8087/api';

let roomsState = {};
let roomCharts = {};
let lastKnownStates = {};

// Tab Navigation Logic
document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    
    tab.classList.add('active');
    const targetId = tab.getAttribute('data-tab');
    document.getElementById(targetId).classList.add('active');

    if (targetId === 'analytics-tab') {
      fetchAnalyticsData();
    } else if (targetId === 'presence-tab') {
      fetchPresenceData();
    }
  });
});

/**
 * Append a formatted log entry line to the terminal UI panel.
 * 
 * @param {string} message - Message text or HTML string.
 * @param {string} [type='system'] - Log category CSS class.
 */
function logToTerminal(message, type = 'system') {
  const timestamp = new Date().toLocaleTimeString();
  const logLine = document.createElement('div');
  logLine.className = `log-line ${type}`;
  logLine.innerHTML = `[${timestamp}] ${message}`;
  terminalLog.appendChild(logLine);
  terminalLog.scrollTop = terminalLog.scrollHeight;
}

/**
 * Get the currently selected timeframe period filter.
 * 
 * @returns {string} Selected period string ("1h", "24h", "7d", or "all").
 */
function getSelectedPeriod() {
  return periodSelect.value;
}

/**
 * Fetch status of all game rooms from the web dashboard API and update UI panels.
 */
async function fetchStatus() {
  try {
    const res = await fetch(`${API_BASE}/status`);
    const data = await res.json();
    
    for (const [roomId, status] of Object.entries(data)) {
      if (!roomsState[roomId]) {
        roomsState[roomId] = { status, env: null, stats: null, strategy: null };
        lastKnownStates[roomId] = status.current_state;
        
        await fetchRoomStrategy(roomId);
        renderRoomPanel(roomId);
        initRoomChart(roomId);
        await updateRoomData(roomId);
      } else {
        const oldState = lastKnownStates[roomId];
        const newState = status.current_state;
        
        roomsState[roomId].status = status;
        
        if (oldState !== newState) {
          lastKnownStates[roomId] = newState;
          logToTerminal(`🚪 <b>[${roomId}]</b> FSM Transition: <span style="color:#00d2ff">${oldState}</span> ➡️ <span style="color:#00e676">${newState}</span>`, 'state-change');
          await updateRoomData(roomId);
        }
        
        updateRoomDOM(roomId);
      }
    }
  } catch (err) {
    console.error('Failed to fetch status', err);
  }
}

/**
 * Fetch FSM strategy configuration for a room from catalog API.
 * 
 * @param {string} roomId - Room identifier.
 */
async function fetchRoomStrategy(roomId) {
  try {
    const res = await fetch(`${API_BASE}/strategy/${roomId}`);
    if (res.ok) {
      roomsState[roomId].strategy = await res.json();
    }
  } catch (err) {
    console.error(`Failed to fetch strategy for ${roomId}`, err);
  }
}

/**
 * Fetch analytics stats, environmental telemetry, and chart history for a room.
 * 
 * @param {string} roomId - Room identifier.
 */
async function updateRoomData(roomId) {
  const period = getSelectedPeriod();
  try {
    const statsRes = await fetch(`${API_BASE}/stats/room/${roomId}?period=${period}`);
    if (statsRes.ok) {
      roomsState[roomId].stats = await statsRes.json();
    }
    
    const envRes = await fetch(`${API_BASE}/stats/environment/${roomId}?period=${period}`);
    if (envRes.ok) {
      roomsState[roomId].env = await envRes.json();
    }
    
    const historyRes = await fetch(`${API_BASE}/stats/history/${roomId}?period=${period}`);
    if (historyRes.ok) {
      const historyData = await historyRes.json();
      updateChart(roomId, historyData.history || []);
    }
    
    updateRoomDOM(roomId);
  } catch (err) {
    console.error(`Error loading data for ${roomId}`, err);
  }
}

/**
 * Render the complete room card panel container with interactive controls and stats cards into DOM.
 * 
 * @param {string} roomId - Room identifier.
 */
function renderRoomPanel(roomId) {
  const data = roomsState[roomId];
  const strategyName = data.strategy ? data.strategy.name || data.strategy.version : 'Custom Game';
  
  let stepsHtml = '';
  let propsOptions = '<option value="prop1">default_prop</option>';
  
  if (data.strategy && data.strategy.states) {
    stepsHtml = Object.keys(data.strategy.states)
      .map(state => `<span class="fsm-step" id="step-${roomId}-${state}">${state}</span>`)
      .join('');

    // Extract prop IDs from strategy definition
    const propSet = new Set();
    Object.values(data.strategy.states).forEach(st => {
      (st.transitions || []).forEach(tr => {
        if (tr.prop_id) propSet.add(tr.prop_id);
      });
    });
    if (propSet.size > 0) {
      propsOptions = Array.from(propSet).map(p => `<option value="${p}">${p}</option>`).join('');
    }
  }

  const html = `
    <div class="room-panel" id="panel-${roomId}">
      <div class="room-info">
        <div>
          <h2>${roomId}</h2>
          <span class="strategy-label">STRATEGY: ${strategyName}</span>
        </div>
        <div class="room-actions">
          <button class="btn btn-open" onclick="sendCommand('${roomId}', 'unlockDoor')">🔓 Unlock</button>
          <button class="btn btn-reset" onclick="sendCommand('${roomId}', 'reset')">🔄 Reset</button>
        </div>
      </div>
      
      <div class="room-state-banner">
        <div>FSM STATE: <span class="state-text" id="state-${roomId}">--</span></div>
        <span class="door-tag" id="lock-${roomId}">LOCKED</span>
      </div>

      <div class="fsm-tracker-container">
        <div class="fsm-tracker-title">Visual Puzzle Workflow</div>
        <div class="fsm-steps">${stepsHtml}</div>
      </div>

      <!-- INTERACTIVE ROOM CONTROLS -->
      <div class="interactive-controls-container">
        <div class="control-box">
          <div class="control-box-title">🕹️ Prop Control</div>
          <div class="control-row">
            <select id="prop-id-${roomId}">${propsOptions}</select>
            <select id="prop-type-${roomId}">
              <option value="keypad">Keypad</option>
              <option value="rfid">RFID Tag</option>
              <option value="button">Button</option>
              <option value="capacitive">Capacitive</option>
            </select>
            <input type="text" id="prop-val-${roomId}" placeholder="Value..." value="pressed" />
            <button class="btn btn-action" onclick="triggerProp('${roomId}')">Trigger</button>
          </div>
        </div>

        <div class="control-box">
          <div class="control-box-title">🔊 Audio Speaker</div>
          <div class="control-row">
            <select id="audio-track-${roomId}">
              <option value="ambient.mp3">Ambient Theme</option>
              <option value="hack_success.mp3">Hack Success</option>
              <option value="siren_alert.mp3">Siren Alert</option>
              <option value="magic_chime.mp3">Magic Chime</option>
              <option value="whispers.mp3">Spooky Whispers</option>
              <option value="boss_battle.mp3">Boss Battle</option>
            </select>
            <button class="btn btn-action" onclick="playAudio('${roomId}')">Play Sound</button>
          </div>
        </div>

        <div class="control-box">
          <div class="control-box-title">💡 Ambiance Lighting</div>
          <div class="control-row">
            <select id="light-color-${roomId}">
              <option value="cyan">Cyan</option>
              <option value="purple">Purple</option>
              <option value="red">Red Warning</option>
              <option value="green">Matrix Green</option>
              <option value="orange">Dungeon Orange</option>
              <option value="dark_red">Horror Dark Red</option>
              <option value="strobe">Strobe Light</option>
              <option value="warm_yellow">Warm Yellow</option>
            </select>
            <button class="btn btn-action" onclick="setLights('${roomId}')">Apply Light</button>
          </div>
        </div>
      </div>

      <div class="room-details-grid">
        <div class="chart-container">
          <div class="chart-title">Solved Stats</div>
          <div style="display:flex; flex-direction:column; justify-content:center; align-items:center; height:100%;">
            <div style="font-size:1.8rem; font-weight:800;" id="solve-time-${roomId}">--</div>
            <div style="font-size:0.8rem; color:var(--text-muted);">Avg Solve Time</div>
            <div style="font-size:1.1rem; font-weight:700; margin-top:0.5rem;" id="total-sessions-${roomId}">--</div>
            <div style="font-size:0.7rem; color:var(--text-muted);">Total Sessions</div>
          </div>
        </div>

        <div class="chart-container">
          <div class="chart-title">Temp & Humidity Trends</div>
          <canvas id="chart-canvas-${roomId}" style="max-height:140px;"></canvas>
        </div>
      </div>
    </div>
  `;
  
  roomsWrapper.insertAdjacentHTML('beforeend', html);
}

/**
 * Update DOM elements for a room panel (state text, lock tag, active step highlight, solve stats).
 * 
 * @param {string} roomId - Room identifier.
 */
function updateRoomDOM(roomId) {
  const data = roomsState[roomId];
  const stateEl = document.getElementById(`state-${roomId}`);
  const lockEl = document.getElementById(`lock-${roomId}`);
  
  const solveTimeEl = document.getElementById(`solve-time-${roomId}`);
  const totalSessionsEl = document.getElementById(`total-sessions-${roomId}`);

  const currentState = data.status ? (data.status.current_state || 'entrance') : 'entrance';
  if (stateEl) stateEl.textContent = currentState;
  
  if (lockEl) {
    const isLocked = currentState !== 'game_cleared' && currentState !== 'core_unlocked' && currentState !== 'champion_cleared' && currentState !== 'case_solved';
    lockEl.textContent = isLocked ? 'LOCKED' : 'UNLOCKED';
    lockEl.className = `door-tag ${isLocked ? 'locked' : 'unlocked'}`;
  }
  
  if (data.strategy && data.strategy.states) {
    Object.keys(data.strategy.states).forEach(state => {
      const stepEl = document.getElementById(`step-${roomId}-${state}`);
      if (stepEl) {
        stepEl.className = 'fsm-step';
        if (state === currentState) {
          stepEl.classList.add('active');
        }
      }
    });
  }

  if (solveTimeEl && data.stats) {
    const avgTime = typeof data.stats.avg_solve_time === 'number' && data.stats.avg_solve_time > 0
      ? (data.stats.avg_solve_time / 60).toFixed(1) + 'm'
      : '--';
    solveTimeEl.textContent = avgTime;
  }
  
  if (totalSessionsEl && data.stats) {
    totalSessionsEl.textContent = data.stats.total_sessions || '0';
  }
}

/**
 * Initialize Chart.js line graph canvas for environmental trends.
 * 
 * @param {string} roomId - Room identifier.
 */
function initRoomChart(roomId) {
  const canvas = document.getElementById(`chart-canvas-${roomId}`);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  roomCharts[roomId] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'Temp (°C)',
          data: [],
          borderColor: '#00d2ff',
          backgroundColor: 'rgba(0, 210, 255, 0.1)',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3
        },
        {
          label: 'Hum (%)',
          data: [],
          borderColor: '#9d4edd',
          backgroundColor: 'rgba(157, 78, 221, 0.1)',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { 
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#838396', font: { size: 9 } }
        }
      }
    }
  });
}

/**
 * Update Chart.js dataset with new historical data points.
 * 
 * @param {string} roomId - Room identifier.
 * @param {Array<Object>} history - Environmental history data points.
 */
function updateChart(roomId, history) {
  const chart = roomCharts[roomId];
  if (!chart) return;
  
  const maxPoints = 30;
  const skip = Math.max(1, Math.floor(history.length / maxPoints));
  const sampledHistory = history.filter((_, idx) => idx % skip === 0);

  chart.data.labels = sampledHistory.map(pt => pt.timestamp);
  chart.data.datasets[0].data = sampledHistory.map(pt => pt.temperature);
  chart.data.datasets[1].data = sampledHistory.map(pt => pt.humidity);
  chart.update();
}

/**
 * Trigger prop interaction event via API.
 * 
 * @param {string} roomId - Target room ID.
 */
window.triggerProp = async (roomId) => {
  const propId = document.getElementById(`prop-id-${roomId}`).value;
  const type = document.getElementById(`prop-type-${roomId}`).value;
  const val = document.getElementById(`prop-val-${roomId}`).value;
  
  logToTerminal(`🎮 Triggering Prop <b>[${propId}]</b> in room: <b>${roomId}</b> (${type}=${val})`, 'command');
  try {
    await fetch(`${API_BASE}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        room_id: roomId,
        command: 'trigger_prop',
        prop_id: propId,
        interaction_type: type,
        value: val
      })
    });
  } catch (err) {
    logToTerminal(`❌ Prop trigger failed: ${err.message}`, 'system');
  }
};

/**
 * Trigger audio playback command via API.
 * 
 * @param {string} roomId - Target room ID.
 */
window.playAudio = async (roomId) => {
  const track = document.getElementById(`audio-track-${roomId}`).value;
  logToTerminal(`🔊 Playing Audio <b>[${track}]</b> in room: <b>${roomId}</b>`, 'command');
  try {
    await fetch(`${API_BASE}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room_id: roomId, command: 'play_audio', track })
    });
  } catch (err) {
    logToTerminal(`❌ Audio trigger failed: ${err.message}`, 'system');
  }
};

/**
 * Apply ambiance lighting color command via API.
 * 
 * @param {string} roomId - Target room ID.
 */
window.setLights = async (roomId) => {
  const color = document.getElementById(`light-color-${roomId}`).value;
  logToTerminal(`💡 Applying Light <b>[${color}]</b> in room: <b>${roomId}</b>`, 'command');
  try {
    await fetch(`${API_BASE}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room_id: roomId, command: 'set_lights', color })
    });
  } catch (err) {
    logToTerminal(`❌ Light trigger failed: ${err.message}`, 'system');
  }
};

/**
 * Dispatch generic operator room command (unlockDoor, reset).
 * 
 * @param {string} roomId - Target room ID.
 * @param {string} command - Command name string.
 */
window.sendCommand = async (roomId, command) => {
  try {
    logToTerminal(`🚀 Sending Command <b>[${command}]</b> to room: <b>${roomId}</b>`, 'command');
    await fetch(`${API_BASE}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room_id: roomId, command })
    });
    setTimeout(fetchStatus, 500);
  } catch (err) {
    logToTerminal(`❌ Command transmission failed: ${err.message}`, 'system');
  }
};

/**
 * Fetch and render system presence data cards.
 */
async function fetchPresenceData() {
  try {
    const res = await fetch(`${API_BASE}/presence`);
    const data = await res.json();
    
    let html = '';
    for (const [serviceId, info] of Object.entries(data)) {
      // Skip raw individual prop or badge device noise
      if (serviceId.startsWith('prop_prop') || serviceId.startsWith('badge_b')) {
        continue;
      }
      
      const isOnline = info.status === 'online';
      const timestampStr = info.timestamp ? new Date(info.timestamp * 1000).toLocaleTimeString() : 'N/A';
      
      let detailText = `Last Seen: ${timestampStr}`;
      if (info.props_online !== undefined) {
        detailText = `📦 <b>${info.props_online}/${info.props_total || 40} Props Available</b> | Last Seen: ${timestampStr}`;
      } else if (info.badges_active !== undefined) {
        detailText = `🏷️ <b>${info.badges_active}/${info.badges_total || 80} Badges Activated</b> | Last Seen: ${timestampStr}`;
      }
      
      html += `
        <div class="presence-card ${isOnline ? 'online' : 'offline'}">
          <div class="presence-title">
            <span>${serviceId}</span>
            <span class="presence-badge ${isOnline ? 'badge-online' : 'badge-offline'}">${info.status || 'unknown'}</span>
          </div>
          <div class="presence-time">${detailText}</div>
        </div>
      `;
    }
    
    presenceWrapper.innerHTML = html || '<div>No system presence data reported yet.</div>';
  } catch (err) {
    console.error('Failed to fetch presence data', err);
  }
}

/**
 * Fetch and render advanced venue analytics dashboards (KPIs, bottlenecks, safety index, hardware alerts).
 */
async function fetchAnalyticsData() {
  try {
    // 1. Center Overview
    const centerRes = await fetch(`${API_BASE}/stats/game_center`);
    if (centerRes.ok) {
      const data = await centerRes.json();
      document.getElementById('analytics-center-body').innerHTML = `
        <div class="metric-big">${data.kpis ? data.kpis.total_completed_games : 0}</div>
        <div class="metric-label">Total Completed Games</div>
        <div style="margin-top:1rem; font-size:0.9rem;">
          <b>Estimated Hourly Throughput:</b> ${data.kpis ? data.kpis.estimated_hourly_player_throughput : 0} players/hr<br>
          <b>Overall Avg Duration:</b> ${data.kpis ? Math.round(data.kpis.overall_avg_duration_sec / 60) : 0} minutes
        </div>
      `;
    }

    // 2. Bottlenecks
    const bRes = await fetch(`${API_BASE}/stats/bottlenecks`);
    if (bRes.ok) {
      const data = await bRes.json();
      const list = (data.chokepoints || []).map(cp => `<li><b>${cp.prop_id}</b>: ${cp.total_interactions} interactions (${cp.bottleneck_severity} severity)</li>`).join('');
      document.getElementById('analytics-bottlenecks-body').innerHTML = list ? `<ul>${list}</ul>` : '<div>No chokepoints detected.</div>';
    }

    // 3. Safety
    const sRes = await fetch(`${API_BASE}/stats/safety`);
    if (sRes.ok) {
      const data = await sRes.json();
      document.getElementById('analytics-safety-body').innerHTML = `
        <div class="metric-big" style="color:${data.safety_score_pct >= 80 ? '#00e676' : '#ff1744'}">${data.safety_score_pct}%</div>
        <div class="metric-label">Safety & Comfort Score (${data.overall_status})</div>
        <div style="margin-top:0.8rem; font-size:0.85rem;">
          <b>Avg Temp:</b> ${data.metrics ? data.metrics.ambient_temp_avg_c : 0}°C | <b>Avg Humidity:</b> ${data.metrics ? data.metrics.ambient_humidity_avg_pct : 0}%<br>
          <b>Safety Alerts:</b> ${data.metrics ? data.metrics.total_safety_alerts : 0}
        </div>
      `;
    }

    // 4. Maintenance
    const mRes = await fetch(`${API_BASE}/stats/maintenance`);
    if (mRes.ok) {
      const data = await mRes.json();
      const list = (data.maintenance_required || []).map(m => `<li>⚠️ <b>${m.component_id}</b> (${m.type}): ${m.status} (level: ${m.current_level})</li>`).join('');
      document.getElementById('analytics-maintenance-body').innerHTML = list ? `<ul>${list}</ul>` : '<div>All props & hardware fully operational. No maintenance alerts.</div>';
    }
  } catch (err) {
    console.error('Failed to fetch analytics', err);
  }
}

periodSelect.addEventListener('change', async () => {
  const period = getSelectedPeriod();
  logToTerminal(`⚙️ Timeframe filter updated to: <b>${period}</b>`, 'system');
  for (const roomId of Object.keys(roomsState)) {
    await updateRoomData(roomId);
  }
});

btnResetDb.addEventListener('click', async () => {
  if (confirm('⚠️ Are you sure you want to RESET the entire events database?')) {
    try {
      const res = await fetch(`${API_BASE}/stats/reset`);
      const data = await res.json();
      if (data.success) {
        logToTerminal(`🔥 <b>Database Cleared:</b> Historical analytics reset.`, 'system');
        for (const roomId of Object.keys(roomsState)) {
          await updateRoomData(roomId);
        }
      }
    } catch (err) {
      logToTerminal(`❌ Database reset failed: ${err.message}`, 'system');
    }
  }
});

// Boot logic initialization
fetchStatus();
setInterval(fetchStatus, 2000);
setInterval(async () => {
  for (const roomId of Object.keys(roomsState)) {
    await updateRoomData(roomId);
  }
}, 5000);

