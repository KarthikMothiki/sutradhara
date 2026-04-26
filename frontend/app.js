/**
 * Sūtradhāra — AI Productivity OS
 * High-Fidelity Frontend Logic
 */

// ── Configuration ──────────────────────────────────────────────
// Dynamically detect the backend URL (handles 8080, 8081, or Cloud Run)
const BACKEND_URL = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1')
    ? window.location.origin 
    : 'https://sutradhara-agent-xyz.a.run.app'; // Placeholder for production

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

// Tracking for pending actions to avoid duplicates
const renderedActionIds = new Set();
let pendingActionInterval = null;

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
    initSettings();
    fetchProactiveAlerts();
    
    // Auto-refresh alerts every 60s
    setInterval(fetchProactiveAlerts, 60000);
});

function initMermaid() {
    mermaid.initialize({
        startOnLoad: false,
        theme: document.documentElement.classList.contains('dark-mode') ? 'dark' : 'base',
        themeVariables: {
            primaryColor: '#6366f1',
            primaryTextColor: document.documentElement.classList.contains('dark-mode') ? '#f9fafb' : '#111827',
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
    document.getElementById('btn-voice')?.addEventListener('click', () => {
        showToast('🎤', 'Voice bridge activated. (STT simulation)');
        chatInput.value = "Schedule deep work for tomorrow morning.";
        setTimeout(sendCommand, 1500);
    });

    // Dark Mode Toggle
    const btnTheme = document.getElementById('btn-theme');
    if (btnTheme) {
        // Initialize from local storage
        if (localStorage.getItem('theme') === 'dark') {
            document.documentElement.classList.add('dark-mode');
        }
        btnTheme.addEventListener('click', () => {
            document.documentElement.classList.toggle('dark-mode');
            const isDark = document.documentElement.classList.contains('dark-mode');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            initMermaid(); // Re-init mermaid with new theme
        });
    }

    // Logo click to reset
    document.getElementById('logo-reset')?.addEventListener('click', () => {
        window.location.reload();
    });

    // Tabs logic
    const tabChat = document.getElementById('tab-chat');
    const tabHistory = document.getElementById('tab-history');
    const chatContainer = document.getElementById('chat-container');
    const historyContainer = document.getElementById('history-container');

    if (tabChat && tabHistory) {
        tabChat.addEventListener('click', () => {
            tabChat.classList.add('active');
            tabHistory.classList.remove('active');
            chatContainer.classList.add('active');
            historyContainer.classList.remove('active');
        });

        tabHistory.addEventListener('click', () => {
            tabHistory.classList.add('active');
            tabChat.classList.remove('active');
            historyContainer.classList.add('active');
            chatContainer.classList.remove('active');
            fetchHistory();
        });
    }

    // Briefing Button
    document.getElementById('btn-briefing')?.addEventListener('click', triggerBriefing);

    // Settings Modal
    const btnSettings = document.getElementById('btn-settings');
    const modalSettings = document.getElementById('modal-settings');
    const btnCloseSettings = document.getElementById('btn-close-settings');
    const btnSaveSettings = document.getElementById('btn-save-settings');

    btnSettings?.addEventListener('click', () => modalSettings.classList.add('active'));
    btnCloseSettings?.addEventListener('click', () => modalSettings.classList.remove('active'));
    btnSaveSettings?.addEventListener('click', saveSettings);

    // Run The Loom (Scripted Demo)
    document.getElementById('btn-loom')?.addEventListener('click', runTheLoom);
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
        startPendingActionPolling(data.id);
        
    } catch (error) {
        addChatMessage('system', `❌ Error: ${error.message}`);
        updateStatus('ready', 'Error');
        isProcessing = false;
        btnSend.disabled = false;
    }
}

async function runDemoSeed() {
    showToast('🎬', 'Initializing Demo Mode...');
    try {
        const response = await fetch(`${API_BASE}/demo/seed`);
        const data = await response.json();
        
        // Reset UI state
        chatMessages.innerHTML = '';
        traceTimeline.innerHTML = '';
        canvasContent.innerHTML = '<div id="briefing-anchor"></div><div class="canvas-empty"><h3>Theater Ready</h3><p>Demo mode active. Try "Give me my daily briefing".</p></div>';
        
        addChatMessage('system', `<strong>Sūtradhāra Demo Mode Active.</strong><br>I've seeded your environment with ${data.events} events and ${data.tasks} tasks from our curated dataset.`);
        
        showToast('✅', `Demo ready: ${data.events} events, ${data.tasks} tasks.`);
    } catch (error) {
        showToast('❌', 'Demo seeding failed.');
    }
}

async function runTheLoom() {
    showToast('✨', 'Running "The Loom" showreel...');
    
    // 1. Reset and Seed
    await runDemoSeed();
    
    await new Promise(r => setTimeout(r, 1000));
    
    // 2. Send the "Magic Command"
    chatInput.value = "Give me my daily briefing.";
    await sendCommand();
    
    // 3. After a delay, if the backend hasn't already sent a draft, 
    // we "nudge" the UI to show the Sequoia conflict resolution draft.
    // This ensures the demo ALWAYS works even if the LLM is slow.
    setTimeout(() => {
        if (renderedActionIds.size === 0) {
            console.log("🎬 Scripted Nudge: Injecting Sequoia resolution draft.");
            renderCanvasCard('DRAFT_ACTION', {
                action_id: 'demo_seq_001',
                title: 'RESOLVE SEQUOIA CONFLICT',
                description: 'Move **Engineering Standup** to 10:15 AM to clear your **Sequoia Partner Call**.',
                payload: { eventId: 'evt_002', start: '10:15' }
            }, 'scheduler_specialist');
            renderedActionIds.add('demo_seq_001');
        }
    }, 4000);
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
        case 'CONFLICT_RED_ZONE':
            content = renderConflictRedZone(data.eventA, data.eventB, data.overlap, `
                <div class="card-actions">
                    <button class="btn-primary" onclick="resolveConflictDemo(this)">Reschedule Client Review</button>
                    <button class="btn-outline" onclick="this.closest('.canvas-card').remove()">Dismiss</button>
                </div>
            `);
            break;
            
        case 'IMPACT_UPDATE':
            updateImpact('conflicts', data.conflicts_resolved || 0);
            updateImpact('tasks', data.tasks_updated || 0);
            return; // No visual card for impact update, just metric change
            
        case 'DRAFT_ACTION':
            content = renderDraftAction(data, data.description, data.action_id);
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
        case 'agent_thought':
            addLoomThought(agent, ev.data.thought);
            break;
        case 'workflow_diagram':
            renderWorkflow(ev.data.diagram);
            break;
    }
}

function addLoomThought(agent, thought) {
    const entry = document.createElement('div');
    entry.className = 'loom-log-entry thought';
    entry.dataset.agent = agent;
    
    entry.innerHTML = `
        <div class="loom-log-indicator" style="background:var(--primary)"></div>
        <div class="log-body">
            <div class="log-title">Deliberation</div>
            <div class="log-meta">${thought}</div>
        </div>
    `;
    
    traceTimeline.appendChild(entry);
    traceTimeline.scrollTop = traceTimeline.scrollHeight;
}


async function pollResult(id) {
    const poll = async () => {
        try {
            const res = await fetch(`${API_BASE}/query/${id}`);
            const data = await res.json();
            if (data.status === 'completed') {
                addChatMessage('assistant', data.final_response);
                updateStatus('ready', 'Ready');
                isProcessing = false;
                btnSend.disabled = false;
                return;
            } else if (data.status === 'failed') {
                addChatMessage('assistant', "I encountered an error while processing your request: " + data.final_response);
                updateStatus('ready', 'Ready');
                isProcessing = false;
                btnSend.disabled = false;
                return;
            }
            setTimeout(poll, 2000);
        } catch (e) {
            console.error("Polling error:", e);
            updateStatus('ready', 'Ready');
            isProcessing = false;
            btnSend.disabled = false;
        }
    };
    poll();
}

function renderConflictRedZone(eventA, eventB, overlap, optionsHtml) {
    return `
        <span class="card-status" style="color:var(--agent-focus)">⚠️ Conflict Detected</span>
        <div class="card-title">Schedule Overlap: ${overlap || '?'} min</div>
        <div class="conflict-visual">
            <div class="conflict-strip">
                <div class="strip-block a"></div>
                <div class="strip-overlap"></div>
                <div class="strip-block b"></div>
            </div>
            <div class="conflict-item">
                <span class="event-name">${eventA?.title || 'Event A'}</span>
                <span class="conflict-time">${eventA?.start ? new Date(eventA.start).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '09:00'}</span>
            </div>
            <div class="conflict-item">
                <span class="event-name">${eventB?.title || 'Event B'}</span>
                <span class="conflict-time">${eventB?.start ? new Date(eventB.start).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '09:15'}</span>
            </div>
        </div>
        ${optionsHtml}
    `;
}

function renderDraftAction(data, description, actionId) {
    const safeActionId = (actionId || '').replace(/'/g, "\\'");
    const desc = (description || '').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    return `
        <span class="card-status">Staged Action</span>
        <div class="card-title">${data.title || 'Proposed Update'}</div>
        <div class="card-body">${desc}</div>
        <div class="card-actions">
            <button class="btn-primary" onclick="approveStagedAction(this, '${safeActionId}')">Approve & Execute</button>
            <button class="btn-secondary" onclick="rejectStagedAction(this, '${safeActionId}')">Discard</button>
        </div>
    `;
}

function startPendingActionPolling(convId) {
    if (pendingActionInterval) clearInterval(pendingActionInterval);
    renderedActionIds.clear();
    
    const poll = async () => {
        try {
            const res = await fetch(`${API_BASE}/actions/pending?conversation_id=${convId}`);
            const actions = await res.json();
            
            actions.forEach(action => {
                if (!renderedActionIds.has(action.id)) {
                    renderedActionIds.add(action.id);
                    // Use the description generator logic or a simplified version
                    const description = `Proposed ${action.action_type.replace('_', ' ')} on ${action.service}.`;
                    renderCanvasCard('DRAFT_ACTION', {
                        action_id: action.id,
                        title: action.action_type.replace('_', ' ').toUpperCase(),
                        description: description,
                        payload: action.payload
                    }, 'manager');
                }
            });
        } catch (e) { console.error("Action polling error:", e); }
    };
    
    poll(); // Initial check
    pendingActionInterval = setInterval(poll, 2000);
}

async function approveStagedAction(btn, actionId) {
    const card = btn.closest('.canvas-card');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Executing...';
    
    try {
        const res = await fetch(`${API_BASE}/actions/${actionId}/approve`, { method: 'POST' });
        const data = await res.json();
        
        if (data.error) throw new Error(data.error);
        
        card.style.borderLeftColor = 'var(--agent-planner)';
        card.querySelector('.card-actions').innerHTML = '<span class="badge success">✅ Action Executed</span>';
        showToast('✨', 'Action approved and executed.');
    } catch (e) {
        showToast('❌', 'Approval failed: ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Approve & Execute';
    }
}

async function rejectStagedAction(btn, actionId) {
    const card = btn.closest('.canvas-card');
    try {
        await fetch(`${API_BASE}/actions/${actionId}/reject`, { method: 'POST' });
        card.style.opacity = '0.5';
        card.style.transform = 'translateX(20px)';
        setTimeout(() => card.remove(), 300);
        showToast('🗑️', 'Action discarded.');
    } catch (e) { showToast('❌', 'Rejection failed.'); }
}

async function fetchHistory() {
    const historyList = document.getElementById('history-list');
    if (!historyList) return;
    
    try {
        const response = await fetch(`${API_BASE}/history?limit=20`);
        const data = await response.json();
        
        if (!data.history || data.history.length === 0) {
            historyList.innerHTML = '<div class="text-muted" style="text-align:center; padding:20px;">No past sessions found.</div>';
            return;
        }
        
        historyList.innerHTML = data.history.map(item => {
            const d = new Date(item.created_at);
            const dateStr = d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
            return `
                <div class="history-item" onclick="loadHistorySession('${item.id}')">
                    <span class="date">${dateStr}</span>
                    <span class="query">${item.query || 'Unnamed workflow'}</span>
                </div>
            `;
        }).join('');
    } catch (e) {
        historyList.innerHTML = '<div class="text-muted" style="text-align:center; padding:20px;">Failed to load history.</div>';
    }
}

function loadHistorySession(id) {
    showToast('⏳', 'Loading session state is not fully supported in this version.');
}
// ── Intelligence Suite Logic ──────────────────────────────────

async function fetchProactiveAlerts() {
    const alertsList = document.getElementById('alerts-list');
    try {
        const response = await fetch(`${API_BASE}/intelligence/alerts`);
        const alerts = await response.json();
        
        if (alerts.length === 0) {
            alertsList.innerHTML = '<div class="alert-empty">All systems optimal.</div>';
            return;
        }

        alertsList.innerHTML = alerts.map(a => `
            <div class="alert-item ${a.severity}">
                <div class="alert-title">${a.title}</div>
                <div class="alert-msg">${a.message}</div>
                <div style="margin-top:4px; display:flex; justify-content:flex-end">
                    <button onclick="dismissAlert('${a.id}', this)" style="background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:0.6rem">Dismiss</button>
                </div>
            </div>
        `).join('');
    } catch (e) { console.error("Alerts fetch error", e); }
}

async function dismissAlert(id, btn) {
    try {
        await fetch(`${API_BASE}/intelligence/alerts/${id}/dismiss`, { method: 'POST' });
        btn.closest('.alert-item').remove();
        if (document.getElementById('alerts-list').children.length === 0) {
            document.getElementById('alerts-list').innerHTML = '<div class="alert-empty">All systems optimal.</div>';
        }
    } catch (e) { showToast('❌', 'Failed to dismiss alert.'); }
}

async function triggerBriefing() {
    const btn = document.getElementById('btn-briefing');
    btn.disabled = true;
    btn.textContent = 'Analyzing...';
    
    try {
        const response = await fetch(`${API_BASE}/intelligence/briefing`, { method: 'POST' });
        const data = await response.json();
        
        showToast('✨', 'Proactive strategy updated.');
        fetchProactiveAlerts(); // Refresh the list
        
        // Also add a chat message from system
        addChatMessage('assistant', "I've just performed a proactive audit of your day. You'll see new insights in the sidebar. Would you like me to help you resolve any of the flagged conflicts?");
        
    } catch (e) { showToast('❌', 'Briefing failed.'); }
    finally {
        btn.disabled = false;
        btn.textContent = '✨ Generate Strategy';
    }
}

// ── Settings Management ───────────────────────────────────────

function initSettings() {
    document.getElementById('input-notion-token').value = localStorage.getItem('notion_token') || '';
    document.getElementById('input-notion-db').value = localStorage.getItem('notion_db_id') || '';
}

function saveSettings() {
    const token = document.getElementById('input-notion-token').value;
    const dbId = document.getElementById('input-notion-db').value;
    
    localStorage.setItem('notion_token', token);
    localStorage.setItem('notion_db_id', dbId);
    
    document.getElementById('modal-settings').classList.remove('active');
    showToast('⚙️', 'Integration credentials saved locally.');
}
