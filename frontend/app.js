/**
 * Sūtradhāra — AI Productivity Orchestrator
 * Frontend application logic
 */

// ── Configuration ──────────────────────────────────────────────
// Important: After deploying to Cloud Run, replace this placeholder with your actual Cloud Run URL
const CLOUD_RUN_URL = 'https://sutradhara-agent-716237412278.us-central1.run.app';

// Determine backend URL based on whether frontend is running locally or mapped to GitHub Pages
const BACKEND_URL = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://127.0.0.1:8080'  // Local FastAPI instance
    : CLOUD_RUN_URL;           // Production Cloud Run instance

const API_BASE = BACKEND_URL + '/api/v1';
const WS_BASE = BACKEND_URL.replace('http://', 'ws://').replace('https://', 'wss://');

// ── State ──────────────────────────────────────────────────────
let currentConversationId = null;
let ws = null;
let isProcessing = false;
// Persistent session ID — survives across queries within a page session.
// The agent uses this to retain conversation history (memory).
// Refreshing the page starts a new chat session.
const chatSessionId = crypto.randomUUID();

// ── DOM Elements ───────────────────────────────────────────────
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const statusIndicator = document.getElementById('status-indicator');
const statusDot = statusIndicator.querySelector('.status-dot');
const statusText = statusIndicator.querySelector('.status-text');
const traceTimeline = document.getElementById('trace-timeline');
const workflowContainer = document.getElementById('workflow-container');
const historyList = document.getElementById('history-list');
const toastContainer = document.getElementById('toast-container');

// ── Initialize ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initMermaid();
    setupEventListeners();
    loadHistory();
});

function initMermaid() {
    const isLight = localStorage.getItem('theme') === 'light';
    mermaid.initialize({
        startOnLoad: false,
        theme: isLight ? 'default' : 'dark',
        themeVariables: {
            primaryColor: '#8b5cf6',
            primaryTextColor: isLight ? '#0f172a' : '#e8e8f0',
            primaryBorderColor: '#6d28d9',
            lineColor: isLight ? '#94a3b8' : '#6060780',
            secondaryColor: isLight ? '#f1f5f9' : '#1a1a28',
            tertiaryColor: isLight ? '#f8fafc' : '#12121a',
            fontFamily: 'Inter, sans-serif',
        },
    });
}

function setupEventListeners() {
    // Send button
    btnSend.addEventListener('click', sendQuery);

    // Enter to send (Shift+Enter for new line)
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendQuery();
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
            sendQuery();
        });
    });

    // Tab switching
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // History button
    document.getElementById('btn-history').addEventListener('click', () => {
        switchTab('history');
        loadHistory();
    });

    // Theme toggle button
    const btnTheme = document.getElementById('btn-settings');
    if (btnTheme) {
        btnTheme.title = "Toggle Theme";
        const svgMoon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>';
        const svgSun = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
        
        if (localStorage.getItem('theme') === 'light') {
            document.body.classList.add('light-mode');
            btnTheme.innerHTML = svgSun;
        } else {
            btnTheme.innerHTML = svgMoon;
        }

        btnTheme.addEventListener('click', () => {
            const isLight = document.body.classList.toggle('light-mode');
            localStorage.setItem('theme', isLight ? 'light' : 'dark');
            btnTheme.innerHTML = isLight ? svgSun : svgMoon;
            
            // Reinitialize mermaid for future diagrams
            initMermaid();
        });
    }

    // Logo click to return to new chat
    const logoBlock = document.querySelector('.logo');
    if (logoBlock) {
        logoBlock.style.cursor = 'pointer';
        logoBlock.addEventListener('click', () => {
            window.location.reload();
        });
    }
}

// ── API Functions ──────────────────────────────────────────────

async function sendQuery() {
    const query = chatInput.value.trim();
    if (!query || isProcessing) return;

    isProcessing = true;
    updateStatus('processing', 'Processing…');
    btnSend.disabled = true;

    // Add user message to chat
    addMessage('user', query, '👤');
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Clear trace timeline
    clearTrace();

    try {
        const response = await fetch(`${API_BASE}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, session_id: chatSessionId }),
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        currentConversationId = data.id;

        // Connect WebSocket for live trace
        connectWebSocket(data.id);

        // Add loading message
        addLoadingMessage();

        // Poll for result
        pollResult(data.id);

        showToast('🚀', 'Query submitted to the crew!');
    } catch (error) {
        addMessage('system', `❌ Error: ${error.message}`, '⚠️');
        updateStatus('error', 'Error');
        isProcessing = false;
        btnSend.disabled = false;
    }
}

async function pollResult(conversationId) {
    const maxRetries = 60;
    let retries = 0;

    const poll = async () => {
        try {
            const response = await fetch(`${API_BASE}/query/${conversationId}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();

            if (data.status === 'completed') {
                removeLoadingMessage();
                addMessage('assistant', data.final_response, '<img src="logo.png" alt="S" class="avatar-logo">', conversationId);

                if (data.workflow_diagram) {
                    renderDiagram(data.workflow_diagram);
                }

                updateStatus('ready', 'Ready');
                isProcessing = false;
                btnSend.disabled = false;
                disconnectWebSocket();
                loadHistory();
                return;
            }

            if (data.status === 'failed') {
                removeLoadingMessage();
                addMessage('system', `❌ ${data.final_response || 'Processing failed'}`, '⚠️');
                updateStatus('error', 'Failed');
                isProcessing = false;
                btnSend.disabled = false;
                disconnectWebSocket();
                return;
            }

            retries++;
            if (retries < maxRetries) {
                setTimeout(poll, 2000);
            } else {
                removeLoadingMessage();
                addMessage('system', '⏱ Query timed out. Check history for updates.', '⚠️');
                updateStatus('ready', 'Ready');
                isProcessing = false;
                btnSend.disabled = false;
            }
        } catch (error) {
            retries++;
            if (retries < maxRetries) {
                setTimeout(poll, 3000);
            }
        }
    };

    setTimeout(poll, 1500);
}

async function loadHistory() {
    try {
        const response = await fetch(`${API_BASE}/history?per_page=20`);
        if (!response.ok) return;

        const data = await response.json();
        renderHistory(data.conversations);
    } catch (error) {
        // Silently fail — history is not critical
    }
}

async function undoConversation(conversationId) {
    try {
        const response = await fetch(`${API_BASE}/query/${conversationId}/undo`, {
            method: 'POST',
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        if (data.success) {
            showToast('↩️', `Undone ${data.undone_actions} action(s)`);
            data.details.forEach(d => addTraceEvent('undo', '↩️', d, ''));
        } else {
            showToast('ℹ️', 'Nothing to undo.');
        }
    } catch (error) {
        showToast('❌', `Undo failed: ${error.message}`);
    }
}

// ── WebSocket ──────────────────────────────────────────────────

function connectWebSocket(conversationId) {
    disconnectWebSocket();

    try {
        ws = new WebSocket(`${WS_BASE}/ws/trace/${conversationId}`);

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleTraceEvent(data);
        };

        ws.onclose = () => { ws = null; };
        ws.onerror = () => { ws = null; };

        // Keepalive ping every 30s
        ws._pingInterval = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send('ping');
            }
        }, 30000);
    } catch (error) {
        // WebSocket not available — rely on polling
    }
}

function disconnectWebSocket() {
    if (ws) {
        clearInterval(ws._pingInterval);
        ws.close();
        ws = null;
    }
}

function handleTraceEvent(event) {
    const iconMap = {
        agent_start: '💭',
        agent_end: '✅',
        tool_call: '🔧',
        tool_result: '📦',
        error: '❌',
        workflow_diagram: '📊',
    };

    const icon = iconMap[event.event_type] || '⚡';
    let title = '';
    let subtitle = '';

    const formatAgentName = (name) => {
        if (!name) return 'System';
        const formatted = name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        if (name.includes('manager')) return `🧠 ${formatted}`;
        if (name.includes('calendar')) return `📅 ${formatted}`;
        if (name.includes('notion')) return `📝 ${formatted}`;
        if (name.includes('planner')) return `🗺️ ${formatted}`;
        if (name.includes('focus')) return `🎯 ${formatted}`;
        return `🤖 ${formatted}`;
    };

    const displayAgent = event.agent_name ? formatAgentName(event.agent_name) : 'Agent';

    switch (event.event_type) {
        case 'agent_start':
            title = `${displayAgent} thinking...`;
            subtitle = event.data?.query ? `"${event.data.query.substring(0, 100)}…"` : '';
            break;
        case 'agent_end':
            let shortRes = event.data?.response ? event.data.response.substring(0, 80) : '';
            title = `${displayAgent} finished analysis`;
            subtitle = shortRes ? `Ready with response: ${shortRes}…` : '';
            break;
        case 'tool_call':
            title = `${displayAgent} executing action`;
            subtitle = `Calling tool: ${event.tool_name}()`;
            break;
        case 'tool_result':
            title = `${event.tool_name}() returned data`;
            subtitle = event.data ? JSON.stringify(event.data).substring(0, 100) : '';
            break;
        case 'error':
            title = 'Error';
            subtitle = event.data?.error || '';
            break;
        case 'workflow_diagram':
            title = `🧠 Manager Agent generating the workflow...`;
            subtitle = 'Live diagram updated';
            if (event.data?.diagram) {
                renderDiagram(event.data.diagram);
            }
            break;
    }

    const time = new Date(event.timestamp).toLocaleTimeString();
    addTraceEvent(event.event_type, icon, title, subtitle, time);
}

// ── UI Rendering ───────────────────────────────────────────────

function addMessage(type, text, avatar, conversationId = null) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message message-${type}`;
    if (type === 'assistant') {
        msgDiv.classList.add('message-response');
    }

    // Convert markdown-like formatting
    const formattedText = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>')
        .replace(/• /g, '&bull; ');

    let undoBtn = '';
    if (conversationId && type === 'assistant') {
        undoBtn = `<button class="btn-undo" onclick="undoConversation('${conversationId}')">↩️ Undo actions</button>`;
    }

    msgDiv.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">
            <p>${formattedText}</p>
            ${undoBtn}
        </div>
    `;

    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addLoadingMessage() {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message message-system';
    msgDiv.id = 'loading-message';
    msgDiv.innerHTML = `
        <div class="message-avatar"><img src="logo.png" alt="S" class="avatar-logo"></div>
        <div class="message-content">
            <p>Thinking<span class="loading-dots">...</span></p>
        </div>
    `;
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Animate dots
    const dots = msgDiv.querySelector('.loading-dots');
    let dotCount = 0;
    msgDiv._interval = setInterval(() => {
        dotCount = (dotCount + 1) % 4;
        dots.textContent = '.'.repeat(dotCount || 1);
    }, 500);
}

function removeLoadingMessage() {
    const msg = document.getElementById('loading-message');
    if (msg) {
        clearInterval(msg._interval);
        msg.remove();
    }
}

function addTraceEvent(type, icon, title, subtitle, time = '') {
    // Remove empty state if present
    const empty = traceTimeline.querySelector('.trace-empty');
    if (empty) empty.remove();

    const eventDiv = document.createElement('div');
    eventDiv.className = 'trace-event';
    eventDiv.innerHTML = `
        <div class="trace-icon ${type}">${icon}</div>
        <div class="trace-details">
            <div class="trace-title">${title}</div>
            ${subtitle ? `<div class="trace-subtitle">${subtitle}</div>` : ''}
        </div>
        ${time ? `<div class="trace-time">${time}</div>` : ''}
    `;

    traceTimeline.appendChild(eventDiv);
    traceTimeline.scrollTop = traceTimeline.scrollHeight;
}

function clearTrace() {
    traceTimeline.innerHTML = '';
}

async function renderDiagram(mermaidCode) {
    switchTab('workflow');

    workflowContainer.innerHTML = '';
    const diagramDiv = document.createElement('div');
    diagramDiv.className = 'mermaid';
    diagramDiv.textContent = mermaidCode;
    workflowContainer.appendChild(diagramDiv);

    try {
        await mermaid.run({ nodes: [diagramDiv] });
    } catch (error) {
        diagramDiv.textContent = mermaidCode;
        diagramDiv.style.whiteSpace = 'pre-wrap';
        diagramDiv.style.fontFamily = 'var(--font-mono)';
        diagramDiv.style.fontSize = '0.75rem';
        diagramDiv.style.color = 'var(--text-secondary)';
    }
}

function renderHistory(conversations) {
    historyList.innerHTML = '';

    if (!conversations || conversations.length === 0) {
        historyList.innerHTML = `
            <div class="trace-empty">
                <div class="trace-empty-icon">📜</div>
                <p>No conversations yet. Start chatting!</p>
            </div>
        `;
        return;
    }

    conversations.forEach(conv => {
        const item = document.createElement('div');
        item.className = 'history-item';
        item.onclick = () => viewConversation(conv.id);

        const time = new Date(conv.created_at).toLocaleString();
        const sourceIcon = conv.source.startsWith('scheduler') ? '⏰' : '💬';

        item.innerHTML = `
            <div class="history-status ${conv.status}"></div>
            <div class="history-content">
                <div class="history-query">${sourceIcon} ${conv.user_query}</div>
                <div class="history-meta">${time} · ${conv.status}</div>
            </div>
        `;

        historyList.appendChild(item);
    });
}

async function viewConversation(conversationId) {
    try {
        const response = await fetch(`${API_BASE}/query/${conversationId}`);
        if (!response.ok) return;

        const data = await response.json();

        // Show the conversation in chat
        addMessage('user', data.user_query, '👤');
        if (data.final_response) {
            addMessage('assistant', data.final_response, '<img src="logo.png" alt="S" class="avatar-logo">', conversationId);
        }

        // Show workflow diagram if available
        if (data.workflow_diagram) {
            renderDiagram(data.workflow_diagram);
        }

        // Show trace events
        clearTrace();

        const formatAgentName = (name) => {
            if (!name) return 'System';
            const formatted = name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
            if (name.includes('manager')) return `🧠 ${formatted}`;
            if (name.includes('calendar')) return `📅 ${formatted}`;
            if (name.includes('notion')) return `📝 ${formatted}`;
            if (name.includes('planner')) return `🗺️ ${formatted}`;
            if (name.includes('focus')) return `🎯 ${formatted}`;
            return `🤖 ${formatted}`;
        };

        data.workflow_runs.forEach(wr => {
            const displayAgentName = wr.agent_name ? formatAgentName(wr.agent_name) : 'Agent';
            
            const isTool = !!wr.tool_called;
            
            addTraceEvent(
                isTool ? 'tool_call' : 'agent_end',
                isTool ? '🔧' : '✅',
                `${displayAgentName} ${isTool ? 'executing tool: ' + wr.tool_called : 'finished processing'}`,
                isTool ? 'Tool execution' : 'Agent finished analysis',
                new Date(wr.created_at).toLocaleTimeString()
            );
        });

        switchTab('trace');
        showToast('📜', 'Loaded conversation from history');
    } catch (error) {
        showToast('❌', 'Failed to load conversation');
    }
}

// ── Tab Switching ──────────────────────────────────────────────

function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === tabName);
    });
    document.querySelectorAll('.tab-content').forEach(tc => {
        tc.classList.toggle('active', tc.id === `tab-${tabName}`);
    });
}

// ── Status ─────────────────────────────────────────────────────

function updateStatus(state, text) {
    statusText.textContent = text;
    statusDot.className = 'status-dot';
    if (state === 'processing') statusDot.classList.add('processing');
    if (state === 'error') statusDot.classList.add('error');
}

// ── Toast Notifications ────────────────────────────────────────

function showToast(icon, message, duration = 4000) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `
        <span class="toast-icon">${icon}</span>
        <span class="toast-text">${message}</span>
    `;
    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('toast-out');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}
