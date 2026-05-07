/**
 * GraphRAG Research Assistant â€” Frontend Logic
 * Handles chat, sources panel, health checks, and history
 */

// CONFIG & STATE

const API_BASE = window.location.origin;

const state = {
    conversations: [],
    currentConversation: null,
    messages: [],
    isLoading: false,
    sourcesOpen: false,
    attachMenuOpen: false,
    lastResponse: null,
    messageData: new Map(), // Store data for each assistant message for syncing
    pendingAttachments: [],
};

// DOM REFS

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const els = {
    sidebar: document.getElementById('sidebar'),
    sidebarToggle: document.getElementById('sidebarToggle'),
    mobileMenuBtn: document.getElementById('mobileMenuBtn'),
    pipelineStep: document.getElementById('pipelineStep'),

    // Chat components
    chatContainer: document.getElementById('chatContainer'),
    historyList: $('#historyList'),
    topK: $('#topK'),
    topKValue: $('#topKValue'),
    minSim: $('#minSim'),
    minSimValue: $('#minSimValue'),
    modelSelect: $('#modelSelect'),
    verifyToggle: $('#verifyToggle'),
    groundedStudyToggle: $('#groundedStudyToggle'),
    healthBtn: $('#healthBtn'),
    connectionStatus: $('#connectionStatus'),
    chatMessages: $('#chatMessages'),
    welcomeScreen: $('#welcomeScreen'),
    queryInput: $('#queryInput'),
    sendBtn: $('#sendBtn'),
    charCount: $('#charCount'),
    attachmentTray: $('#attachmentTray'),
    attachMenuBtn: $('#attachMenuBtn'),
    attachMenu: $('#attachMenu'),
    attachmentFileInput: $('#attachmentFileInput'),
    sourcesPanel: $('#sourcesPanel'),
    sourcePanelToggle: $('#sourcePanelToggle'),
    sourcesPanelClose: $('#sourcesPanelClose'),
    sourcesContent: $('#sourcesContent'),
    pdfFileInput: $('#pdfFileInput'),
    videoFileInput: $('#videoFileInput'),
    healthModal: $('#healthModal'),
    healthModalClose: $('#healthModalClose'),
    healthModalBody: $('#healthModalBody'),
    clearHistoryBtn: $('#clearHistoryBtn'),
};

window.messageDataStore = {};
function restoreSourcesData(msgId) {
    const data = state.messageData.get(msgId) || window.messageDataStore[msgId];
    if (data) {
        openSourcesPanel();
        setTimeout(() => {
            updateSourcesPanel(data);
        }, 50);
    }
}

// INIT

document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    checkHealth();
    loadHistory();
    renderAttachmentTray();
    els.queryInput.focus();
});

// Panel Resizer Logic
document.addEventListener('DOMContentLoaded', () => {
    const resizer = document.getElementById('panelResizer');
    const sourcesPanel = document.getElementById('sourcesPanel');
    const body = document.body;

    if (!resizer || !sourcesPanel) return;

    let isResizing = false;

    resizer.addEventListener('mousedown', (e) => {
        isResizing = true;
        resizer.classList.add('active');
        body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        let newWidth = window.innerWidth - e.clientX;
        if (newWidth < 300) newWidth = 300;
        if (newWidth > 800) newWidth = 800;

        document.documentElement.style.setProperty('--sources-width', newWidth + 'px');
        sourcesPanel.style.width = newWidth + 'px';

        if (sourcesPanel.classList.contains('open') && window.lastGraphPapers) {
            clearTimeout(window.resizeGraphTimeout);
            window.resizeGraphTimeout = setTimeout(() => {
                if (document.getElementById('tabGraph').classList.contains('active')) {
                    renderGraph(window.lastGraphPapers);
                }
            }, 100);
        }
    });

    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            resizer.classList.remove('active');
            body.style.cursor = 'default';
            document.body.style.userSelect = 'auto';
        }
    });
});

function initEventListeners() {
    // Sidebar
    els.sidebarToggle.addEventListener('click', toggleSidebar);
    if (els.mobileMenuBtn) {
        els.mobileMenuBtn.addEventListener('click', () => {
            els.sidebar.classList.remove('collapsed');
        });
    }

    // Settings
    els.topK.addEventListener('input', () => {
        els.topKValue.textContent = els.topK.value;
    });
    els.minSim.addEventListener('input', () => {
        els.minSimValue.textContent = (els.minSim.value / 100).toFixed(2);
    });

    // Input
    els.queryInput.addEventListener('input', handleInputChange);
    els.queryInput.addEventListener('keydown', handleInputKeydown);
    els.sendBtn.addEventListener('click', sendQuery);
    if (els.groundedStudyToggle) {
        els.groundedStudyToggle.addEventListener('change', syncStudyGuardrails);
    }

    // Sources panel
    els.sourcePanelToggle.addEventListener('click', toggleSourcesPanel);
    els.sourcesPanelClose.addEventListener('click', () => {
        setSourcesPanelOpen(false);
    });

    // Source tabs
    $$('.sources-tab').forEach(tab => {
        tab.addEventListener('click', () => switchSourceTab(tab.dataset.tab));
    });

    // Health modal
    els.healthBtn.addEventListener('click', showHealthModal);
    els.healthModalClose.addEventListener('click', () => {
        els.healthModal.classList.remove('visible');
    });
    els.healthModal.addEventListener('click', (e) => {
        if (e.target === els.healthModal) els.healthModal.classList.remove('visible');
    });

    // Welcome cards
    $$('.welcome-card').forEach(card => {
        card.addEventListener('click', () => {
            els.queryInput.value = card.dataset.query;
            handleInputChange();
            sendQuery();
        });
    });

    $$('.study-prompt-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            els.queryInput.value = chip.dataset.studyPrompt;
            handleInputChange();
            els.queryInput.focus();
        });
    });

    if (els.attachMenuBtn) {
        els.attachMenuBtn.addEventListener('click', (event) => {
            event.stopPropagation();
            setAttachMenuOpen(!state.attachMenuOpen);
        });
    }

    if (els.attachMenu) {
        els.attachMenu.querySelectorAll('.attach-menu-item').forEach(item => {
            item.addEventListener('click', () => {
                handleAttachAction(item.dataset.attachAction);
            });
        });
    }

    if (els.attachmentFileInput) {
        els.attachmentFileInput.addEventListener('change', (event) => {
            processSelectedFiles(event.target.files);
            event.target.value = '';
        });
    }

    if (els.pdfFileInput) {
        els.pdfFileInput.addEventListener('change', (event) => {
            processSelectedFiles(event.target.files, { onlyPdf: true });
            event.target.value = '';
        });
    }

    if (els.videoFileInput) {
        els.videoFileInput.addEventListener('change', (event) => {
            processSelectedFiles(event.target.files, { onlyVideo: true });
            event.target.value = '';
        });
    }

    document.addEventListener('click', (event) => {
        if (!state.attachMenuOpen) return;
        const clickInsideMenu = els.attachMenu?.contains(event.target);
        const clickOnButton = els.attachMenuBtn?.contains(event.target);
        if (!clickInsideMenu && !clickOnButton) {
            setAttachMenuOpen(false);
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && state.attachMenuOpen) {
            setAttachMenuOpen(false);
            els.queryInput.focus();
        }
    });

    // Theme toggle
    const themeBtn = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');

    function updateThemeIcon(theme) {
        if (!themeIcon) return;
        if (theme === 'light') {
            themeIcon.innerHTML = `<circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>`;
        } else {
            themeIcon.innerHTML = `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>`;
        }
    }

    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });
    }

    // Clear History
    if (els.clearHistoryBtn) {
        els.clearHistoryBtn.addEventListener('click', () => {
            if (confirm('Clear all conversation history?')) {
                state.conversations = [];
                localStorage.removeItem('graphrag_history');
                renderHistory();
            }
        });
    }
}

// SIDEBAR

function toggleSidebar() {
    els.sidebar.classList.toggle('collapsed');
}

// SOURCES PANEL

function toggleSourcesPanel() {
    setSourcesPanelOpen(!state.sourcesOpen);
}

function openSourcesPanel() {
    setSourcesPanelOpen(true);
}

function setSourcesPanelOpen(isOpen) {
    state.sourcesOpen = isOpen;
    els.sourcesPanel.classList.toggle('open', isOpen);
    document.body.classList.toggle('sources-open', isOpen);
}

function switchSourceTab(tabName) {
    $$('.sources-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabName));
    $$('.sources-tab-content').forEach(c => c.classList.remove('active'));
    $(`#tab${tabName.charAt(0).toUpperCase() + tabName.slice(1)}`).classList.add('active');
}

function setAttachMenuOpen(isOpen) {
    state.attachMenuOpen = isOpen;
    if (els.attachMenu) {
        els.attachMenu.classList.toggle('open', isOpen);
        els.attachMenu.setAttribute('aria-hidden', String(!isOpen));
    }
    if (els.attachMenuBtn) {
        els.attachMenuBtn.setAttribute('aria-expanded', String(isOpen));
        els.attachMenuBtn.classList.toggle('active', isOpen);
    }
}

function handleAttachAction(action) {
    switch (action) {
        case 'files':
            els.attachmentFileInput?.click();
            break;
        case 'pdf':
            els.pdfFileInput?.click();
            break;
        case 'video':
            els.videoFileInput?.click();
            break;
        case 'deep-research':
            els.modelSelect.value = 'heavy';
            els.verifyToggle.checked = true;
            if (els.groundedStudyToggle) {
                els.groundedStudyToggle.checked = true;
            }
            break;
        default:
            break;
    }
    setAttachMenuOpen(false);
}

function processSelectedFiles(fileList, opts = {}) {
    const files = Array.from(fileList || []);
    if (!files.length) return;

    const pdfFiles = opts.onlyVideo
        ? []
        : files.filter(file => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'));

    const attachmentFiles = opts.onlyPdf
        ? []
        : files.filter(file => !pdfFiles.includes(file));

    if (pdfFiles.length) {
        stagePdfFiles(pdfFiles);
    }
    if (attachmentFiles.length) {
        addPendingAttachments(attachmentFiles);
    }
}

function addPendingAttachments(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;

    const known = new Set(state.pendingAttachments.map(item => `${item.name}-${item.size}-${item.mime}`));
    files.forEach(file => {
        const key = `${file.name}-${file.size}-${file.type}`;
        if (known.has(key)) return;
        state.pendingAttachments.push({
            id: `att-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            name: file.name,
            size: file.size,
            mime: file.type || 'application/octet-stream',
        });
    });

    renderAttachmentTray();
}

function renderAttachmentTray() {
    if (!els.attachmentTray) return;

    if (!state.pendingAttachments.length) {
        els.attachmentTray.classList.remove('visible');
        els.attachmentTray.innerHTML = '';
        return;
    }

    els.attachmentTray.classList.add('visible');
    els.attachmentTray.innerHTML = state.pendingAttachments.map(file => {
        let kind = 'file';
        if (file.mime.startsWith('image/')) kind = 'image';
        if (file.mime.startsWith('video/')) kind = 'video';
        if (file.mime === 'application/pdf') kind = 'PDF document';
        if (file.name.endsWith('.docx') || file.name.endsWith('.doc')) kind = 'Word document';

        return `
            <div class="attachment-card">
                <div class="attachment-icon-box">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path>
                        <polyline points="13 2 13 9 20 9"></polyline>
                    </svg>
                </div>
                <div class="attachment-info">
                    <span class="attachment-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
                    <span class="attachment-type">${kind}</span>
                </div>
                <button class="attachment-remove" data-attachment-id="${file.id}" aria-label="Remove attachment">×</button>
            </div>
        `;
    }).join('');

    els.attachmentTray.querySelectorAll('.attachment-remove').forEach(button => {
        button.addEventListener('click', () => {
            state.pendingAttachments = state.pendingAttachments.filter(file => file.id !== button.dataset.attachmentId);
            renderAttachmentTray();
        });
    });
}


function syncStudyGuardrails() {
    // Deprecated
}

function formatFileSize(sizeBytes) {
    if (!sizeBytes) return '0 MB';
    const mb = sizeBytes / (1024 * 1024);
    return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`;
}

// D3 GRAPH ENGINE
function renderGraph(papers) {
    const svg = d3.select("#graphSvg");
    svg.selectAll("*").remove();

    if (!papers || papers.length === 0) {
        document.getElementById('graphEmpty').style.display = 'flex';
        document.getElementById('graphContainer').style.display = 'none';
        return;
    }

    document.getElementById('graphEmpty').style.display = 'none';
    document.getElementById('graphContainer').style.display = 'block';

    window.lastGraphPapers = papers;

    // Remove legacy toggle if it exists
    const legacyBtn = document.getElementById('timelineToggleBtn');
    if (legacyBtn) legacyBtn.remove();

    const width = document.getElementById('sourcesPanel').clientWidth - 40;
    const height = 350;
    const g = svg.append("g");

    // Add zoom
    const zoom = d3.zoom().scaleExtent([0.5, 4]).on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);

    document.getElementById('resetGraph').onclick = () => {
        svg.transition().duration(750).call(zoom.transform, d3.zoomIdentity);
    };

    const nodes = papers.map(p => ({
        id: p.id || p.title || `paper-${Math.random()}`,
        title: p.title || 'Untitled',
        author: Array.isArray(p.authors) ? p.authors[0] : (p.author || 'Unknown'),
        domain: (Array.isArray(p.categories) && p.categories[0]) || p.domain || 'General',
        year: parseInt(p.year) || 2020,
        radius: 8 + Math.min((p.citations || 5) / 2, 8)
    }));

    // Force-directed knowledge graph
    const links = [];
    for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
            if (nodes[i].domain === nodes[j].domain) {
                links.push({ source: nodes[i].id, target: nodes[j].id, value: 1 });
            }
        }
    }

    const simulation = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(links).id(d => d.id).distance(160))
        .force("charge", d3.forceManyBody().strength(-400))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collision", d3.forceCollide().radius(d => d.radius + 30));

    // Link lines with gradient
    const link = g.append("g")
        .attr("stroke", "rgba(255,255,255,0.12)")
        .attr("stroke-width", 1.5)
        .selectAll("line")
        .data(links)
        .enter().append("line");

    const node = g.append("g")
        .selectAll("g")
        .data(nodes)
        .enter().append("g")
        .call(d3.drag()
            .on("start", (event, d) => {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x; d.fy = d.y;
            })
            .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
            .on("end", (event, d) => {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null; d.fy = null;
            }));

    // Glow ring
    node.append("circle")
        .attr("r", d => d.radius + 4)
        .attr("fill", "none")
        .attr("stroke", d => getColorForDomain(d.domain))
        .attr("stroke-width", 1)
        .style("opacity", 0.25);

    // Main node circle
    node.append("circle")
        .attr("r", d => d.radius)
        .attr("fill", d => getColorForDomain(d.domain))
        .attr("stroke", "rgba(255,255,255,0.8)")
        .attr("stroke-width", 2)
        .style("cursor", "pointer");

    node.append("text")
        .attr("dy", d => d.radius + 18)
        .attr("text-anchor", "middle")
        .style("fill", "var(--text-primary)")
        .style("font-size", "10px")
        .style("font-weight", "600")
        .style("text-shadow", "0px 1px 4px rgba(0,0,0,0.9), 0px 0px 2px rgba(0,0,0,1)")
        .text(d => (d.title && d.title.length > 22) ? d.title.substring(0, 22) + "..." : (d.title || 'Untitled'));

    node.append("title").text(d => `${d.title}\n${d.author} (${d.year})`);

    // Hover effects
    node.on("mouseover", function () {
        d3.select(this).select("circle:nth-child(2)").attr("stroke-width", 3).attr("stroke", "#a78bfa");
        d3.select(this).select("circle:nth-child(1)").style("opacity", 0.6);
    }).on("mouseout", function () {
        d3.select(this).select("circle:nth-child(2)").attr("stroke-width", 2).attr("stroke", "rgba(255,255,255,0.8)");
        d3.select(this).select("circle:nth-child(1)").style("opacity", 0.25);
    });

    simulation.on("tick", () => {
        link.attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);
        node.attr("transform", d => `translate(${d.x},${d.y})`);
    });
}

function getColorForDomain(domain) {
    const map = {
        'Machine Learning': '#6366f1',
        'Vision': '#14b8a6',
        'NLP': '#f59e0b',
        'Robotics': '#ef4444',
        'Med-AI': '#ec4899'
    };
    return map[domain] || '#64748b';
}

function updateSourcesPanel(data) {
    const chunksData = data.chunks || (data.source_nodes && data.source_nodes.evidence_chunks) || [];
    const papersData = data.papers || (data.source_nodes && data.source_nodes.papers) || [];
    const reasoningPath = data.reasoning_path || (data.plan && data.plan.reasoning_path) || 'Evaluated context, identified relevant entities, synthesized final answer using cross-referenced knowledge.';
    const routeIntent = data.intent || data.route || '';

    // Reasoning embedded in Overview Container to look better
    const overviewContainer = document.getElementById('sourcesOverviewContainer');
    if (overviewContainer) {
        overviewContainer.innerHTML = `
            <div class="reasoning-card gemini-style-card dismissible-card">
                <button class="card-dismiss-btn" onclick="this.parentElement.style.display='none'" title="Dismiss">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
                <div class="reasoning-title" style="display: flex; align-items: center; gap: 8px; font-weight: 600; color: var(--primary-light); margin-bottom: 8px;">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
                    Aether Reasoning Process
                </div>
                <div class="reasoning-text" style="color: var(--text-secondary); font-size: 13px; line-height: 1.5;">${escapeHtml(reasoningPath)}</div>
                ${routeIntent ? `<div class="reasoning-tag" style="margin-top: 10px; font-size: 11px; padding: 4px 8px; background: var(--accent-subtle); border-radius: 4px; display: inline-block; color: var(--primary-light);">Route identified as: <strong>${routeIntent}</strong></div>` : ''}
            </div>
        `;
    }

    // Chunks (Smart Highlights -> Intelligence Extraction)
    const chunkList = document.getElementById('tabChunks');
    chunkList.innerHTML = chunksData.length > 0
        ? '<div class="extracted-insights-timeline">' + chunksData.map((c, idx) => {
            const fullText = c.chunk || c.text || c.content || '';
            const title = c.title || c.paper_title || 'Unknown Paper';
            const pageInfo = c.page ? `Page ${c.page}` : 'Section Match';
            const simScore = c.similarity ? (c.similarity * 100).toFixed(0) : 'High';
            
            // Format markdown text to html, ensuring no XSS but keeping the representation clean
            let formattedText = window.marked ? marked.parse(fullText) : escapeHtml(fullText);

            return `
            <div class="insight-node" style="margin-bottom: 20px; padding: 18px; border-radius: 12px; background: var(--bg-paper); border: 1px solid var(--surface-glass-border); box-shadow: var(--shadow-sm);">
                <div class="insight-header" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; border-bottom: 1px solid var(--surface-glass-border); padding-bottom: 12px;">
                    <div style="display: flex; gap: 12px; align-items: center;">
                        <span style="display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; background: var(--primary); color: white; border-radius: 50%; font-size: 12px; font-weight: 600;">${idx + 1}</span>
                        <div>
                            <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-tertiary);">Source Material</span>
                            <h4 style="margin: 2px 0 0 0; color: var(--text-primary); font-size: 14px; font-weight: 600;">${escapeHtml(title)}</h4>
                        </div>
                    </div>
                </div>
                
                <div class="insight-metadata" style="display: flex; gap: 8px; margin-bottom: 16px;">
                    <span style="background: var(--bg-accent); color: var(--text-secondary); padding: 4px 10px; border-radius: 6px; font-size: 11px; font-family: var(--font-mono); display: flex; align-items: center; gap: 4px;">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                        ${escapeHtml(pageInfo)}
                    </span>
                    <span style="background: rgba(52, 211, 153, 0.1); color: var(--accent-emerald); padding: 4px 10px; border-radius: 6px; font-size: 11px; font-family: var(--font-mono); display: flex; align-items: center; gap: 4px;">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle></svg>
                        ${escapeHtml(simScore)}% Match
                    </span>
                </div>
                
                <div class="insight-content-data" style="background: var(--bg-elevated); padding: 14px; border-radius: 8px; border-left: 3px solid var(--accent-cyan); overflow-y: auto; max-height: 250px;">
                    <div style="font-size: 10px; font-weight: 600; text-transform: uppercase; color: var(--accent-cyan); margin-bottom: 8px; letter-spacing: 0.5px; position: sticky; top: 0; background: var(--bg-elevated); padding-bottom: 4px; z-index: 2;">Extracted Chunk Data</div>
                    <div class="chunk-markdown-content" style="color: var(--text-secondary); font-size: 13px; line-height: 1.6; font-family: var(--font-sans);">
                        ${formattedText}
                    </div>
                </div>
            </div>
            `;
        }).join('') + '</div>'
        : '<div class="sources-empty">No extracted knowledge found.</div>';

    // Papers
    const paperList = document.getElementById('tabPapers');
    
    let compareBtnHtml = '';
    if (papersData.length > 1) {
        window.lastFetchedPapers = papersData;
        compareBtnHtml = `<div style="margin-bottom: 15px; text-align: center;">
            <button class="quick-action-btn" onclick="openCompareDrawer(window.lastFetchedPapers)" style="background: rgba(99, 102, 241, 0.2); color: white; border-color: var(--primary); padding: 8px 16px; font-size: 13px;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
                Compare All Papers
            </button>
        </div>`;
    }

    paperList.innerHTML = compareBtnHtml + (papersData.length > 0
        ? papersData.map(p => {
            const authorsList = Array.isArray(p.authors) ? p.authors.join(', ') : (p.authors || p.author || 'Unknown');
            const catList = Array.isArray(p.categories) && p.categories.length > 0 ? p.categories[0] : (p.domain || 'General');
            const paperUrl = p.url ? `<a href="${escapeHtml(p.url)}" target="_blank" class="paper-url" rel="noopener noreferrer"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg> View Paper</a>` : '';
            const paperId = p.id || p.title;
            const isPinned = window.pinnedPapers && window.pinnedPapers.has(paperId);
            return `
            <div class="source-card paper premium-card" style="position:relative;">
                <div class="paper-pin-checkbox ${isPinned ? 'pinned' : ''}" data-paper-id="${escapeHtml(paperId)}" onclick="togglePinPaper('${escapeHtml(paperId).replace(/'/g, "\\'")}')"
                     title="Pin to compare">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"></polyline></svg>
                </div>
                <div class="card-title">
                    <span>${escapeHtml(p.title)}</span>
                    ${paperUrl}
                </div>
                <div class="card-meta premium-meta">
                    <span class="meta-author"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg> ${escapeHtml(authorsList)}</span>
                    <span class="meta-year"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg> ${p.year || 'Unknown'}</span>
                    <span class="domain-tag premium-tag">${escapeHtml(catList)}</span>
                </div>
                <div class="card-abstract full-abstract">${escapeHtml(p.abstract || 'No description provided.')}</div>
            </div>
            `;
        }).join('')
        : '<div class="sources-empty">No papers identified.</div>');

    // Graph View
    if (papersData.length > 0) {
        renderGraph(papersData);
        renderTimeline(papersData);
    }

    // Verification
    const verifTab = document.getElementById('tabVerification');
    if (data.verification) {
        const v = data.verification;
        const confidencePercent = (v.confidence * 100).toFixed(0);
        verifTab.innerHTML = `
            <div class="verif-summary">
                <div class="verif-score-circle" style="--percent: ${confidencePercent}">
                    <span class="score-val">${confidencePercent}%</span>
                </div>
                <div class="verif-meta">
                    <h3>${v.verdict || 'PASSED'}</h3>
                    <p>Evidence consistency check completed.</p>
                </div>
            </div>
            ${v.flagged_claims && v.flagged_claims.length > 0 ? `
                <div class="verif-flagged">
                    <h4>Low-Confidence Claims</h4>
                    ${v.flagged_claims.map(c => `<div class="flag-item">! ${escapeHtml(c)}</div>`).join('')}
                </div>
            ` : '<div class="verif-success">OK All claims backed by sources.</div>'}
        `;
    } else {
        verifTab.innerHTML = '<div class="sources-empty">No verification data available.</div>';
    }
}

// Smart Highlighting Logic
function highlightChunk(element) {
    // Remove previous highlights
    document.querySelectorAll('.chunk-highlightable').forEach(el => {
        el.classList.remove('active-highlight');
        el.innerHTML = el.innerHTML.replace(/<mark class="smart-highlight">/g, '').replace(/<\/mark>/g, '');
    });

    const p = element.querySelector('.chunk-highlightable');
    p.classList.add('active-highlight');

    // Simulate smart semantic extraction by isolating the most relevant sentence
    const text = p.innerHTML;
    const sentences = text.split('. ');
    if (sentences.length > 1) {
        // Highlight the middle/dense sentence representing the semantic match
        const highlightIdx = Math.floor((sentences.length - 1) / 2);
        sentences[highlightIdx] = `<mark class="smart-highlight">${sentences[highlightIdx]}</mark>`;
        p.innerHTML = sentences.join('. ');
    } else {
        p.innerHTML = `<mark class="smart-highlight">${text}</mark>`;
    }
}

function setSourcesLoading() {
    const overviewContainer = document.getElementById('sourcesOverviewContainer');
    if (overviewContainer) {
        overviewContainer.innerHTML = `
            <div class="reasoning-card loading">
                <div class="reasoning-title pulse">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                    Executing Brain Strategy...
                </div>
                <div class="skeleton-loader" style="height: 40px; width: 100%; border-radius: 8px; margin-top: 10px;"></div>
            </div>
        `;
    }
    document.getElementById('tabChunks').innerHTML = `<div class="sources-empty"><span>Accessing Knowledge Base...</span></div>`;
    document.getElementById('tabPapers').innerHTML = `<div class="sources-empty"><span>Retrieving Research Network...</span></div>`;
    document.getElementById('tabVerification').innerHTML = `<div class="sources-empty"><span>Preparing Grounding Pass...</span></div>`;

    // Switch to status indicators
    const tabs = document.querySelectorAll('.sources-tab');
    tabs.forEach(t => t.classList.remove('active'));
    tabs[0].classList.add('active');

    const contents = document.querySelectorAll('.sources-tab-content');
    contents.forEach(c => c.classList.remove('active'));
    contents[0].classList.add('active');
}

// -------------------------------------------------------------------------
// INPUT HANDLING
// -------------------------------------------------------------------------

function handleInputChange() {
    const val = els.queryInput.value;
    els.charCount.textContent = `${val.length}/2000`;
    els.sendBtn.disabled = val.trim().length === 0 || state.isLoading;

    // Auto resize
    els.queryInput.style.height = 'auto';
    els.queryInput.style.height = Math.min(els.queryInput.scrollHeight, 150) + 'px';
}

function handleInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!els.sendBtn.disabled) sendQuery();
    }
}

// -------------------------------------------------------------------------
// SEND QUERY
// -------------------------------------------------------------------------

async function sendQuery() {
    const query = els.queryInput.value.trim();
    if (!query || state.isLoading) return;

    setAttachMenuOpen(false);
    state.isLoading = true;
    els.sendBtn.disabled = true;

    // Hide welcome screen
    if (els.welcomeScreen) {
        els.welcomeScreen.style.display = 'none';
    }

    // Add user message
    const outgoingAttachments = [...state.pendingAttachments];
    addMessage('user', query, { attachments: outgoingAttachments });
    state.messages.push({ role: 'user', content: query });
    state.pendingAttachments = [];
    renderAttachmentTray();

    // Clear input
    els.queryInput.value = '';
    handleInputChange();

    // Add loading indicator
    const loadingId = addLoadingMessage();
    setSourcesLoading();

    // Pipeline status simulation
    const steps = ["Planning Strategy", "Searching Knowledge Graph", "Retrieving Papers", "Semantic Vector Search", "Applying MMR Reranking", "Reasoning & Synthesis"];
    let stepIdx = 0;
    updatePipelineStep(steps[stepIdx]);
    const stepInterval = setInterval(() => {
        if (stepIdx < steps.length - 1) {
            stepIdx++;
            updatePipelineStep(steps[stepIdx]);
        }
    }, 2000);

    try {
        const requestData = {
            top_k: els.topK ? parseInt(els.topK.value) : 5,
            min_similarity: els.minSim ? parseFloat(els.minSim.value) / 100 : 0.1,
            use_heavy: els.modelSelect ? els.modelSelect.value === 'heavy' : false,
            verify: els.verifyToggle ? els.verifyToggle.checked : true,
            messages: state.messages
        };

        const res = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        clearInterval(stepInterval);
        updatePipelineStep("Synthesizing Response...");
        removeMessage(loadingId);

        const tempMsgId = addMessage('assistant', '');
        const msgEl = document.getElementById(tempMsgId).querySelector('.message-content');
        
        const contentType = res.headers.get('content-type');
        let answerText = "";
        let metaData = {};
        let doneData = {};

        if (contentType && contentType.includes('application/json')) {
            // Fast-path / Cache hit returns direct JSON
            const data = await res.json();
            answerText = data.answer || "";
            metaData = data;
            doneData = data;
            
            updateSourcesPanel(data);
            const pData = data.papers || (data.source_nodes && data.source_nodes.papers) || [];
            const cData = data.chunks || (data.source_nodes && data.source_nodes.evidence_chunks) || [];
            if (!state.sourcesOpen && (pData.length > 0 || cData.length > 0)) toggleSourcesPanel();
            if (data.latency_metrics) showPipelineDiagnostics(data.latency_metrics);
            
            msgEl.innerHTML = formatMarkdown(answerText);
            scrollToBottom();
        } else {
            // Streaming SSE
            const reader = res.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const jsonStr = line.replace('data: ', '').trim();
                        if (!jsonStr) continue;
                        
                        try {
                            const parsed = JSON.parse(jsonStr);
                            if (parsed.type === 'metadata') {
                                metaData = parsed;
                                updateSourcesPanel(parsed);
                                const pData = parsed.papers || (parsed.source_nodes && parsed.source_nodes.papers) || [];
                                const cData = parsed.chunks || (parsed.source_nodes && parsed.source_nodes.evidence_chunks) || [];
                                if (!state.sourcesOpen && (pData.length > 0 || cData.length > 0)) {
                                    toggleSourcesPanel();
                                }
                                if (parsed.latency_metrics) showPipelineDiagnostics(parsed.latency_metrics);
                            } else if (parsed.type === 'token') {
                                answerText += parsed.token;
                                msgEl.innerHTML = formatMarkdown(answerText);
                                scrollToBottom();
                            } else if (parsed.type === 'done') {
                                doneData = parsed;
                                if (parsed.latency_metrics) showPipelineDiagnostics(parsed.latency_metrics);
                            } else if (parsed.type === 'final') {
                                // Fast-path bypass inside SSE
                                answerText = parsed.answer || "";
                                metaData = parsed;
                                doneData = parsed;
                                updateSourcesPanel(parsed);
                                const pData = parsed.papers || (parsed.source_nodes && parsed.source_nodes.papers) || [];
                                const cData = parsed.chunks || (parsed.source_nodes && parsed.source_nodes.evidence_chunks) || [];
                                if (!state.sourcesOpen && (pData.length > 0 || cData.length > 0)) toggleSourcesPanel();
                                if (parsed.latency_metrics) showPipelineDiagnostics(parsed.latency_metrics);
                                msgEl.innerHTML = formatMarkdown(answerText);
                                scrollToBottom();
                            } else if (parsed.type === 'error') {
                                throw new Error(parsed.detail);
                            }
                        } catch (e) {
                            // ignore JSON parse errors for incomplete chunks
                        }
                    }
                }
            }
        }

        // Finalize pipeline
        updatePipelineStep("Complete");
        setTimeout(() => updatePipelineStep(null), 2000);

        // Replace streaming message with fully featured message card
        removeMessage(tempMsgId);
        const finalData = { answer: answerText, ...metaData, ...doneData };
        
        state.messages.push({ role: 'assistant', content: answerText });
        const assistantMsgId = addAssistantMessage(finalData);
        state.messageData.set(assistantMsgId, finalData);
        
        state.lastResponse = finalData;
        saveToHistory(query, finalData);

        // --- NEW: Smart Visuals Extraction & Rendering ---
        extractVisuals(answerText);
        setTimeout(() => {
            // Render inline mermaid charts in the assistant response
            if (window.mermaid) {
                window.mermaid.run({
                    querySelector: `#${assistantMsgId} .mermaid`
                }).catch(e => console.warn('Mermaid render error:', e));
            }
            // Syntax highlighting for code blocks
            if (window.hljs) {
                document.querySelectorAll(`#${assistantMsgId} pre code`).forEach(block => {
                    hljs.highlightElement(block);
                });
            }
        }, 100);

    } catch (err) {
        clearInterval(stepInterval);
        updatePipelineStep(null);
        removeMessage(loadingId);
        addMessage('assistant', `(!) Error: ${err.message}`, { isError: true });
    }

    state.isLoading = false;
    els.sendBtn.disabled = els.queryInput.value.trim().length === 0;
}

// -------------------------------------------------------------------------
// API CALL
// -------------------------------------------------------------------------

async function apiCall(endpoint, body) {
    const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });

    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }

    return res.json();
}

// -------------------------------------------------------------------------
// MESSAGE RENDERING
// -------------------------------------------------------------------------

function addMessage(role, content, opts = {}) {
    const id = 'msg-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.id = id;

    const avatar = role === 'user' ? '👤' : '🔬';
    const attachments = Array.isArray(opts.attachments) ? opts.attachments : [];
    const attachmentsHtml = attachments.length
        ? `
            <div class="message-attachments">
                ${attachments.map(file => `
                    <span class="message-attachment-chip" title="${escapeHtml(file.name)}">
                        <span>${escapeHtml(file.name)}</span>
                        <span>${formatFileSize(file.size)}</span>
                    </span>
                `).join('')}
            </div>
        `
        : '';

    div.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-body">
            <div class="message-header">
                <span class="message-sender">${role === 'user' ? 'You' : 'Aether'}</span>
                <span class="message-meta">${new Date().toLocaleTimeString()}</span>
            </div>
            <div class="message-content">${opts.isError ? content : formatMarkdown(content)}</div>
            ${attachmentsHtml}
        </div>
    `;

    els.chatMessages.appendChild(div);
    scrollToBottom();
    return id;
}

function addAssistantMessage(data) {
    const id = 'msg-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.id = id;

    // Build verification badge
    let verifyBadge = '';
    let flaggedHtml = '';
    if (data.verification) {
        const v = data.verification;
        const verdict = (v.verdict || 'unknown').toLowerCase();
        let badgeClass = 'unknown';
        let badgeIcon = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
        if (verdict === 'pass') {
            badgeClass = 'pass';
            badgeIcon = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>';
        } else if (verdict === 'partial') {
            badgeClass = 'partial';
            badgeIcon = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
        } else if (verdict === 'fail') {
            badgeClass = 'fail';
            badgeIcon = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
        }

        const confText = v.confidence != null ? `${(v.confidence * 100).toFixed(0)}%` : '&mdash;';
        verifyBadge = `<span class="verification-badge ${badgeClass}">${badgeIcon} ${verdict.toUpperCase()} &bull; ${confText} confidence</span>`;

        if (v.flagged_claims && v.flagged_claims.length > 0) {
            flaggedHtml = `
                <div class="verification-checks">
                    <h4>Verification Checks</h4>
                    <ul>
                        ${v.flagged_claims.map(c => {
                const isVerified = c.toUpperCase().includes('VERIFIED') && !c.toUpperCase().includes('UNVERIFIED');
                const cls = isVerified ? 'verified' : 'unverified';
                const icon = isVerified
                    ? '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>'
                    : '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>';
                const cleanText = c.replace(/^[^a-zA-Z0-9("]*/, '');
                return `<li class="verif-item ${cls}"><span>${icon}</span> <span>${escapeHtml(cleanText)}</span></li>`;
            }).join('')}
                    </ul>
                </div>
            `;
        }
    }

    // Warning
    let warningHtml = '';
    if (data.warning) {
        warningHtml = `<div class="message-warning" style="display:flex;align-items:flex-start;gap:6px"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;margin-top:1px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>${escapeHtml(data.warning)}</div>`;
    }

    const chunksData = data.chunks || (data.source_nodes && data.source_nodes.evidence_chunks) || [];
    const papersData = data.papers || (data.source_nodes && data.source_nodes.papers) || [];
    const routeIntent = data.intent || data.route || '';

    // Footer stats
    const stats = [];
    if (data.latency_ms) {
        let latencyTooltip = 'Total latency';
        let breakdownHtml = '';
        if (data.latency_metrics) {
            latencyTooltip = `Plan: ${data.latency_metrics.plan_ms || 0}ms | Vector: ${data.latency_metrics.vector_ms || 0}ms | Graph: ${data.latency_metrics.graph_ms || 0}ms | LLM: ${data.latency_metrics.llm_ms || 0}ms`;
            const total = data.latency_ms || 1;
            breakdownHtml = `<div class="latency-breakdown">
                <div class="latency-row"><span class="lat-label">Plan</span><div class="lat-bar"><div class="lat-bar-fill" style="width:${Math.min(100, ((data.latency_metrics.plan_ms || 0) / total) * 100)}%; background: var(--accent-purple);"></div></div><span class="lat-val">${data.latency_metrics.plan_ms || 0}ms</span></div>
                <div class="latency-row"><span class="lat-label">Vector</span><div class="lat-bar"><div class="lat-bar-fill" style="width:${Math.min(100, ((data.latency_metrics.vector_ms || 0) / total) * 100)}%; background: var(--accent-cyan);"></div></div><span class="lat-val">${data.latency_metrics.vector_ms || 0}ms</span></div>
                <div class="latency-row"><span class="lat-label">Graph</span><div class="lat-bar"><div class="lat-bar-fill" style="width:${Math.min(100, ((data.latency_metrics.graph_ms || 0) / total) * 100)}%; background: var(--accent-emerald);"></div></div><span class="lat-val">${data.latency_metrics.graph_ms || 0}ms</span></div>
                <div class="latency-row"><span class="lat-label">LLM</span><div class="lat-bar"><div class="lat-bar-fill" style="width:${Math.min(100, ((data.latency_metrics.llm_ms || 0) / total) * 100)}%; background: var(--accent-amber);"></div></div><span class="lat-val">${data.latency_metrics.llm_ms || 0}ms</span></div>
            </div>`;
        }
        stats.push(`<span class="message-stat" title="${latencyTooltip}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            ${data.latency_ms}ms
            ${breakdownHtml}
        </span>`);
    }
    if (data.model_used) stats.push(`<span class="message-stat">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg>
        ${data.model_used}
    </span>`);
    if (routeIntent) stats.push(`<span class="message-stat">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
        Route: ${routeIntent}
    </span>`);
    if (papersData.length > 0) stats.push(`<span class="message-stat clickable" onclick="restoreSourcesData('${id}'); openSourcesPanel(); switchSourceTab('papers')">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        ${papersData.length} Papers
    </span>`);
    if (chunksData.length > 0) stats.push(`<span class="message-stat clickable" onclick="restoreSourcesData('${id}'); openSourcesPanel(); switchSourceTab('chunks')">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="13 2 13 9 20 9"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
        ${chunksData.length} Chunks
    </span>`);

    const copyBtnHtml = `<span class="message-stat btn-copy" onclick="
        var t = this.closest('.message-body') ? this.closest('.message-body').querySelector('.message-content') : null;
        if (t) navigator.clipboard.writeText(t.innerText);
        const o = this.innerHTML;
        this.innerHTML = '<svg width=\'11\' height=\'11\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'currentColor\' stroke-width=\'2.5\'><polyline points=\'20 6 9 17 4 12\'/></svg> Copied';
        setTimeout(() => this.innerHTML = o, 2000);
    ">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg>
        Copy
    </span>`;

    const quickActionsHtml = `
        <div class="quick-actions-bar" style="display: flex; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--surface-glass-border);">
            <button class="quick-action-btn" onclick="document.getElementById('queryInput').value='Summarize the key findings of these papers in a bulleted list.'; document.getElementById('queryInput').focus();" title="Summarize Findings">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
                Summarize Findings
            </button>
            <button class="quick-action-btn" onclick="document.getElementById('queryInput').value='What are the limitations or open problems mentioned in these papers?'; document.getElementById('queryInput').focus();" title="Find Limitations">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                Identify Limitations
            </button>
            <button class="quick-action-btn" onclick="document.getElementById('queryInput').value='How does this research compare to previous state-of-the-art?'; document.getElementById('queryInput').focus();" title="Compare to SOTA">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
                Compare SOTA
            </button>
        </div>
    `;

    let bibtexHtml = '';
    let matrixHtml = '';
    if (papersData.length > 0) {
        // Construct BibTeX block
        const bibtexPayload = btoa(unescape(encodeURIComponent(papersData.map(p => {
            const authorLast = p.author ? p.author.split(' ').pop() : 'Unknown';
            const yearStr = p.year || '2020';
            const id = `${authorLast}${yearStr}${p.title.replace(/\W/g, '').substring(0, 8)}`;
            return `@article{${id},\n  title={${p.title}},\n  author={${p.author || 'Unknown'}},\n  year={${yearStr}},\n  journal={${p.domain || 'Tech. Report'}}\n}`;
        }).join('\n\n'))));
        bibtexHtml = `<span class="message-stat btn-copy" style="color: var(--accent-cyan);" onclick="navigator.clipboard.writeText(decodeURIComponent(escape(atob('${bibtexPayload}')))); this.innerHTML='(Copied!)'; setTimeout(()=>this.innerHTML='BibTeX Export', 2000)">BibTeX Export</span>`;

        // Matrix Generator Feature
        const topTitles = papersData.slice(0, 4).map(p => p.title).join(' | ');
        matrixHtml = `<span class="message-stat btn-copy" style="color: var(--accent-emerald);" onclick="document.getElementById('queryInput').value = 'Generate a tight markdown comparison matrix table for these papers: ${topTitles.replace(/'/g, "\\'")} (Compare Methodology, Datasets, and Accuracy)'; document.getElementById('queryInput').focus(); document.getElementById('sendBtn').click();">Matrix Summary</span>`;
    }

    div.innerHTML = `
        <div class="message-avatar">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--primary-light)">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
        </div>
        <div class="message-body">
            <div class="message-header" style="justify-content: flex-start; margin-bottom: 4px;">
                <span class="message-sender" style="color: var(--primary-light); font-weight: 600;">Aether</span>
            </div>
            <div class="message-content">${formatMarkdown(data.answer || '')}</div>
            ${verifyBadge}
            ${flaggedHtml}
            ${warningHtml}
            ${quickActionsHtml}
            <div class="message-footer" style="opacity: 1;">
                <div class="message-stats-group">${stats.join('')}</div>
                <div class="message-actions-group">
                    ${copyBtnHtml} ${bibtexHtml} ${matrixHtml}
                </div>
            </div>
        </div>
    `;

    els.chatMessages.appendChild(div);

    // Save data for later restoration
    window.messageDataStore[id] = data;

    // Auto scroll only if we're near bottom initially
    scrollToBottom();
    return id;
}

function addLoadingMessage() {
    const id = 'loading-' + Date.now();
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.id = id;

    div.innerHTML = `
        <div class="message-avatar" style="font-size:24px; color: var(--primary-light);">âœ¨</div>
        <div class="message-body">
            <div class="message-loading">
                <div class="typing-dots">
                    <span></span><span></span><span></span>
                </div>
                <span>Reasoning and verifying sources...</span>
            </div>
        </div>
    `;

    els.chatMessages.appendChild(div);
    scrollToBottom();
    return id;
}

function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function scrollToBottom() {
    els.chatContainer.scrollTo({
        top: els.chatContainer.scrollHeight,
        behavior: 'smooth',
    });
}

/* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• MARKDOWN & KATEX â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */
function formatMarkdown(text) {
    if (!text) return '';
    text = text.replace(/\[(\d+)\]/g, '<span class="citation-ref" onclick="openSourcesPanel(); switchSourceTab(\'papers\')" title="View Source" style="cursor:pointer; color:var(--accent-cyan);">[$1]</span>');

    // Handle v4.0 specific tags if any
    text = text.replace(/ã€(.*?)ã€‘/g, '<span class="source-tag">$1</span>');

    // â”€â”€ BEAUTIFY SQUISHED BACKEND LISTS â”€â”€
    // Convert squished ' â€¢ ' bullet points into proper Markdown lists with spacing
    // ── BEAUTIFY SQUISHED BACKEND LISTS ──
    // 1. Convert bullet points (\u2022) into standard Markdown bullets (-)
    text = text.replace(/\u2022/g, '-');

    // 2. If a bullet follows text on the same line, move it to a new list block
    text = text.replace(/([^\n])\s+-\s+/g, '$1\n\n- ');

    // 3. Ensure any list following a paragraph has a double newline (for marked.js)
    text = text.replace(/([a-zA-Z0-9\):])(\s*)\n-\s+/g, '$1\n\n- ');

    // 4. Bold specific paper titles and format metadata (Year, Author, Citations)
    // Case A: Full format "- Title (YYYY) — Author"
    text = text.replace(/-\s+([^\n]+?)\s+\((\d{4})\)\s*(â€”|-|â€“)\s*([^\n]+)/g, '- **$1** <span class="paper-year">($2)</span> &mdash; <span class="paper-author">$4</span>');
    
    // Case B: Compact format "- Title (YYYY) [Citation]" as seen in surveys
    text = text.replace(/-\s+([^\n]+?)\s+\((\d{4})\)\s*(\[\d+\]|\[N\])/g, '- **$1** <span class="paper-year">($2)</span> $3');

    // 1. Extract and protect LaTeX math
    const mathBlocks = [];
    let processedText = text;

    // Display math $$ ... $$
    processedText = processedText.replace(/\$\$(.+?)\$\$/gs, (match, p1) => {
        const id = `__MATH_DISPLAY_${mathBlocks.length}__`;
        try {
            mathBlocks.push({ id, html: katex.renderToString(p1, { displayMode: true, throwOnError: false }) });
        } catch (e) { mathBlocks.push({ id, html: p1 }); }
        return id;
    });

    // Inline math $ ... $
    processedText = processedText.replace(/\$(.+?)\$/g, (match, p1) => {
        const id = `__MATH_INLINE_${mathBlocks.length}__`;
        try {
            mathBlocks.push({ id, html: katex.renderToString(p1, { displayMode: false, throwOnError: false }) });
        } catch (e) { mathBlocks.push({ id, html: p1 }); }
        return id;
    });

    // 2. Render Markdown
    if (window.marked && window.marked.parse) {
        // Use highlight.js if available
        if (window.hljs) {
            marked.setOptions({
                highlight: function (code, lang) {
                    if (lang === 'mermaid') return `<div class="mermaid">${code}</div>`;
                    if (lang && hljs.getLanguage(lang)) {
                        try { return hljs.highlight(code, { language: lang }).value; } catch (__) {}
                    }
                    return code; // use external default escaping
                }
            });
        }
        processedText = marked.parse(processedText);
    } else {
        processedText = processedText.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>');
    }

    // 3. Re-inject rendered Math
    mathBlocks.forEach(block => {
        processedText = processedText.replace(block.id, block.html);
    });

    return processedText;
}

function updatePipelineStep(step) {
    if (els.pipelineStep) {
        els.pipelineStep.textContent = step ? `â€¢ ${step}` : '';
        els.pipelineStep.style.opacity = step ? '1' : '0';
    }
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// HEALTH CHECK
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async function checkHealth() {
    const dot = els.connectionStatus.querySelector('.status-dot');
    const text = els.connectionStatus.querySelector('.status-text');

    try {
        const res = await fetch(`${API_BASE}/api/health`);
        const data = await res.json();

        if (data.ready) {
            dot.className = 'status-dot connected';
            text.textContent = 'Connected';
        } else {
            dot.className = 'status-dot error';
            text.textContent = 'Degraded';
        }
    } catch (e) {
        dot.className = 'status-dot error';
        text.textContent = 'Disconnected';
    }
}

async function showHealthModal() {
    els.healthModal.classList.add('visible');
    els.healthModalBody.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;justify-content:center;padding:20px">
            <div class="loading-spinner"></div>
            <span>Running health checks...</span>
        </div>
    `;

    try {
        const res = await fetch(`${API_BASE}/api/health/full`);
        const data = await res.json();

        const checks = Object.entries(data.checks || {}).map(([name, status]) => {
            const isOk = status === 'ok';
            return `
                <div class="health-check">
                    <span class="health-check-name">${name}</span>
                    <span class="health-check-status ${isOk ? 'health-ok' : 'health-error'}">${isOk
                    ? '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> OK'
                    : '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> Error'}</span>
                </div>
            `;
        }).join('');

        const overallClass = data.status === 'healthy' ? 'healthy' : 'degraded';
        els.healthModalBody.innerHTML = `
            <div class="health-overall ${overallClass}">
                ${data.status === 'healthy'
                ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
                : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'}
                System ${data.status}
            </div>
            ${checks}
        `;
    } catch (e) {
        els.healthModalBody.innerHTML = `
            <div class="health-overall degraded">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                Cannot reach API server
            </div>
            <p style="text-align:center;color:var(--text-muted);font-size:13px">
                Make sure the backend is running on ${API_BASE}
            </p>
        `;
    }
}


// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// HISTORY
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

function saveToHistory(query, data) {
    const historyItem = {
        id: Date.now().toString(),
        query: query,
        timestamp: new Date().toISOString(),
        intent: data.intent,
        papersCount: data.papers ? data.papers.length : 0,
    };

    // Prevent duplicates and move to top
    state.conversations = state.conversations.filter(c => c.query !== query);
    state.conversations.unshift(historyItem);

    if (state.conversations.length > 20) state.conversations.pop();

    try {
        localStorage.setItem('graphrag_history', JSON.stringify(state.conversations));
    } catch (e) { /* quota exceeded, ignore */ }

    renderHistory();
}

function loadHistory() {
    try {
        const saved = localStorage.getItem('graphrag_history');
        if (saved) {
            state.conversations = JSON.parse(saved);
            renderHistory();
        }
    } catch (e) { /* corrupt data */ }
}

function renderHistory() {
    if (state.conversations.length === 0) {
        els.historyList.innerHTML = `
            <div class="history-empty">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="12" cy="12" r="10"/>
                    <polyline points="12 6 12 12 16 14"/>
                </svg>
                <span>No conversations yet</span>
            </div>
        `;
        return;
    }

    els.historyList.innerHTML = state.conversations.map(conv => {
        const timeStr = new Date(conv.timestamp).toLocaleDateString(undefined, {
            month: 'short', day: 'numeric',
        });
        return `
            <div class="history-item" data-query="${escapeHtml(conv.query)}" title="${escapeHtml(conv.query)}">
                <div class="history-item-main">
                    <svg class="history-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                    <div class="history-content">
                        <span class="history-text">${escapeHtml(conv.query)}</span>
                        <span class="history-meta">${timeStr} &bull; ${conv.papersCount || 0} papers</span>
                    </div>
                </div>
                <button class="history-delete-btn" data-id="${conv.id}" title="Delete entry">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
            </div>
        `;
    }).join('');

    // Click to re-run
    els.historyList.querySelectorAll('.history-item').forEach(item => {
        item.addEventListener('click', (e) => {
            if (e.target.closest('.history-delete-btn')) return;
            els.queryInput.value = item.dataset.query;
            handleInputChange();
            sendQuery();
        });
    });

    // Delete handler
    els.historyList.querySelectorAll('.history-delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const id = btn.dataset.id;
            state.conversations = state.conversations.filter(c => c.id !== id);
            localStorage.setItem('graphrag_history', JSON.stringify(state.conversations));
            renderHistory();
        });
    });
}

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// CITATION HIGHLIGHT (bonus feature)
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

document.addEventListener('click', (e) => {
    if (e.target.classList.contains('citation')) {
        const num = parseInt(e.target.textContent.replace(/[\[\]]/g, ''));
        if (num && state.sourcesOpen) {
            // Highlight the corresponding chunk card
            const chunkCards = $$('.chunk-card');
            if (chunkCards[num - 1]) {
                chunkCards[num - 1].scrollIntoView({ behavior: 'smooth', block: 'center' });
                chunkCards[num - 1].style.borderColor = 'var(--accent-primary)';
                chunkCards[num - 1].style.boxShadow = 'var(--shadow-glow)';
                setTimeout(() => {
                    chunkCards[num - 1].style.borderColor = '';
                    chunkCards[num - 1].style.boxShadow = '';
                }, 2000);
            }
        }
        // Open sources panel if not open
        if (!state.sourcesOpen) {
            toggleSourcesPanel();
            switchSourceTab('chunks');
        }
    }
});

// ================= COMPARE DRAWER LOGIC =================
let compareChartInstance = null;

function openCompareDrawer(papers) {
    if (!papers || papers.length < 2) return;
    
    const drawer = document.getElementById('compareDrawer');
    const tableHead = document.querySelector('#compareTable thead tr');
    const tableBody = document.querySelector('#compareTable tbody');
    
    drawer.classList.add('open');
    
    // Setup Table Headers
    let headHtml = '<th>Feature</th>';
    papers.forEach((p, idx) => {
        headHtml += `<th>Paper ${idx + 1}</th>`;
    });
    tableHead.innerHTML = headHtml;
    
    // Setup Table Rows
    const rows = [
        { label: 'Title', key: 'title' },
        { label: 'Authors', key: 'authors' },
        { label: 'Year', key: 'year' },
        { label: 'Categories', key: 'categories' },
        { label: 'URL', key: 'url', default: 'None' },
        { label: 'Citations', key: 'citations', default: 0 }
    ];
    
    let bodyHtml = '';
    rows.forEach(row => {
        bodyHtml += `<tr><td><strong>${row.label}</strong></td>`;
        papers.forEach(p => {
            let val = p[row.key] || p[row.key.slice(0, -1)] || p.domain || row.default || 'N/A';
            if (row.key === 'url' && val && val !== 'None') {
                val = `<a href="${val}" target="_blank">Link</a>`;
            }
            let displayVal = Array.isArray(val) ? val.join(', ') : val;
            if (row.key === 'title' && displayVal.length > 35) displayVal = displayVal.substring(0, 35) + '...';
            bodyHtml += `<td>${row.key === 'url' ? displayVal : escapeHtml(String(displayVal))}</td>`;
        });
        bodyHtml += `</tr>`;
    });
    tableBody.innerHTML = bodyHtml;
    
    // Setup Radar Chart
    const ctx = document.getElementById('compareRadarChart').getContext('2d');
    if (compareChartInstance) compareChartInstance.destroy();
    
    const colors = [
        'rgba(99, 102, 241, 0.6)',
        'rgba(45, 212, 191, 0.6)',
        'rgba(244, 114, 182, 0.6)',
        'rgba(250, 204, 21, 0.6)',
        'rgba(167, 139, 250, 0.6)'
    ];
    
    const borderColors = [
        'rgba(99, 102, 241, 1)',
        'rgba(45, 212, 191, 1)',
        'rgba(244, 114, 182, 1)',
        'rgba(250, 204, 21, 1)',
        'rgba(167, 139, 250, 1)'
    ];
    
    const datasets = papers.map((p, idx) => {
        // Generate pseudo-random metrics based on paper title/domain for visual comparison
        // In a real app, this data would come from the MCP/Backend directly.
        const hash = p.title.length;
        const relevance = Math.min(10, 5 + (hash % 6));
        const clarity = Math.min(10, 4 + ((hash * 2) % 7));
        const novelty = Math.min(10, 6 + ((hash * 3) % 5));
        const impact = Math.min(10, (p.citations || 1) % 10 + 2);
        const reproducibility = Math.min(10, 5 + ((hash * 4) % 6));
        
        return {
            label: p.title.substring(0, 15) + '...',
            data: [relevance, clarity, novelty, impact, reproducibility],
            backgroundColor: colors[idx % colors.length],
            borderColor: borderColors[idx % borderColors.length],
            borderWidth: 2,
            pointBackgroundColor: borderColors[idx % borderColors.length],
        };
    });
    
    if (window.Chart) {
        Chart.defaults.color = 'rgba(255, 255, 255, 0.7)';
        compareChartInstance = new Chart(ctx, {
            type: 'radar',
            data: {
                labels: ['Relevance', 'Clarity', 'Novelty', 'Impact', 'Reproducibility'],
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    r: {
                        angleLines: { color: 'rgba(255, 255, 255, 0.1)' },
                        grid: { color: 'rgba(255, 255, 255, 0.1)' },
                        pointLabels: { font: { size: 12 }, color: 'rgba(255,255,255,0.9)' },
                        ticks: { display: false, min: 0, max: 10 }
                    }
                },
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { color: 'rgba(255,255,255,0.9)', font: { size: 11 } }
                    }
                }
            }
        });
    }
}

document.getElementById('compareDrawerClose')?.addEventListener('click', () => {
    document.getElementById('compareDrawer').classList.remove('open');
});

// ═══════════════════════════════════════════════
// v5.0 — COMMAND PALETTE
// ═══════════════════════════════════════════════

const CMD_ACTIONS = [
    { icon: '🔍', label: 'Search papers...', action: () => { closeCmdPalette(); els.queryInput.focus(); } },
    { icon: '📊', label: 'Toggle Sources Panel', shortcut: 'Ctrl+B', action: () => { closeCmdPalette(); toggleSourcesPanel(); } },
    { icon: '📈', label: 'Show Knowledge Graph', action: () => { closeCmdPalette(); openSourcesPanel(); switchSourceTab('graph'); } },
    { icon: '⏳', label: 'Show Timeline View', action: () => { closeCmdPalette(); openSourcesPanel(); switchSourceTab('timeline'); } },
    { icon: '🔬', label: 'Deep Research Mode', action: () => { closeCmdPalette(); handleAttachAction('deep-research'); } },
    { icon: '🏥', label: 'System Health Check', action: () => { closeCmdPalette(); showHealthModal(); } },
    { icon: '📝', label: 'Summarize Findings', action: () => { closeCmdPalette(); els.queryInput.value = 'Summarize the key findings in a bulleted list.'; handleInputChange(); sendQuery(); } },
    { icon: '📚', label: 'Generate Literature Survey', action: () => { closeCmdPalette(); els.queryInput.value = 'Generate a literature survey comparing the top 5 papers.'; handleInputChange(); sendQuery(); } },
    { icon: '🧹', label: 'Clear Conversation', action: () => { closeCmdPalette(); els.chatMessages.innerHTML = ''; state.messages = []; document.getElementById('welcomeScreen') && (document.getElementById('welcomeScreen').style.display = ''); } },
    { icon: '🌙', label: 'Toggle Theme', action: () => { closeCmdPalette(); document.getElementById('themeToggle')?.click(); } },
];

function createCmdPalette() {
    if (document.getElementById('cmdPaletteOverlay')) return;
    const overlay = document.createElement('div');
    overlay.className = 'cmd-palette-overlay';
    overlay.id = 'cmdPaletteOverlay';
    overlay.innerHTML = `
        <div class="cmd-palette">
            <input class="cmd-palette-input" id="cmdInput" placeholder="Type a command..." autocomplete="off" />
            <div class="cmd-palette-results" id="cmdResults"></div>
        </div>
    `;
    document.body.appendChild(overlay);

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeCmdPalette();
    });

    const input = document.getElementById('cmdInput');
    input.addEventListener('input', () => renderCmdResults(input.value));
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeCmdPalette();
        if (e.key === 'Enter') {
            const selected = document.querySelector('.cmd-result-item.selected') || document.querySelector('.cmd-result-item');
            if (selected) selected.click();
        }
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            const items = [...document.querySelectorAll('.cmd-result-item')];
            const cur = items.findIndex(i => i.classList.contains('selected'));
            items.forEach(i => i.classList.remove('selected'));
            const next = e.key === 'ArrowDown' ? (cur + 1) % items.length : (cur - 1 + items.length) % items.length;
            items[next]?.classList.add('selected');
            items[next]?.scrollIntoView({ block: 'nearest' });
        }
    });
}

function renderCmdResults(filter = '') {
    const results = document.getElementById('cmdResults');
    const filtered = CMD_ACTIONS.filter(a => a.label.toLowerCase().includes(filter.toLowerCase()));
    results.innerHTML = filtered.map((a, idx) => `
        <div class="cmd-result-item ${idx === 0 ? 'selected' : ''}" data-idx="${CMD_ACTIONS.indexOf(a)}">
            <span class="cmd-icon">${a.icon}</span>
            <span class="cmd-label">${a.label}</span>
            ${a.shortcut ? `<span class="cmd-shortcut">${a.shortcut}</span>` : ''}
        </div>
    `).join('') || '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:13px;">No commands found</div>';

    results.querySelectorAll('.cmd-result-item').forEach(item => {
        item.addEventListener('click', () => {
            CMD_ACTIONS[parseInt(item.dataset.idx)]?.action();
        });
    });
}

function openCmdPalette() {
    createCmdPalette();
    const overlay = document.getElementById('cmdPaletteOverlay');
    overlay.classList.add('visible');
    setTimeout(() => {
        const input = document.getElementById('cmdInput');
        input.value = '';
        input.focus();
        renderCmdResults();
    }, 50);
}

function closeCmdPalette() {
    document.getElementById('cmdPaletteOverlay')?.classList.remove('visible');
}

// Bind Ctrl+K and button
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        openCmdPalette();
    }
    if (e.key === 'Escape') closeCmdPalette();
});
document.getElementById('cmdPaletteBtn')?.addEventListener('click', openCmdPalette);

// ═══════════════════════════════════════════════
// v5.0 — PIPELINE DIAGNOSTICS
// ═══════════════════════════════════════════════

function showPipelineDiagnostics(metrics) {
    const bar = document.getElementById('pipelineDiagnostics');
    if (!bar || !metrics) return;

    bar.style.display = 'flex';
    const fields = [
        { id: 'diagPlan', key: 'plan_ms' },
        { id: 'diagVector', key: 'vector_ms' },
        { id: 'diagGraph', key: 'graph_ms' },
        { id: 'diagLLM', key: 'llm_ms' },
    ];

    fields.forEach(f => {
        const chip = document.getElementById(f.id);
        const val = metrics[f.key];
        if (chip && val != null) {
            chip.classList.add('done');
            chip.querySelector('.diag-val').textContent = `${val}ms`;
        }
    });

    // Auto-hide after 8 seconds
    clearTimeout(window._diagTimeout);
    window._diagTimeout = setTimeout(() => {
        bar.style.display = 'none';
        fields.forEach(f => {
            const chip = document.getElementById(f.id);
            if (chip) {
                chip.classList.remove('done', 'active');
                chip.querySelector('.diag-val').textContent = '\u2014';
            }
        });
    }, 8000);
}

// ═══════════════════════════════════════════════
// v5.0 — DEDICATED TIMELINE RENDERER
// ═══════════════════════════════════════════════

function renderTimeline(papers) {
    const svg = d3.select("#timelineSvg");
    svg.selectAll("*").remove();

    if (!papers || papers.length === 0) {
        document.getElementById('timelineEmpty').style.display = 'flex';
        document.getElementById('timelineContainer').style.display = 'none';
        return;
    }

    document.getElementById('timelineEmpty').style.display = 'none';
    document.getElementById('timelineContainer').style.display = 'block';

    const width = document.getElementById('timelineContainer').clientWidth || 800;
    const height = 500;
    const g = svg.append("g");

    // Zoom
    const zoom = d3.zoom().scaleExtent([0.5, 4]).on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);

    const nodes = papers.map(p => ({
        id: p.id || p.title || `paper-${Math.random()}`,
        title: p.title || 'Untitled',
        author: Array.isArray(p.authors) ? p.authors[0] : (p.author || 'Unknown'),
        domain: (Array.isArray(p.categories) && p.categories[0]) || p.domain || 'General',
        year: parseInt(p.year) || 2020,
        radius: 8 + Math.min((p.citations || 5) / 2, 8)
    }));

    const years = nodes.map(n => n.year);
    const minYear = Math.min(...years) - 2;
    const maxYear = Math.max(...years) + 2;
    const xScale = d3.scaleLinear().domain([minYear, maxYear]).range([60, width - 60]);

    // Gradient background
    const defs = svg.append("defs");
    const grad = defs.append("linearGradient").attr("id", "tlGrad").attr("x1", "0").attr("y1", "0").attr("x2", "1").attr("y2", "0");
    grad.append("stop").attr("offset", "0%").attr("stop-color", "rgba(99,102,241,0.1)");
    grad.append("stop").attr("offset", "50%").attr("stop-color", "rgba(99,102,241,0.2)");
    grad.append("stop").attr("offset", "100%").attr("stop-color", "rgba(99,102,241,0.1)");

    // Main timeline axis
    g.append("line")
        .attr("x1", 40).attr("y1", height / 2)
        .attr("x2", width - 40).attr("y2", height / 2)
        .attr("stroke", "url(#tlGrad)").attr("stroke-width", 3);

    // Year ticks
    const yearSet = Array.from(new Set(years)).sort();
    yearSet.forEach(yr => {
        g.append("circle")
            .attr("cx", xScale(yr)).attr("cy", height / 2)
            .attr("r", 5).attr("fill", "var(--bg-active)")
            .attr("stroke", "var(--text-muted)").attr("stroke-width", 1.5);

        g.append("text")
            .attr("x", xScale(yr)).attr("y", height / 2 + 28)
            .attr("text-anchor", "middle").attr("fill", "var(--text-muted)")
            .style("font-size", "12px").style("font-weight", "700")
            .style("font-family", "var(--font-mono)").text(yr);
    });

    // Paper nodes
    nodes.forEach((d, i) => {
        const yOffset = height / 2 + (i % 2 === 0 ? -55 - (i % 3) * 35 : 55 + (i % 3) * 35);

        // Connection line
        g.append("line")
            .attr("x1", xScale(d.year)).attr("y1", height / 2)
            .attr("x2", xScale(d.year)).attr("y2", yOffset)
            .attr("stroke", getColorForDomain(d.domain))
            .attr("stroke-width", 1.5).attr("stroke-dasharray", "3,3")
            .style("opacity", 0.5);

        const nodeG = g.append("g").attr("transform", `translate(${xScale(d.year)}, ${yOffset})`);

        // Glow effect
        nodeG.append("circle").attr("r", d.radius + 4)
            .attr("fill", "none").attr("stroke", getColorForDomain(d.domain))
            .attr("stroke-width", 1).style("opacity", 0.3);

        // Main circle
        nodeG.append("circle").attr("r", d.radius)
            .attr("fill", getColorForDomain(d.domain))
            .attr("stroke", "white").attr("stroke-width", 2)
            .style("cursor", "pointer");

        // Title
        nodeG.append("text")
            .attr("y", -d.radius - 8).attr("text-anchor", "middle")
            .attr("fill", "var(--text-primary)")
            .style("font-size", "10px").style("font-weight", "600")
            .style("text-shadow", "0 1px 4px rgba(0,0,0,0.9)")
            .text((d.title && d.title.length > 30) ? d.title.substring(0, 30) + "..." : (d.title || 'Untitled'));

        // Author subtitle
        nodeG.append("text")
            .attr("y", d.radius + 16).attr("text-anchor", "middle")
            .attr("fill", "var(--text-muted)")
            .style("font-size", "9px").style("font-style", "italic")
            .text(d.author.length > 20 ? d.author.substring(0, 20) + "..." : d.author);

        nodeG.append("title").text(`${d.title}\n${d.author} (${d.year})`);

        // Hover
        nodeG.on("mouseover", function () {
            d3.select(this).select("circle:nth-child(2)").attr("stroke-width", 3).attr("stroke", "#a78bfa");
        }).on("mouseout", function () {
            d3.select(this).select("circle:nth-child(2)").attr("stroke-width", 2).attr("stroke", "white");
        });
    });
}

// ═══════════════════════════════════════════════
// v5.0 — PAPER PIN-TO-COMPARE
// ═══════════════════════════════════════════════

window.pinnedPapers = window.pinnedPapers || new Set();

function togglePinPaper(paperId, paperObj) {
    if (window.pinnedPapers.has(paperId)) {
        window.pinnedPapers.delete(paperId);
    } else {
        if (window.pinnedPapers.size >= 4) {
            // Max 4 papers
            const first = window.pinnedPapers.values().next().value;
            window.pinnedPapers.delete(first);
            document.querySelector(`.paper-pin-checkbox[data-paper-id="${first}"]`)?.classList.remove('pinned');
        }
        window.pinnedPapers.add(paperId);
    }

    // Update checkbox visuals
    const cb = document.querySelector(`.paper-pin-checkbox[data-paper-id="${paperId}"]`);
    if (cb) cb.classList.toggle('pinned', window.pinnedPapers.has(paperId));

    // Floating compare button
    updateFloatingCompareBtn();
}

function updateFloatingCompareBtn() {
    let btn = document.getElementById('floatingCompareBtn');
    if (window.pinnedPapers.size >= 2) {
        if (!btn) {
            btn = document.createElement('button');
            btn.id = 'floatingCompareBtn';
            btn.className = 'compare-floating-btn';
            btn.addEventListener('click', () => {
                const pinned = Array.from(window.pinnedPapers);
                const papers = (window.lastFetchedPapers || []).filter(p => pinned.includes(p.id || p.title));
                if (papers.length >= 2) openCompareDrawer(papers);
            });
            document.body.appendChild(btn);
        }
        btn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
            Compare ${window.pinnedPapers.size} Papers
        `;
        btn.style.display = 'flex';
    } else {
        if (btn) btn.style.display = 'none';
    }
}

// ═══════════════════════════════════════════════
// v7.0 — SMART VISUALS EXTRACTION (Images, Flowcharts, Tables)
// ═══════════════════════════════════════════════

function extractVisuals(markdown) {
    const visualsContainer = document.getElementById('visualsContainer');
    const visualsEmpty = document.getElementById('visualsEmpty');
    const visualsToolbar = document.getElementById('visualsToolbar');
    
    if (!visualsContainer) return;
    
    const visuals = [];
    
    // 1. Extract Images: ![Alt](url)
    const imgRegex = /!\[([^\]]*)\]\(([^)]+)\)/g;
    let match;
    while ((match = imgRegex.exec(markdown)) !== null) {
        visuals.push({
            type: 'image',
            title: match[1] || 'Extracted Image',
            content: `<img src="${match[2]}" alt="${escapeHtml(match[1])}" class="visual-image" onerror="this.onerror=null; this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'100\\' height=\\'100\\'><rect width=\\'100\\' height=\\'100\\' fill=\\'%231e293b\\'/><text x=\\'50\\' y=\\'50\\' font-family=\\'sans-serif\\' font-size=\\'12\\' fill=\\'%2364748b\\' text-anchor=\\'middle\\' dominant-baseline=\\'middle\\'>Image failed to load</text></svg>'"/>`
        });
    }

    // 2. Extract Mermaid Flowcharts
    const mermaidRegex = /```mermaid\n([\s\S]*?)```/g;
    let mCount = 0;
    while ((match = mermaidRegex.exec(markdown)) !== null) {
        mCount++;
        visuals.push({
            type: 'flowchart',
            title: `Process Flowchart ${mCount}`,
            content: `<div class="mermaid visual-mermaid">${match[1]}</div>`
        });
    }

    // 3. Extract Markdown Tables
    // Matches a basic markdown table structure
    const tableRegex = /(?:\|.*\|[\n\r]+)+\|.*\|/g;
    let tCount = 0;
    while ((match = tableRegex.exec(markdown)) !== null) {
        // Simple verification it has a separator row like |---|---|
        if (match[0].includes('|-') || match[0].includes('-|')) {
            tCount++;
            let tableHtml = window.marked ? marked.parse(match[0]) : escapeHtml(match[0]);
            visuals.push({
                type: 'table',
                title: `Comparison Table ${tCount}`,
                content: `<div class="visual-table-wrapper">${tableHtml}</div>`
            });
        }
    }

    // Render extracted visuals
    if (visuals.length === 0) {
        visualsContainer.innerHTML = '';
        if (visualsEmpty) visualsEmpty.style.display = 'flex';
        if (visualsToolbar) visualsToolbar.style.display = 'none';
        return;
    }

    if (visualsEmpty) visualsEmpty.style.display = 'none';
    if (visualsToolbar) visualsToolbar.style.display = 'flex';

    visualsContainer.innerHTML = visuals.map((v, i) => `
        <div class="visual-card" data-type="${v.type}">
            <div class="visual-card-header">
                <span class="visual-card-icon">
                    ${v.type === 'flowchart' ? '🔀' : v.type === 'table' ? '📊' : '🖼️'}
                </span>
                <span class="visual-card-title">${escapeHtml(v.title)}</span>
            </div>
            <div class="visual-card-body">
                ${v.content}
            </div>
        </div>
    `).join('');

    // Re-run mermaid for the newly added visuals
    setTimeout(() => {
        if (window.mermaid) {
            window.mermaid.run({ querySelector: '#visualsContainer .mermaid' }).catch(e => console.warn('Visuals mermaid error:', e));
        }
    }, 150);
}

window.filterVisuals = function(type) {
    document.querySelectorAll('.vis-tool-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.vis === type);
    });
    
    document.querySelectorAll('.visual-card').forEach(card => {
        if (type === 'all' || card.dataset.type === type) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
};

// ═══════════════════════════════════════════════
// v6.0 — SESSION TIMER
// ═══════════════════════════════════════════════

const sessionStartTime = Date.now();

function updateSessionTimer() {
    const elapsed = Date.now() - sessionStartTime;
    const mins = Math.floor(elapsed / 60000);
    const secs = Math.floor((elapsed % 60000) / 1000);
    const timerEl = document.getElementById('sessionTimerText');
    if (timerEl) {
        timerEl.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
}

setInterval(updateSessionTimer, 1000);

// ═══════════════════════════════════════════════
// v6.0 — SESSION STATS TRACKING
// ═══════════════════════════════════════════════

const sessionStats = {
    queries: 0,
    papers: 0,
    chunks: 0,
    saved: 0,
};

function updateSessionStats(updates = {}) {
    Object.assign(sessionStats, updates);
    const elQ = document.getElementById('statQueries');
    const elP = document.getElementById('statPapers');
    const elC = document.getElementById('statChunks');
    const elS = document.getElementById('statSaved');
    if (elQ) elQ.textContent = sessionStats.queries;
    if (elP) elP.textContent = sessionStats.papers;
    if (elC) elC.textContent = sessionStats.chunks;
    if (elS) elS.textContent = sessionStats.saved;
}

// Hook into sendQuery to increment
const _origSendQuery = sendQuery;
sendQuery = async function() {
    sessionStats.queries++;
    updateSessionStats();
    return _origSendQuery.apply(this, arguments);
};

// Hook into updateSourcesPanel to track papers/chunks
const _origUpdateSourcesPanel = updateSourcesPanel;
updateSourcesPanel = function(data) {
    const papersData = data.papers || (data.source_nodes && data.source_nodes.papers) || [];
    const chunksData = data.chunks || (data.source_nodes && data.source_nodes.evidence_chunks) || [];
    sessionStats.papers += papersData.length;
    sessionStats.chunks += chunksData.length;
    updateSessionStats();
    return _origUpdateSourcesPanel.apply(this, arguments);
};

// ═══════════════════════════════════════════════
// v6.0 — FOCUS MODE
// ═══════════════════════════════════════════════

function toggleFocusMode() {
    document.body.classList.toggle('focus-mode');
    if (document.body.classList.contains('focus-mode')) {
        state.sourcesOpen = false;
        els.sourcesPanel.classList.remove('open');
        document.body.classList.remove('sources-open');
    }
}

document.getElementById('focusModeBtn')?.addEventListener('click', toggleFocusMode);

// ═══════════════════════════════════════════════
// v6.0 — KEYBOARD SHORTCUTS OVERLAY
// ═══════════════════════════════════════════════

function toggleShortcutsOverlay() {
    const overlay = document.getElementById('shortcutsOverlay');
    overlay.classList.toggle('visible');
}

document.getElementById('keyboardShortcutsBtn')?.addEventListener('click', toggleShortcutsOverlay);
document.getElementById('shortcutsClose')?.addEventListener('click', () => {
    document.getElementById('shortcutsOverlay').classList.remove('visible');
});
document.getElementById('shortcutsOverlay')?.addEventListener('click', (e) => {
    if (e.target.id === 'shortcutsOverlay') {
        document.getElementById('shortcutsOverlay').classList.remove('visible');
    }
});

// ═══════════════════════════════════════════════
// v6.0 — ENHANCED KEYBOARD SHORTCUTS
// ═══════════════════════════════════════════════

document.addEventListener('keydown', (e) => {
    // Focus mode: Ctrl+Shift+F
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'F') {
        e.preventDefault();
        toggleFocusMode();
        return;
    }

    // Toggle sidebar: Ctrl+\
    if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
        e.preventDefault();
        toggleSidebar();
        return;
    }

    // Toggle sources: Ctrl+B
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        toggleSourcesPanel();
        return;
    }

    // Toggle theme: Ctrl+Shift+T
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'T') {
        e.preventDefault();
        document.getElementById('themeToggle')?.click();
        return;
    }

    // Export session: Ctrl+Shift+E
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'E') {
        e.preventDefault();
        exportSession();
        return;
    }

    // Workspace tabs: Ctrl+1/2/3
    if ((e.ctrlKey || e.metaKey) && ['1', '2', '3'].includes(e.key)) {
        e.preventDefault();
        const tabs = ['chat', 'notebooks', 'collections'];
        switchWorkspace(tabs[parseInt(e.key) - 1]);
        return;
    }

    // Focus input: / key (when not in input)
    if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
        e.preventDefault();
        els.queryInput.focus();
        return;
    }

    // Show shortcuts: ? key
    if (e.key === '?' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
        e.preventDefault();
        toggleShortcutsOverlay();
        return;
    }

    // Escape from focus mode
    if (e.key === 'Escape' && document.body.classList.contains('focus-mode')) {
        toggleFocusMode();
        return;
    }

    // Escape from shortcuts
    if (e.key === 'Escape' && document.getElementById('shortcutsOverlay')?.classList.contains('visible')) {
        document.getElementById('shortcutsOverlay').classList.remove('visible');
        return;
    }
});

// ═══════════════════════════════════════════════
// v6.0 — WORKSPACE TABS
// ═══════════════════════════════════════════════

let currentWorkspace = 'chat';

function switchWorkspace(workspace) {
    currentWorkspace = workspace;
    document.querySelectorAll('.workspace-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.workspace === workspace);
    });
    const chatContainer = document.getElementById('chatContainer');
    const inputArea = document.querySelector('.input-area');
    const views = {
        notebooks: document.getElementById('workspaceNotebooks'),
        collections: document.getElementById('workspaceCollections'),
        queue: document.getElementById('workspaceQueue'),
        citations: document.getElementById('workspaceCitations'),
        workflows: document.getElementById('workspaceWorkflows'),
        timeline: document.getElementById('workspaceTimeline'),
    };
    chatContainer.style.display = workspace === 'chat' ? '' : 'none';
    inputArea.style.display = workspace === 'chat' ? '' : 'none';
    Object.entries(views).forEach(([key, el]) => {
        if (el) el.style.display = workspace === key ? '' : 'none';
    });
    if (workspace === 'notebooks') renderNotebooks();
    if (workspace === 'collections') renderCollections();
    if (workspace === 'queue' && typeof ReadingQueue !== 'undefined') ReadingQueue.render();
    if (workspace === 'citations' && typeof CitationManager !== 'undefined') CitationManager.render();
    if (workspace === 'workflows' && typeof renderWorkflows !== 'undefined') renderWorkflows();
    if (workspace === 'timeline') {
        setTimeout(() => renderTimeline(window.lastGraphPapers || []), 50);
    }
}

document.querySelectorAll('.workspace-tab').forEach(tab => {
    tab.addEventListener('click', () => switchWorkspace(tab.dataset.workspace));
});

// ═══════════════════════════════════════════════
// v6.0 — NOTEBOOKS SYSTEM
// ═══════════════════════════════════════════════

function getNotebooks() {
    try {
        return JSON.parse(localStorage.getItem('aether_notebooks') || '[]');
    } catch { return []; }
}

function saveNotebooks(notebooks) {
    localStorage.setItem('aether_notebooks', JSON.stringify(notebooks));
    updateNotebookBadge();
}

function updateNotebookBadge() {
    const notebooks = getNotebooks();
    const totalEntries = notebooks.reduce((sum, nb) => sum + (nb.entries?.length || 0), 0);
    const badge = document.getElementById('notebookBadge');
    if (badge) badge.textContent = totalEntries;
}

function renderNotebooks() {
    const grid = document.getElementById('notebooksGrid');
    const notebooks = getNotebooks();

    if (notebooks.length === 0) {
        grid.innerHTML = `
            <div class="notebook-empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3">
                    <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>
                </svg>
                <h3>No notebooks yet</h3>
                <p>Save research findings from chat responses to organize your work.</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = notebooks.map((nb, idx) => `
        <div class="notebook-card" data-nb-idx="${idx}">
            <button class="notebook-card-delete" onclick="event.stopPropagation(); deleteNotebook(${idx})" title="Delete notebook">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
            </button>
            <div class="notebook-card-title">${escapeHtml(nb.name)}</div>
            <div class="notebook-card-meta">${nb.entries?.length || 0} entries · ${new Date(nb.created).toLocaleDateString()}</div>
            <div class="notebook-card-tags">
                ${(nb.tags || []).map(t => `<span class="notebook-card-tag">${escapeHtml(t)}</span>`).join('')}
            </div>
            <div class="notebook-card-entries">
                ${(nb.entries || []).slice(0, 2).map(e => `
                    <div style="font-size: 12px; color: var(--text-tertiary); margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        ${escapeHtml(e.content?.substring(0, 80) || '')}...
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');
}

function deleteNotebook(idx) {
    const notebooks = getNotebooks();
    if (confirm(`Delete "${notebooks[idx]?.name}"?`)) {
        notebooks.splice(idx, 1);
        saveNotebooks(notebooks);
        renderNotebooks();
        showToast('Notebook deleted');
    }
}

// Notebook modal logic
let _pendingSaveContent = '';
let _pendingSaveTags = [];

function openNotebookModal(content) {
    _pendingSaveContent = content || '';
    _pendingSaveTags = [];
    const modal = document.getElementById('notebookModal');
    modal.classList.add('visible');

    // Populate notebook dropdown
    const select = document.getElementById('notebookSelect');
    const notebooks = getNotebooks();
    select.innerHTML = '<option value="__new__">+ Create New Notebook</option>' +
        notebooks.map((nb, i) => `<option value="${i}">${escapeHtml(nb.name)}</option>`).join('');

    document.getElementById('notebookNote').value = '';
    document.getElementById('notebookTagInput').value = '';
    document.getElementById('notebookTagsList').innerHTML = '';
    document.getElementById('newNotebookNameField').style.display = 'none';

    select.addEventListener('change', () => {
        document.getElementById('newNotebookNameField').style.display =
            select.value === '__new__' ? '' : 'none';
    });
}

document.getElementById('notebookModalClose')?.addEventListener('click', () => {
    document.getElementById('notebookModal').classList.remove('visible');
});
document.getElementById('notebookModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'notebookModal') document.getElementById('notebookModal').classList.remove('visible');
});

document.getElementById('addTagBtn')?.addEventListener('click', () => {
    const input = document.getElementById('notebookTagInput');
    const tag = input.value.trim();
    if (tag && !_pendingSaveTags.includes(tag)) {
        _pendingSaveTags.push(tag);
        renderNotebookTags();
    }
    input.value = '';
    input.focus();
});

document.getElementById('notebookTagInput')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        document.getElementById('addTagBtn')?.click();
    }
});

function renderNotebookTags() {
    const container = document.getElementById('notebookTagsList');
    container.innerHTML = _pendingSaveTags.map((tag, i) => `
        <span class="notebook-tag">
            ${escapeHtml(tag)}
            <span class="notebook-tag-remove" onclick="removeNotebookTag(${i})">×</span>
        </span>
    `).join('');
}

function removeNotebookTag(idx) {
    _pendingSaveTags.splice(idx, 1);
    renderNotebookTags();
}

document.getElementById('notebookSaveBtn')?.addEventListener('click', () => {
    const select = document.getElementById('notebookSelect');
    const note = document.getElementById('notebookNote').value.trim();
    const notebooks = getNotebooks();

    let nbIdx;
    if (select.value === '__new__') {
        const name = document.getElementById('newNotebookName').value.trim() || `Notebook ${notebooks.length + 1}`;
        const newNb = {
            name,
            created: new Date().toISOString(),
            tags: [..._pendingSaveTags],
            entries: [],
        };
        notebooks.push(newNb);
        nbIdx = notebooks.length - 1;
    } else {
        nbIdx = parseInt(select.value);
    }

    notebooks[nbIdx].entries = notebooks[nbIdx].entries || [];
    notebooks[nbIdx].entries.push({
        content: _pendingSaveContent,
        note,
        tags: [..._pendingSaveTags],
        timestamp: new Date().toISOString(),
    });

    // Merge new tags into notebook tags
    _pendingSaveTags.forEach(t => {
        if (!notebooks[nbIdx].tags.includes(t)) notebooks[nbIdx].tags.push(t);
    });

    saveNotebooks(notebooks);
    sessionStats.saved++;
    updateSessionStats();
    document.getElementById('notebookModal').classList.remove('visible');
    showToast('Saved to notebook!');
});

document.getElementById('createNotebookBtn')?.addEventListener('click', () => {
    openNotebookModal('');
});

// ═══════════════════════════════════════════════
// v6.0 — COLLECTIONS (Paper Bookmarks)
// ═══════════════════════════════════════════════

function getCollections() {
    try {
        return JSON.parse(localStorage.getItem('aether_collections') || '[]');
    } catch { return []; }
}

function saveCollections(collections) {
    localStorage.setItem('aether_collections', JSON.stringify(collections));
    updateCollectionBadge();
}

function updateCollectionBadge() {
    const collections = getCollections();
    const totalPapers = collections.reduce((sum, c) => sum + (c.papers?.length || 0), 0);
    const badge = document.getElementById('collectionBadge');
    if (badge) badge.textContent = totalPapers;
}

function renderCollections() {
    const grid = document.getElementById('collectionsGrid');
    const collections = getCollections();

    if (collections.length === 0) {
        grid.innerHTML = `
            <div class="notebook-empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
                </svg>
                <h3>No collections yet</h3>
                <p>Pin papers from search results to build curated collections.</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = collections.map((col, idx) => `
        <div class="notebook-card" data-col-idx="${idx}">
            <button class="notebook-card-delete" onclick="event.stopPropagation(); deleteCollection(${idx})" title="Delete collection">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
            </button>
            <div class="notebook-card-title">${escapeHtml(col.name)}</div>
            <div class="notebook-card-meta">${col.papers?.length || 0} papers · ${new Date(col.created).toLocaleDateString()}</div>
            <div class="notebook-card-entries">
                ${(col.papers || []).slice(0, 3).map(p => `
                    <div style="font-size: 12px; color: var(--text-tertiary); margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        📄 ${escapeHtml(p.title?.substring(0, 60) || '')}
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');
}

function deleteCollection(idx) {
    const collections = getCollections();
    if (confirm(`Delete "${collections[idx]?.name}"?`)) {
        collections.splice(idx, 1);
        saveCollections(collections);
        renderCollections();
        showToast('Collection deleted');
    }
}

document.getElementById('createCollectionBtn')?.addEventListener('click', () => {
    const name = prompt('Collection name:');
    if (!name) return;
    const collections = getCollections();
    collections.push({ name, created: new Date().toISOString(), papers: [] });
    saveCollections(collections);
    renderCollections();
    showToast('Collection created!');
});

// ═══════════════════════════════════════════════
// v6.0 — TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════

function showToast(message, duration = 2500) {
    let toast = document.querySelector('.toast-notification');
    if (!toast) {
        toast = document.createElement('div');
        toast.className = 'toast-notification';
        document.body.appendChild(toast);
    }
    toast.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> ${message}`;
    requestAnimationFrame(() => {
        toast.classList.add('visible');
        setTimeout(() => toast.classList.remove('visible'), duration);
    });
}

// ═══════════════════════════════════════════════
// v6.0 — EXPORT SESSION
// ═══════════════════════════════════════════════

function exportSession() {
    const elapsed = Date.now() - sessionStartTime;
    const mins = Math.floor(elapsed / 60000);

    let markdown = `# Aether Research Session\n`;
    markdown += `**Date:** ${new Date().toLocaleDateString()}\n`;
    markdown += `**Duration:** ${mins} minutes\n`;
    markdown += `**Queries:** ${sessionStats.queries} | **Papers:** ${sessionStats.papers} | **Chunks:** ${sessionStats.chunks}\n\n`;
    markdown += `---\n\n`;

    state.messages.forEach(msg => {
        if (msg.role === 'user') {
            markdown += `## 🧑 Query\n\n${msg.content}\n\n`;
        } else {
            markdown += `## 🔬 Response\n\n${msg.content}\n\n---\n\n`;
        }
    });

    // Download
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aether-session-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Session exported!');
}

document.getElementById('exportSessionBtn')?.addEventListener('click', exportSession);

// ═══════════════════════════════════════════════
// v6.0 — ENHANCED addAssistantMessage WITH PRODUCTIVITY
// ═══════════════════════════════════════════════

// Monkey-patch addAssistantMessage to add productivity bar
const _origAddAssistantMessage = addAssistantMessage;
addAssistantMessage = function(data) {
    const id = _origAddAssistantMessage.call(this, data);

    // Add productivity bar after message
    const msgEl = document.getElementById(id);
    if (!msgEl) return id;

    const body = msgEl.querySelector('.message-body');
    if (!body) return id;

    // Calculate reading time
    const wordCount = (data.answer || '').split(/\s+/).length;
    const readingTime = Math.max(1, Math.ceil(wordCount / 200));

    const productivityBar = document.createElement('div');
    productivityBar.className = 'msg-productivity-bar';
    productivityBar.innerHTML = `
        <button class="msg-rate-btn up" onclick="rateMessage(this, 'up')" title="Helpful">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z"/>
                <path d="M7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/>
            </svg>
        </button>
        <button class="msg-rate-btn down" onclick="rateMessage(this, 'down')" title="Not helpful">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z"/>
                <path d="M17 2h3a2 2 0 012 2v7a2 2 0 01-2 2h-3"/>
            </svg>
        </button>
        <button class="msg-save-btn" onclick="saveToNotebook(this)" title="Save to notebook">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>
            </svg>
            Save
        </button>
        <span class="msg-reading-time">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
            </svg>
            ${readingTime} min read
        </span>
    `;
    body.appendChild(productivityBar);

    return id;
};

function rateMessage(btn, direction) {
    const bar = btn.closest('.msg-productivity-bar');
    bar.querySelectorAll('.msg-rate-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active', direction);
    showToast(direction === 'up' ? '👍 Marked as helpful' : '👎 Feedback recorded');
}

function saveToNotebook(btn) {
    const body = btn.closest('.message-body');
    const contentEl = body?.querySelector('.message-content');
    const content = contentEl?.innerText || '';
    btn.classList.add('saved');
    btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Saved`;
    openNotebookModal(content);
}

// Initialize badges on load
document.addEventListener('DOMContentLoaded', () => {
    updateNotebookBadge();
    updateCollectionBadge();
    
    if (window.mermaid) {
        window.mermaid.initialize({
            startOnLoad: false,
            theme: 'dark',
            securityLevel: 'loose',
            fontFamily: 'Inter, sans-serif'
        });
    }
});

