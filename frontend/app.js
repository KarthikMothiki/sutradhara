/**
 * Sūtradhāra — AI Productivity OS
 * High-Fidelity Frontend Logic
 */

// ── Configuration ──────────────────────────────────────────────
// Dynamically detect the backend URL (handles 8080, 8081, or Cloud Run)
const BACKEND_URL = window.location.origin;
const API_BASE = '/api/v1';
const WS_BASE = window.location.origin.replace('http://', 'ws://').replace('https://', 'wss://');

// ── State ──────────────────────────────────────────────────────
let ws = null;
let isProcessing = false;
const chatSessionId = (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') 
    ? crypto.randomUUID() 
    : Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);

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

// ── Multi-Modal Elements ──
const btnVoice = document.getElementById('btn-voice');
const btnUpload = document.getElementById('btn-upload');
const fileInput = document.getElementById('file-upload');

// ── Multi-Modal State ──
let currentAssistantMessageContent = null;
let uploadedImages = []; // Array of {name, base64, mime}
let isRecording = false;
let recognition = null;

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

    // ✨ Generate Strategy button — mode-aware
    const btnBriefing = document.getElementById('btn-briefing');
    if (btnBriefing) {
        btnBriefing.addEventListener('click', async () => {
            if (btnBriefing.disabled) return;
            btnBriefing.disabled = true;
            btnBriefing.textContent = '⏳ Analyzing...';
            try {
                await runTheLoom();
            } finally {
                // Reset button after 60s max (covers slow LLM)
                setTimeout(() => {
                    btnBriefing.disabled = false;
                    btnBriefing.textContent = '✨ Generate Strategy';
                }, 60000);
                // Also reset as soon as query completes
                const resetBtn = () => {
                    btnBriefing.disabled = false;
                    btnBriefing.textContent = '✨ Generate Strategy';
                };
                // Poll isProcessing to detect completion
                const checkDone = setInterval(() => {
                    if (!isProcessing) { resetBtn(); clearInterval(checkDone); }
                }, 1000);
            }
        });
    }

    // Demo Mode Button
    document.getElementById('btn-demo').addEventListener('click', runDemoSeed);

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

    // ── Multi-Modal Listeners (G7) ──
    btnVoice?.addEventListener('click', toggleVoiceRecognition);
    btnUpload?.addEventListener('click', () => fileInput?.click());
    fileInput?.addEventListener('change', handleFileUpload);
}

// ── Core Actions ───────────────────────────────────────────────

async function sendCommand() {
    const query = chatInput.value.trim();
    if (!query || isProcessing) return;

    isProcessing = true;
    updateStatus('processing', 'Orchestrating...');
    btnSend.disabled = true;

    // Reset streaming state
    currentAssistantMessageContent = null;

    // Add user message (visualize images if any)
    let displayHtml = `<p>${query.replace(/\n/g, '<br>')}</p>`;
    if (uploadedImages.length > 0) {
        displayHtml += '<div class="message-images">';
        uploadedImages.forEach(img => {
            displayHtml += `<img src="${img.base64}" class="chat-img-preview" title="${img.name}">`;
        });
        displayHtml += '</div>';
    }
    
    addChatMessage('user', displayHtml, true); // true = allow HTML
    
    const payload = { 
        query, 
        session_id: chatSessionId,
        images: uploadedImages.map(img => img.base64),
        notion_token: localStorage.getItem('notion_token'),
        notion_database_id: localStorage.getItem('notion_db_id')
    };

    chatInput.value = '';
    chatInput.style.height = 'auto';
    uploadedImages = []; // Clear queue
    updateUploadBadge();

    // Reset Canvas (except pinned briefing)
    clearCanvas(false);
    clearLoom();

    try {
        const response = await fetch(`${API_BASE}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
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

// ── G7 Multi-Modal Handlers ──

function handleFileUpload(e) {
    const files = Array.from(e.target.files);
    files.forEach(file => {
        const reader = new FileReader();
        reader.onload = (rev) => {
            uploadedImages.push({
                name: file.name,
                base64: rev.target.result,
                mime: file.type
            });
            updateUploadBadge();
            showToast('📎', `Attached ${file.name}`);
        };
        reader.readAsDataURL(file);
    });
}

function updateUploadBadge() {
    if (uploadedImages.length > 0) {
        btnUpload.classList.add('active');
        btnUpload.innerHTML = `📎<span class="badge-count">${uploadedImages.length}</span>`;
    } else {
        btnUpload.classList.remove('active');
        btnUpload.innerHTML = `📎`;
    }
}

function toggleVoiceRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        showToast('❌', 'Speech recognition not supported in this browser.');
        return;
    }

    if (isRecording) {
        recognition.stop();
        return;
    }

    isRecording = true;
    btnVoice.classList.add('active');
    updateStatus('listening', 'Listening...');

    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    
    // Clear the input when starting a new recording
    chatInput.value = '';

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        chatInput.value = transcript;
        showToast('🎙️', `Recognized: "${transcript}"`);
    };

    recognition.onend = () => {
        isRecording = false;
        btnVoice.classList.remove('active');
        updateStatus('ready', 'Ready');
        
        // G10 Polish: Auto-send ONLY when speech is fully processed and meaningful
        if (chatInput.value.trim().length > 8) {
            sendCommand();
        }
    };

    recognition.onerror = (err) => {
        console.error('Speech Error:', err.error || err);
        isRecording = false;
        btnVoice.classList.remove('active');
        updateStatus('ready', 'Ready');
    };

    recognition.start();
}

async function runDemoSeed() {
    const isLiveMode = document.getElementById('mode-badge')?.textContent?.includes('Live');
    if (isLiveMode) {
        showToast('ℹ️', 'Demo seeding skipped — Live Mode is active.');
        return;
    }
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
    const isLiveMode = document.getElementById('mode-badge')?.textContent?.includes('Live');

    if (isLiveMode) {
        // Live Mode: skip seeding, directly send briefing against real data
        chatMessages.innerHTML = '';
        traceTimeline.innerHTML = '';
        canvasContent.innerHTML = '<div id="briefing-anchor"></div>';
        showToast('🔗', 'Live Mode — briefing your real data...');
        chatInput.value = "Give me my daily briefing. Check my calendar for conflicts and cross-reference my high-priority Notion tasks.";
        await sendCommand();
        return;
    }

    // Demo Mode: full scripted showreel
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
            // Injecting Sequoia resolution draft.
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
                    <button class="btn-primary" onclick="resolveConflictDemo(this, ${data.overlap || 30})">Reschedule to resolve</button>
                    <button class="btn-secondary" onclick="this.closest('.canvas-card').remove()">Dismiss</button>
                </div>
            `);
            break;
            
        case 'IMPACT_UPDATE':
            updateImpact('conflicts', data.conflicts_resolved || 0, data.minutes_reclaimed || 0);
            updateImpact('tasks', data.tasks_updated || 0, data.minutes_reclaimed || 0);
            return; 
            
        case 'DRAFT_ACTION':
            content = renderDraftAction(data, data.description, data.action_id);
            break;

        case 'CALENDAR_DATA': {
            const events = data.events || [];
            const agentLabel = 'Calendar Specialist';
            if (!events.length) {
                content = `
                    <div class="card-header">
                        <span class="card-status">Calendar</span>
                        <span class="badge-pill status">Clear</span>
                    </div>
                    <div class="card-title">📅 Schedule Clear</div>
                    <div class="card-body" style="color:var(--text-muted)">No events found in the queried range. Your schedule is open.</div>
                `;
            } else {
                const eventRows = events.map(e => {
                    const start = e.start ? new Date(e.start).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';
                    const end = e.end ? new Date(e.end).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';
                    const attendeeCount = (e.attendees || []).length;
                    return `
                        <div class="event-row">
                            <div class="event-time-badge">
                                <span>${start}</span>
                                ${end ? `<span class="time-sep">→</span><span>${end}</span>` : ''}
                            </div>
                            <div class="event-info">
                                <div class="event-row-title">${e.title || e.summary || 'Untitled Event'}</div>
                                ${attendeeCount ? `<div class="event-row-meta">👥 ${attendeeCount} attendee${attendeeCount > 1 ? 's' : ''}</div>` : ''}
                            </div>
                        </div>`;
                }).join('');
                content = `
                    <div class="card-header">
                        <span class="card-status">Calendar Feed</span>
                        <span class="badge-pill date">${events.length} event${events.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="card-title">📅 Upcoming Schedule</div>
                    <div class="event-list">${eventRows}</div>
                `;
            }
            break;
        }

        case 'NOTION_TASKS': {
            const tasks = data.tasks || [];
            const priorityOrder = { 'high': 0, 'med': 1, 'medium': 1, 'low': 2, '': 3 };
            const sorted = [...tasks].sort((a, b) => 
                (priorityOrder[a.priority?.toLowerCase()] ?? 3) - (priorityOrder[b.priority?.toLowerCase()] ?? 3)
            );
            const taskRows = sorted.map(t => {
                const pClass = (t.priority || '').toLowerCase().startsWith('h') ? 'high'
                             : (t.priority || '').toLowerCase().startsWith('l') ? 'low' : 'med';
                return `
                    <div class="task-row">
                        <div class="task-checkbox"></div>
                        <div class="task-content">
                            <div class="task-title">${t.title}</div>
                            ${t.status ? `<div class="task-status-text">${t.status}</div>` : ''}
                        </div>
                        ${t.priority ? `<span class="badge-pill priority-${pClass}">${t.priority}</span>` : ''}
                    </div>`;
            }).join('');
            content = `
                <div class="card-header">
                    <span class="card-status">Notion Sync</span>
                    <span class="badge-pill date">${tasks.length} task${tasks.length !== 1 ? 's' : ''}</span>
                </div>
                <div class="card-title">📋 Task Priorities</div>
                <div class="task-list">${taskRows}</div>
            `;
            updateImpact('tasks', tasks.length);
            break;
        }

        default:
            // Fallback for unknown types — show raw JSON gracefully
            content = `
                <div class="card-header"><span class="card-status">${type}</span></div>
                <div class="card-title">Agent Output</div>
                <pre style="font-size:0.7rem;color:var(--text-muted);overflow:auto;max-height:200px">${JSON.stringify(data, null, 2)}</pre>
            `;
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

function renderD3Workflow(data) {
    const iconExpand = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>`;
    const iconCollapse = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>`;
    
    workflowContainer.innerHTML = `<div id="workflow-graph"><button id="btn-expand-graph" class="btn-expand-graph" title="Expand Graph">${iconExpand}</button></div>`;
    const container = document.getElementById('workflow-graph');
    let width = container.clientWidth;
    let height = container.clientHeight || 400;

    const svg = d3.select("#workflow-graph")
        .append("svg")
        .attr("width", "100%")
        .attr("height", "100%")
        .call(d3.zoom().on("zoom", (event) => {
            g.attr("transform", event.transform);
        }))
        .append("g");

    const g = svg.append("g");

    // Expand logic
    const btnExpand = document.getElementById('btn-expand-graph');
    const backdrop = document.getElementById('workflow-graph-backdrop');
    
    btnExpand.addEventListener('click', () => {
        container.classList.toggle('expanded');
        backdrop.classList.toggle('active');
        
        if (container.classList.contains('expanded')) {
            btnExpand.innerHTML = iconCollapse;
            btnExpand.title = "Collapse Graph";
        } else {
            btnExpand.innerHTML = iconExpand;
            btnExpand.title = "Expand Graph";
        }
        
        // Re-center after transition
        setTimeout(() => {
            simulation.alpha(0.3).restart();
        }, 300);
    });
    
    backdrop.addEventListener('click', () => {
        container.classList.remove('expanded');
        backdrop.classList.remove('active');
        btnExpand.innerHTML = iconExpand;
        btnExpand.title = "Expand Graph";
    });

    const simulation = d3.forceSimulation(data.nodes)
        .force("link", d3.forceLink(data.links).id(d => d.id).distance(120))
        .force("charge", d3.forceManyBody().strength(-400))
        .force("center", d3.forceCenter(width / 2, height / 2));

    // Add marker for arrows
    svg.append("defs").append("marker")
        .attr("id", "arrowhead")
        .attr("viewBox", "-0 -5 10 10")
        .attr("refX", 20)
        .attr("refY", 0)
        .attr("orient", "auto")
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("xoverflow", "visible")
        .append("svg:path")
        .attr("d", "M 0,-5 L 10 ,0 L 0,5")
        .attr("fill", "#94a3b8")
        .style("stroke", "none");

    const link = g.append("g")
        .attr("class", "links")
        .selectAll("line")
        .data(data.links)
        .enter().append("line")
        .attr("class", "d3-link")
        .attr("marker-end", "url(#arrowhead)");

    const node = g.append("g")
        .attr("class", "nodes")
        .selectAll("g")
        .data(data.nodes)
        .enter().append("g")
        .attr("class", d => `d3-node node-${d.type}`)
        .on("click", (event, d) => {
            d3.selectAll(".d3-node circle").style("stroke-width", "2px");
            d3.select(event.currentTarget).select("circle").style("stroke-width", "4px");
            filterLoomLogs(d.type === 'start' || d.type === 'end' ? 'manager' : d.type);
        })
        .call(d3.drag()
            .on("start", dragstarted)
            .on("drag", dragged)
            .on("end", dragended));

    node.append("circle")
        .attr("r", 10)
        .style("filter", "drop-shadow(0 0 5px rgba(0,0,0,0.2))");

    node.append("text")
        .attr("class", "d3-label")
        .attr("dx", 15)
        .attr("dy", ".35em")
        .text(d => d.label)
        .style("font-weight", d => (d.type === 'start' || d.type === 'end') ? "700" : "400");

    simulation.on("tick", () => {
        link
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);

        node
            .attr("transform", d => `translate(${d.x},${d.y})`);
    });

    function dragstarted(event, d) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }

    function dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }

    function dragended(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }
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

function addChatMessage(role, text, isHtml = false) {
    const msg = document.createElement('div');
    msg.className = `message message-${role}`;
    const content = isHtml ? text : text.replace(/\n/g, '<br>');
    msg.innerHTML = `
        <div class="message-content">
            <p>${content}</p>
        </div>
    `;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ── G8 Streaming Handler ──

function handleResponseChunk(text) {
    if (!currentAssistantMessageContent) {
        // Create new assistant message bubble
        const msg = document.createElement('div');
        msg.className = 'message message-assistant';
        msg.innerHTML = `
            <div class="message-content">
                <p></p>
            </div>
        `;
        chatMessages.appendChild(msg);
        currentAssistantMessageContent = msg.querySelector('p');
        
        // Hide processing indicator once streaming starts
        updateStatus('ready', 'Streaming...');
    }
    
    // Append text with basic line-break handling
    // For production, a real markdown renderer would be used here
    currentAssistantMessageContent.innerHTML += text.replace(/\n/g, '<br>');
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function clearCanvas(force = true) {
    if (force) {
        canvasContent.innerHTML = '<div id="briefing-anchor"></div>';
    } else {
        const briefing = document.getElementById('daily-briefing-card');
        canvasContent.innerHTML = '';
        canvasContent.innerHTML = '<div id="briefing-anchor"></div>';
        if (briefing) {
            const anchor = document.getElementById('briefing-anchor');
            anchor.appendChild(briefing);
        }
    }
}

function clearLoom() {
    traceTimeline.innerHTML = '';
}

function updateImpact(key, val, reclaimedMinutes = 0) {
    const startValue = impactMetrics[key];
    impactMetrics[key] += val;
    
    // Use factual reclaimedMinutes if provided, otherwise fallback to realistic defaults
    if (reclaimedMinutes > 0) {
        impactMetrics.minutes += reclaimedMinutes;
    } else {
        if (key === 'conflicts') impactMetrics.minutes += val * 15; // Avg conflict resolution time
        if (key === 'tasks') impactMetrics.minutes += val * 5;      // Avg admin time per task
    }
    
    animateNumber(`stat-conflicts`, startValue, impactMetrics.conflicts);
    animateNumber(`stat-tasks`, startValue, impactMetrics.tasks);
    animateNumber(`stat-minutes`, startValue, impactMetrics.minutes);
}

function animateNumber(id, start, end) {
    const obj = document.getElementById(id);
    if (!obj) return;
    
    // Trigger pop animation
    obj.classList.remove('stat-update');
    void obj.offsetWidth; // Force reflow
    obj.classList.add('stat-update');

    let current = start;
    const duration = 800;
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
    const isRetry = btn.textContent.includes('Retry');
    btn.disabled = true;
    btn.textContent = 'Executing...';
    
    try {
        // If retrying a rejected action, reset it first
        if (isRetry) {
            await fetch(`${API_BASE}/actions/${actionId}/reset`, { method: 'POST' });
        }

        const response = await fetch(`${API_BASE}/actions/${actionId}/approve`, { method: 'POST' });
        const data = await response.json();
        
        if (data.error) throw new Error(data.error);

        // Mark card as executed
        card.style.borderColor = 'var(--agent-planner)';
        const badge = card.querySelector('.badge, .badge-pill');
        if (badge) {
            badge.textContent = '✓ Executed';
            badge.style.background = 'rgba(16, 185, 129, 0.15)';
            badge.style.color = '#10b981';
        }
        card.querySelectorAll('.card-actions button').forEach(b => b.remove());
        
        showToast('✅', 'Action executed & logged.');
        const reclaimed = 10;
        updateImpact('tasks', 1, reclaimed);
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

function resolveConflictDemo(btn, overlap = 15) {
    const visual = btn.closest('.canvas-card').querySelector('.conflict-visual');
    btn.disabled = true;
    btn.textContent = 'Rescheduling...';
    
    setTimeout(() => {
        if (visual) {
            visual.classList.add('resolved');
            const items = visual.querySelectorAll('.conflict-item');
            if (items.length > 1) {
                items[1].querySelector('span').textContent = 'Client Review (Moved)';
                items[1].querySelector('.conflict-time').textContent = '11:00 - 11:45';
            }
        }
        
        btn.closest('.canvas-card').querySelector('.badge').textContent = 'Resolved';
        btn.closest('.canvas-card').querySelector('.badge').style.color = 'var(--agent-planner)';
        btn.remove();
        
        // Factual: each resolved conflict reclaims the actual overlap minutes
        updateImpact('conflicts', 1, overlap);
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
        case 'loom_event':
            addLoomEvent(agent, ev.data.type, ev.data.text);
            break;
        case 'workflow_diagram':
            if (ev.data.json_data) {
                renderD3Workflow(ev.data.json_data);
            } else {
                renderWorkflow(ev.data.diagram);
            }
            break;
        case 'response_chunk':
            handleResponseChunk(ev.data.text);
            break;
    }
}

function addLoomThought(agent, thought) {
    addLoomEvent(agent, 'THOUGHT', thought);
}

function addLoomEvent(agent, type, text) {
    const entry = document.createElement('div');
    const typeClass = type.toLowerCase();
    entry.className = `loom-log-entry ${typeClass}`;
    entry.dataset.agent = agent;
    
    let icon = '🧠';
    if (type === 'HANDOFF') icon = '🤝';
    if (type === 'RESEARCH') icon = '🛰️';
    if (type === 'ACTION') icon = '🎬';

    entry.innerHTML = `
        <div class="loom-log-indicator" style="background:var(--primary)"></div>
        <div class="log-body">
            <div class="log-title">${icon} ${type}</div>
            <div class="log-meta">${text}</div>
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
                if (currentAssistantMessageContent) {
                    // Final sync to ensure markdown/formatting is complete
                    currentAssistantMessageContent.innerHTML = data.final_response.replace(/\n/g, '<br>');
                } else {
                    addChatMessage('assistant', data.final_response);
                }
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
    
    // Parse description for markdown-like bolding
    let desc = (description || '').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // Extract structured data from description or data payload
    const priority = data.priority || '';
    const dueDate = data.due_date || data.deadline || '';
    const status = data.status || '';
    
    // Split description into "What" and "Insight" if it contains the insight header
    let insightHtml = '';
    if (desc.includes('Proactive Insight:')) {
        const parts = desc.split('Proactive Insight:');
        desc = parts[0];
        insightHtml = `
            <div class="card-insight">
                <span class="insight-icon">💡</span>
                <span class="insight-text">${parts[1]}</span>
            </div>
        `;
    }

    // Build structured badges
    let badgesHtml = '';
    if (priority) badgesHtml += `<span class="badge-pill priority-${priority.toLowerCase()}">${priority}</span>`;
    if (dueDate) badgesHtml += `<span class="badge-pill date"><i class="far fa-calendar"></i> ${dueDate}</span>`;
    if (status) badgesHtml += `<span class="badge-pill status">${status}</span>`;

    return `
        <div class="card-header">
            <span class="card-status">Staged Action</span>
            <div class="card-badges">${badgesHtml}</div>
        </div>
        <div class="card-title">${data.title || 'Proposed Update'}</div>
        <div class="card-body">${desc}</div>
        ${insightHtml}
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
    
    historyList.innerHTML = '<div class="text-muted" style="text-align:center; padding:20px;">Fetching history...</div>';

    try {
        // API returns { conversations: [...], total, page, per_page }
        const response = await fetch(`${API_BASE}/history?per_page=30`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        const sessions = data.conversations || [];

        if (sessions.length === 0) {
            historyList.innerHTML = '<div class="text-muted" style="text-align:center; padding:20px;">No past sessions found.</div>';
            return;
        }
        
        historyList.innerHTML = sessions.map(item => {
            const d = new Date(item.created_at);
            const dateStr = d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
            const statusClass = item.status === 'completed' ? 'status-ok' : item.status === 'failed' ? 'status-err' : 'status-pending';
            const query = item.user_query || 'Unnamed workflow';
            const truncated = query.length > 55 ? query.substring(0, 52) + '...' : query;
            return `
                <div class="history-item" onclick="loadHistorySession('${item.id}')">
                    <div style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
                        <span class="date" style="font-size:0.65rem; color:var(--text-muted); white-space:nowrap;">${dateStr}</span>
                        <span class="badge-pill ${statusClass}" style="font-size:0.55rem; padding:2px 6px;">${item.status}</span>
                    </div>
                    <span class="query" style="display:block; margin-top:4px; font-size:0.75rem;">${truncated}</span>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('History fetch error:', e);
        historyList.innerHTML = '<div class="text-muted" style="text-align:center; padding:20px;">Failed to load history.</div>';
    }
}

async function loadHistorySession(id) {
    try {
        // Switch back to Command tab to show the loaded session
        document.getElementById('tab-chat').click();
        showToast('📂', 'Loading session...');

        const res = await fetch(`${API_BASE}/query/${id}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // Clear chat and show the historical exchange
        chatMessages.innerHTML = '';
        addChatMessage('user', data.user_query || 'Previous query');
        if (data.final_response) {
            addChatMessage('assistant', data.final_response);
        }
        clearCanvas();
        clearLoom();
        showToast('✅', 'Session loaded.');
    } catch (e) {
        showToast('❌', 'Could not load that session.');
    }
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

async function initSettings() {
    // Pre-populate from localStorage (user-saved overrides)
    document.getElementById('input-notion-token').value = localStorage.getItem('notion_token') || '';
    document.getElementById('input-notion-db').value = localStorage.getItem('notion_db_id') || '';

    try {
        const res = await fetch(`${API_BASE}/config`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const config = await res.json();

        const checkDemo = document.getElementById('check-demo-mode');
        if (checkDemo) checkDemo.checked = config.demo_mode;
        updateModeBadge(config.demo_mode);

        // ── Auto-credential injection for localhost Live Mode ──
        // When the backend reports Live mode AND has credentials loaded from .env,
        // we don't need the user to paste them manually — show a green indicator instead.
        if (!config.demo_mode) {
            const notionTokenInput = document.getElementById('input-notion-token');
            const notionDbInput    = document.getElementById('input-notion-db');

            if (config.notion_token_present && !notionTokenInput.value) {
                notionTokenInput.placeholder = '✅ Loaded from server .env';
                notionTokenInput.style.borderColor = '#10B981';
            }
            if (config.notion_db_present && !notionDbInput.value) {
                notionDbInput.placeholder = '✅ Loaded from server .env';
                notionDbInput.style.borderColor = '#10B981';
            }

            // Show a toast only on first load (not every time)
            if (!sessionStorage.getItem('livemode_toast_shown')) {
                sessionStorage.setItem('livemode_toast_shown', '1');
                showToast('🔗', 'Live Mode: using your real Google Calendar & Notion data.');
            }
        }
    } catch (err) {
        console.error('Config fetch error', err);
    }
}

function updateModeBadge(isDemo) {
    const badge = document.getElementById('mode-badge');
    if (!badge) return;
    if (isDemo) {
        badge.textContent = 'Demo Mode';
        badge.style.background = 'var(--agent-planner)';
    } else {
        badge.textContent = 'Live Mode 🔗';
        badge.style.background = '#10B981';
    }
}

async function saveSettings() {
    const token = document.getElementById('input-notion-token').value;
    const dbId = document.getElementById('input-notion-db').value;
    const isDemo = document.getElementById('check-demo-mode').checked;
    
    localStorage.setItem('notion_token', token);
    localStorage.setItem('notion_db_id', dbId);
    
    try {
        // Sync demo mode to backend
        const response = await fetch(`${API_BASE}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ demo_mode: isDemo })
        });
        const config = await response.json();
        updateModeBadge(config.demo_mode);
        showToast('⚙️', `Settings saved. ${config.demo_mode ? 'Demo' : 'Live'} mode active.`);
    } catch (e) {
        showToast('❌', 'Failed to sync mode to backend.');
    }
    
    document.getElementById('modal-settings').classList.remove('active');
}
