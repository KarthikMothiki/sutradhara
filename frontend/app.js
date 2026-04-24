/**
 * Sūtradhāra — AI Productivity OS
 * High-Fidelity Frontend Logic
 */

// ── Configuration ──────────────────────────────────────────────
const BACKEND_URL = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://127.0.0.1:8080'
    : 'https://sutradhara-agent-716237412278.us-central1.run.app';

const API_BASE = BACKEND_URL + '/api/v1';
const WS_BASE = BACKEND_URL.replace('http://', 'ws://').replace('https://', 'wss://');

// ── State ──────────────────────────────────────────────────────
let ws = null;
let isProcessing = false;
const chatSessionId = crypto.randomUUID();

// Impact Metrics
const impactMetrics = {
    conflicts: 0,
    tasks: 0,
    minutes: 0
};

// ── DOM Elements ───────────────────────────────────────────────
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const canvasContent = document.getElementById('canvas-content');
const traceTimeline = document.getElementById('trace-timeline');
const workflowContainer = document.getElementById('workflow-container');
const toastContainer = document.getElementById('toast-container');
const statusDot = document.querySelector('.status-dot');
const statusText = document.querySelector('.status-text');

// ── Initialize ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initMermaid();
    setupEventListeners();
    
    // Initial welcome message sequence
    setTimeout(() => showToast('🌅', 'Good morning! Your daily briefing is ready.'), 1000);
});

function initMermaid() {
    mermaid.initialize({
        startOnLoad: false,
        theme: 'base',
        themeVariables: {
            primaryColor: '#7F77DD',
            primaryTextColor: '#111827',
            primaryBorderColor: '#7F77DD',
            lineColor: '#378ADD',
            fontFamily: 'Inter, sans-serif',
            fontSize: '13px',
        },
    });
}

function setupEventListeners() {
    btnSend.addEventListener('click', sendCommand);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendCommand();
        }
    });

    // Auto-resize textarea
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });

    // Suggestion chips
    document.querySelectorAll('.chip').forEach(chip => {
        chip.addEventListener('click', () => {
            chatInput.value = chip.dataset.query;
            sendCommand();
        });
    });

    // Demo Mode Button
    document.getElementById('btn-demo').addEventListener('click', runDemoSeed);

    // Voice Bridge placeholder
    document.getElementById('btn-voice').addEventListener('click', () => {
        showToast('🎤', 'Voice bridge activated. (STT simulation)');
        chatInput.value = "Schedule deep work for tomorrow morning.";
        setTimeout(sendCommand, 1500);
    });
}

// ── Core Actions ───────────────────────────────────────────────

async function sendCommand() {
    const query = chatInput.value.trim();
    if (!query || isProcessing) return;

    isProcessing = true;
    updateStatus('processing', 'Orchestrating...');
    btnSend.disabled = true;

    // Add user message
    addChatMessage('user', query);
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Reset Canvas (except pinned briefing)
    clearCanvas(false);
    clearLoom();

    try {
        const response = await fetch(`${API_BASE}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, session_id: chatSessionId }),
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        connectWebSocket(data.id);
        pollResult(data.id);
        
    } catch (error) {
        addChatMessage('system', `❌ Error: ${error.message}`);
        updateStatus('ready', 'Error');
        isProcessing = false;
        btnSend.disabled = false;
    }
}

async function runDemoSeed() {
    showToast('🎬', 'Seeding demo environment...');
    try {
        const response = await fetch(`${API_BASE}/demo/seed`, { method: 'POST' });
        const data = await response.json();
        
        // Render a fake briefing card to show it worked
        renderBriefingCard({
            meetings: 3,
            tasks: 5,
            insight: "You have a 15-min gap between your 2pm and 3pm meetings. I suggest a quick recharge."
        });
        
        showToast('✅', 'Demo data seeded. Try: "Run conflict detection"');
    } catch (error) {
        showToast('❌', 'Demo seeding failed.');
    }
}

// ── Canvas Rendering (Action Theater) ──────────────────────────

function renderCanvasCard(type, data, agent = 'manager') {
    // Remove empty state
    const empty = canvasContent.querySelector('.canvas-empty');
    if (empty) empty.remove();

    const card = document.createElement('div');
    card.className = `canvas-card ${agent} ${type.toLowerCase()}`;
    
    let content = '';
    switch (type) {
        case 'CALENDAR_CONFLICT':
            content = `
                <div class="card-header">
                    <span class="card-tag">Schedule Conflict</span>
                    <span class="badge" style="color:var(--agent-error)">Overlapping</span>
                </div>
                <div class="card-title">Double Booking Detected</div>
                <div class="conflict-visual">
                    <div class="conflict-item">
                        <span>Standup</span>
                        <span class="conflict-time">09:00 - 09:30</span>
                    </div>
                    <div class="conflict-item">
                        <span>Client Review</span>
                        <span class="conflict-time">09:15 - 10:00</span>
                    </div>
                    <div style="font-size:0.7rem; color:var(--text-muted); margin-top:8px">⚠️ 15-minute overlap found</div>
                </div>
                <div class="card-actions">
                    <button class="btn-primary" onclick="resolveConflictDemo(this)">Reschedule Client Review</button>
                    <button class="btn-outline" onclick="this.closest('.canvas-card').remove()">Dismiss</button>
                </div>
            `;
            break;
            
        case 'DRAFT_ACTION':
            content = `
                <div class="card-header">
                    <span class="card-tag">Staged Action</span>
                    <span class="badge" style="color:var(--agent-focus)">Awaiting Approval</span>
                </div>
                <div class="card-title">${data.title || 'Proposed Update'}</div>
                <p class="card-meta" style="margin:8px 0">${data.description}</p>
                <div class="card-actions">
                    <button class="btn-primary" style="background:var(--agent-manager)" onclick="approveStagedAction(this, '${data.action_id}')">Approve & Execute</button>
                    <button class="btn-outline" onclick="rejectStagedAction(this, '${data.action_id}')">Reject</button>
                </div>
            `;
            break;


        case 'NOTION_TASKS':
            content = `
                <div class="card-header">
                    <span class="card-tag">Notion Sync</span>
                </div>
                <div class="card-title">Top Priorities</div>
                <div class="task-list" style="margin-top:8px">
                    ${data.tasks.map(t => `<div style="font-size:0.85rem; padding:4px 0; border-bottom:0.5px solid var(--border)">• ${t.title} <span class="badge">${t.priority}</span></div>`).join('')}
                </div>
            `;
            updateImpact('tasks', data.tasks.length);
            break;
    }

    card.innerHTML = content;
    canvasContent.appendChild(card);
    canvasContent.scrollTop = canvasContent.scrollHeight;
}

function renderBriefingCard(data) {
    const anchor = document.getElementById('briefing-anchor');
    const existing = document.getElementById('daily-briefing-card');
    if (existing) existing.remove();

    const card = document.createElement('div');
    card.id = 'daily-briefing-card';
    card.className = 'canvas-card manager briefing';
    card.innerHTML = `
        <div class="card-header">
            <span class="card-tag">Proactive Insight</span>
            <span class="badge">Chief of Staff</span>
        </div>
        <div class="card-title">Daily Briefing</div>
        <div class="briefing-grid" style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:10px 0">
            <div style="background:var(--bg-tertiary); padding:8px; border-radius:6px; text-align:center">
                <div style="font-size:1.2rem; font-weight:600">${data.meetings}</div>
                <div style="font-size:0.6rem; text-transform:uppercase">Meetings Today</div>
            </div>
            <div style="background:var(--bg-tertiary); padding:8px; border-radius:6px; text-align:center">
                <div style="font-size:1.2rem; font-weight:600">${data.tasks}</div>
                <div style="font-size:0.6rem; text-transform:uppercase">Notion Tasks</div>
            </div>
        </div>
        <p class="card-meta" style="font-style:italic">"${data.insight}"</p>
    `;
    anchor.appendChild(card);
}

// ── The Loom (Agent Cortex) ────────────────────────────────────

function addLoomLog(agent, title, subtitle = '') {
    const entry = document.createElement('div');
    entry.className = 'loom-log-entry';
    entry.dataset.agent = agent;
    
    entry.innerHTML = `
        <div class="loom-log-indicator" style="background:var(--agent-${agent.split('_')[0]})"></div>
        <div class="log-body">
            <div class="log-title">${title}</div>
            ${subtitle ? `<div class="log-meta">${subtitle}</div>` : ''}
        </div>
    `;
    
    traceTimeline.appendChild(entry);
    traceTimeline.scrollTop = traceTimeline.scrollHeight;
}

async function renderWorkflow(diagram) {
    workflowContainer.innerHTML = `<div class="mermaid">${diagram}</div>`;
    try {
        await mermaid.run({ nodes: [workflowContainer.querySelector('.mermaid')] });
        
        // Add click handlers to nodes for filtering
        setTimeout(() => {
            document.querySelectorAll('.mermaid .node').forEach(node => {
                node.style.cursor = 'pointer';
                node.addEventListener('click', () => {
                    // Remove highlight from others
                    document.querySelectorAll('.mermaid .node').forEach(n => n.classList.remove('node-active'));
                    node.classList.add('node-active');
                    
                    const agentName = node.id.split('-')[0].toLowerCase();
                    filterLoomLogs(agentName);
                });
            });
        }, 500);

    } catch (e) { console.error('Mermaid error', e); }
}

function filterLoomLogs(agentName) {
    document.getElementById('filter-status').textContent = `Filtering: ${agentName}`;
    document.querySelectorAll('.loom-log-entry').forEach(entry => {
        const entryAgent = entry.dataset.agent.toLowerCase();
        entry.style.opacity = (entryAgent.includes(agentName) || agentName === 'all') ? '1' : '0.1';
    });
    
    // Add reset button if not present
    if (agentName !== 'all') {
        const reset = document.createElement('span');
        reset.innerHTML = ' (Reset)';
        reset.style.cursor = 'pointer';
        reset.style.color = 'var(--agent-manager)';
        reset.onclick = () => filterLoomLogs('all');
        document.getElementById('filter-status').appendChild(reset);
    }
}

// ── Helpers ───────────────────────────────────────────────────

function addChatMessage(role, text) {
    const msg = document.createElement('div');
    msg.className = `message message-${role}`;
    msg.innerHTML = `
        <div class="message-content">
            <p>${text.replace(/\n/g, '<br>')}</p>
        </div>
    `;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function updateImpact(key, val) {
    const startValue = impactMetrics[key];
    impactMetrics[key] += val;
    if (key === 'conflicts') impactMetrics.minutes += val * 15;
    if (key === 'tasks') impactMetrics.minutes += val * 3;
    
    animateNumber(`stat-conflicts`, startValue, impactMetrics.conflicts);
    animateNumber(`stat-tasks`, 0, impactMetrics.tasks); // Simplified
    animateNumber(`stat-minutes`, 0, impactMetrics.minutes);
}

function animateNumber(id, start, end) {
    const obj = document.getElementById(id);
    if (!obj) return;
    
    let current = start;
    const duration = 500;
    const stepTime = 50;
    const steps = duration / stepTime;
    const increment = (end - start) / steps;
    if (increment === 0) { obj.textContent = end; return; }
    
    const timer = setInterval(() => {
        current += increment;
        if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
            obj.textContent = end;
            clearInterval(timer);
        } else {
            obj.textContent = Math.floor(current);
        }
    }, stepTime);
}

function showToast(icon, message) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<span class="toast-icon">${icon}</span> ${message}`;
    toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function updateStatus(state, msg) {
    statusText.textContent = msg;
    statusDot.style.background = state === 'processing' ? 'var(--agent-focus)' : '#10B981';
}

// ── Approvals & Interactions ──────────────────────────────────

async function approveStagedAction(btn, actionId) {
    const card = btn.closest('.canvas-card');
    btn.disabled = true;
    btn.textContent = 'Executing...';
    
    try {
        const response = await fetch(`${API_BASE}/actions/${actionId}/approve`, { method: 'POST' });
        const data = await response.json();
        
        if (data.error) throw new Error(data.error);

        card.style.borderColor = 'var(--agent-planner)';
        card.querySelector('.badge').textContent = 'Executed';
        card.querySelector('.badge').style.color = 'var(--agent-planner)';
        
        btn.remove();
        card.querySelector('.btn-outline').remove();
        
        showToast('✅', 'Action executed & logged.');
        updateImpact('tasks', 1);
    } catch (error) {
        showToast('❌', `Execution failed: ${error.message}`);
        btn.disabled = false;
        btn.textContent = 'Retry Approval';
    }
}

async function rejectStagedAction(btn, actionId) {
    const card = btn.closest('.canvas-card');
    try {
        await fetch(`${API_BASE}/actions/${actionId}/reject`, { method: 'POST' });
        card.remove();
        showToast('🗑️', 'Draft discarded.');
    } catch (e) { card.remove(); }
}

function resolveConflictDemo(btn) {
    const visual = btn.closest('.canvas-card').querySelector('.conflict-visual');
    btn.disabled = true;
    btn.textContent = 'Rescheduling...';
    
    setTimeout(() => {
        visual.classList.add('resolved');
        const items = visual.querySelectorAll('.conflict-item');
        items[1].querySelector('span').textContent = 'Client Review (Moved)';
        items[1].querySelector('.conflict-time').textContent = '11:00 - 11:45';
        
        btn.closest('.canvas-card').querySelector('.badge').textContent = 'Resolved';
        btn.closest('.canvas-card').querySelector('.badge').style.color = 'var(--agent-planner)';
        btn.remove();
        
        updateImpact('conflicts', 1);
        showToast('📍', 'Calendar updated. Double-booking resolved.');
    }, 1000);
}


// ── Networking ────────────────────────────────────────────────

function connectWebSocket(id) {
    if (ws) ws.close();
    ws = new WebSocket(`${WS_BASE}/ws/trace/${id}`);
    ws.onmessage = (e) => {
        const ev = JSON.parse(e.data);
        handleAgentEvent(ev);
    };
}

function handleAgentEvent(ev) {
    const agent = ev.agent_name || 'manager';
    switch (ev.event_type) {
        case 'agent_start':
            addLoomLog(agent, `${agent} thinking...`, ev.data?.query);
            break;
        case 'tool_call':
            addLoomLog(agent, `Executing ${ev.tool_name}`, JSON.stringify(ev.data).substring(0, 50));
            break;
        case 'tool_result':
            addLoomLog(agent, `${ev.tool_name} returned data`, JSON.stringify(ev.data).substring(0, 50));
            break;
        case 'canvas_event':
            renderCanvasCard(ev.data.type, ev.data.payload, agent);
            break;
        case 'workflow_diagram':
            renderWorkflow(ev.data.diagram);
            break;
    }
}


async function pollResult(id) {
    const poll = async () => {
        const res = await fetch(`${API_BASE}/query/${id}`);
        const data = await res.json();
        if (data.status === 'completed') {
            addChatMessage('assistant', data.final_response);
            updateStatus('ready', 'Ready');
            isProcessing = false;
            btnSend.disabled = false;
            return;
        }
        setTimeout(poll, 2000);
    };
    poll();
}
