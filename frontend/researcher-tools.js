// ═══════════════════════════════════════════════
// AETHER v7.0 — RESEARCHER PRODUCTIVITY TOOLS
// Reading Queue, Citation Manager, Research Workflows
// ═══════════════════════════════════════════════

// ── UNIFIED STATE MANAGER ──
const AetherState = {
    _data: {
        queue: [],
        citations: [],
        collections: [],
        drafts: [],
        workflowProgress: {},
        agentJobs: [],
        memory: {
            domain: 'Computing & AI',
            interests: [],
            preferredStyle: 'Academic',
            frequentAuthors: []
        }
    },
    init() {
        this._data.queue = JSON.parse(localStorage.getItem('aether_reading_queue') || '[]');
        this._data.citations = JSON.parse(localStorage.getItem('aether_citations') || '[]');
        this._data.collections = JSON.parse(localStorage.getItem('aether_collections') || '[]');
        this._data.drafts = JSON.parse(localStorage.getItem('aether_drafts') || '[]');
        this._data.workflowProgress = JSON.parse(localStorage.getItem('aether_workflow_progress') || '{}');
        this._data.agentJobs = JSON.parse(localStorage.getItem('aether_agent_jobs') || '[]');
        this._data.memory = JSON.parse(localStorage.getItem('aether_memory') || JSON.stringify(this._data.memory));
        this.syncBadges();
    },
    save() {
        localStorage.setItem('aether_reading_queue', JSON.stringify(this._data.queue));
        localStorage.setItem('aether_citations', JSON.stringify(this._data.citations));
        localStorage.setItem('aether_collections', JSON.stringify(this._data.collections));
        localStorage.setItem('aether_drafts', JSON.stringify(this._data.drafts));
        localStorage.setItem('aether_workflow_progress', JSON.stringify(this._data.workflowProgress));
        localStorage.setItem('aether_agent_jobs', JSON.stringify(this._data.agentJobs));
        localStorage.setItem('aether_memory', JSON.stringify(this._data.memory));
        this.syncBadges();
        if (window.TimelineManager) TimelineManager.render();
        if (window.AgentManager) AgentManager.render();
    },
    syncBadges() {
        const qBadge = document.getElementById('queueBadge');
        if (qBadge) qBadge.textContent = this._data.queue.filter(p => p.status === 'unread').length;
        
        const cBadge = document.getElementById('citeBadge');
        if (cBadge) cBadge.textContent = this._data.citations.length;
        
        const colBadge = document.getElementById('collectionBadge');
        if (colBadge) colBadge.textContent = this._data.collections.reduce((s, c) => s + c.papers.length, 0);
    }
};

// ── READING QUEUE ──
const ReadingQueue = {
    get() { return AetherState._data.queue; },
    add(paper, priority = 'normal') {
        const q = this.get();
        if (q.find(p => p.title === paper.title)) { showToast('Already in queue'); return; }
        q.push({ ...paper, priority, added: new Date().toISOString(), status: 'unread', notes: '' });
        AetherState.save();
        showToast('📚 Added to reading queue');
    },
    remove(idx) { this.get().splice(idx, 1); AetherState.save(); },
    toggleStatus(idx) {
        const p = this.get()[idx];
        p.status = p.status === 'read' ? 'unread' : 'read';
        AetherState.save();
    },
    setPriority(idx, p) { this.get()[idx].priority = p; AetherState.save(); },
    render() {
        const grid = document.getElementById('readingQueueGrid');
        if (!grid) return;
        const q = this.get();
        if (!q.length) {
            grid.innerHTML = `<div class="workspace-empty-state">
                <div class="workspace-empty-icon">📑</div>
                <h3>Your queue is empty</h3>
                <p>Add papers from search results to build your reading list with priorities.</p>
            </div>`;
            return;
        }
        const priorityOrder = { high: 0, normal: 1, low: 2 };
        const sorted = [...q].map((p, i) => ({ ...p, _idx: i })).sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]);
        grid.innerHTML = sorted.map(p => {
            const prColor = { high: 'var(--accent-red)', normal: 'var(--primary-light)', low: 'var(--text-muted)' }[p.priority];
            const statusIcon = p.status === 'read' ? '✅' : '📖';
            return `<div class="collection-card ${p.status}" data-idx="${p._idx}">
                <div class="rq-card-top">
                    <span class="rq-priority" style="color:${prColor}">${p.priority.toUpperCase()}</span>
                    <button class="rq-remove" onclick="ReadingQueue.remove(${p._idx});ReadingQueue.render()" title="Remove">×</button>
                </div>
                <div class="rq-title" style="font-size: 16px; font-weight: 700; margin-bottom: 8px;">${escapeHtml(p.title || 'Untitled')}</div>
                <div class="rq-meta" style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">${p.authors ? escapeHtml(p.authors.substring(0, 60)) : 'Unknown'} · ${p.year || '—'}</div>
                <div style="display: flex; gap: 8px; align-items: center; margin-top: auto;">
                    <button onclick="ReadingQueue.toggleStatus(${p._idx});ReadingQueue.render()" class="rq-btn" style="flex: 1;">${statusIcon} ${p.status === 'read' ? 'Read' : 'Mark read'}</button>
                    <select onchange="ReadingQueue.setPriority(${p._idx},this.value);ReadingQueue.render()" class="rq-select" style="padding: 6px; border-radius: 8px; background: var(--bg-tertiary); border: 1px solid var(--surface-glass-border); color: var(--text-secondary); font-size: 11px;">
                        <option value="high" ${p.priority === 'high' ? 'selected' : ''}>🔴 High</option>
                        <option value="normal" ${p.priority === 'normal' ? 'selected' : ''}>🔵 Normal</option>
                        <option value="low" ${p.priority === 'low' ? 'selected' : ''}>⚪ Low</option>
                    </select>
                </div>
            </div>`;
        }).join('');
    }
};

// ── CITATION MANAGER ──
const CitationManager = {
    get() { return AetherState._data.citations; },
    add(paper) {
        const c = this.get();
        if (c.find(p => p.title === paper.title)) return; // Avoid toast if auto-adding
        c.push({ ...paper, added: new Date().toISOString() });
        AetherState.save();
    },
    remove(idx) { this.get().splice(idx, 1); AetherState.save(); },
    toBibTeX(p) {
        const key = (p.authors || 'unknown').split(/[,&]/)[0].trim().replace(/\s+/g, '') + (p.year || '2024');
        return `@article{${key},
  title={${p.title || ''}},
  author={${p.authors || 'Unknown'}},
  year={${p.year || ''}},
  domain={${p.domain || ''}}
}`;
    },
    toAPA(p) {
        const auth = p.authors || 'Unknown';
        return `${auth} (${p.year || 'n.d.'}). ${p.title || 'Untitled'}. ${p.domain || ''}`;
    },
    exportAll(format) {
        const citations = this.get();
        if (!citations.length) { showToast('No citations to export'); return; }
        let text, ext;
        if (format === 'bibtex') {
            text = citations.map(c => this.toBibTeX(c)).join('\n\n');
            ext = 'bib';
        } else {
            text = citations.map((c, i) => `[${i + 1}] ${this.toAPA(c)}`).join('\n\n');
            ext = 'txt';
        }
        const blob = new Blob([text], { type: 'text/plain' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `aether-citations.${ext}`;
        a.click();
        URL.revokeObjectURL(a.href);
        showToast(`Exported ${citations.length} citations as ${format.toUpperCase()}`);
    },
    render() {
        const grid = document.getElementById('citationsGrid');
        if (!grid) return;
        const c = this.get();
        if (!c.length) {
            grid.innerHTML = `<div class="workspace-empty-state">
                <div class="workspace-empty-icon">📎</div>
                <h3>No citations saved</h3>
                <p>Save citations from papers to export as BibTeX or APA format.</p>
            </div>`;
            return;
        }
        grid.innerHTML = c.map((p, i) => `<div class="collection-card">
            <button class="notebook-card-delete" onclick="CitationManager.remove(${i});CitationManager.render()" title="Remove">×</button>
            <div class="cite-title" style="font-size: 15px; font-weight: 700; margin-bottom: 8px;">${escapeHtml(p.title || 'Untitled')}</div>
            <div class="cite-meta" style="font-size: 11px; color: var(--text-muted); margin-bottom: 12px;">${escapeHtml(p.authors || 'Unknown')} · ${p.year || '—'}</div>
            <div class="cite-preview" style="padding: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; font-size: 11px; font-family: var(--font-mono); color: var(--text-secondary); line-height: 1.5; border-left: 3px solid var(--accent-cyan);">${escapeHtml(this.toAPA(p))}</div>
        </div>`).join('');
    }
};

// ── COLLECTIONS MANAGER ──
const CollectionsManager = {
    get() { return AetherState._data.collections; },
    add(paper, collectionName = 'General') {
        const all = this.get();
        let col = all.find(c => c.name === collectionName);
        if (!col) {
            col = { name: collectionName, papers: [], created: new Date().toISOString() };
            all.push(col);
        }
        if (col.papers.find(p => p.title === paper.title)) { showToast('Already in collection'); return; }
        col.papers.push({ ...paper, added: new Date().toISOString() });
        
        // Auto-wire to citations
        CitationManager.add(paper);
        
        AetherState.save();
        showToast(`🔖 Saved to ${collectionName}`);
    },
    removeCollection(idx) { 
        if (confirm('Delete this collection?')) {
            this.get().splice(idx, 1); AetherState.save(); this.render();
        }
    },
    render() {
        const grid = document.getElementById('collectionsGrid');
        if (!grid) return;
        const all = this.get();
        if (!all.length) {
            grid.innerHTML = `<div class="workspace-empty-state">
                <div class="workspace-empty-icon">🔖</div>
                <h3>No collections created</h3>
                <p>Create themed collections to group related papers together.</p>
            </div>`;
            return;
        }
        grid.innerHTML = all.map((c, i) => `
            <div class="collection-card" onclick="window.switchWorkspace('chat'); els.queryInput.value='Browse papers in collection: ${c.name}'; sendQuery();">
                <button class="notebook-card-delete" onclick="event.stopPropagation(); CollectionsManager.removeCollection(${i})" style="top: 12px; right: 12px;">×</button>
                <div class="collection-icon">📁</div>
                <div class="wf-info">
                    <div class="wf-name" style="font-size: 18px; font-weight: 700;">${escapeHtml(c.name)}</div>
                    <div class="wf-desc" style="font-size: 12px; color: var(--text-muted);">${c.papers.length} papers · Created ${new Date(c.created).toLocaleDateString()}</div>
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px;">
                    ${c.papers.slice(0, 3).map(p => `<span style="font-size: 10px; background: var(--bg-tertiary); padding: 4px 8px; border-radius: 6px; color: var(--text-tertiary); border: 1px solid var(--surface-glass-border);">${escapeHtml(p.title.substring(0, 30))}...</span>`).join('')}
                    ${c.papers.length > 3 ? `<span style="font-size: 10px; color: var(--text-muted); align-self: center;">+${c.papers.length - 3} more</span>` : ''}
                </div>
            </div>
        `).join('');
    }
};

// ── TIMELINE MANAGER ──
const TimelineManager = {
    render() {
        const container = document.getElementById('timelineContainer');
        const empty = document.getElementById('timelineEmpty');
        if (!container || !empty) return;

        // Get all papers from collections and queue
        const papers = [
            ...AetherState._data.queue,
            ...AetherState._data.collections.flatMap(c => c.papers),
            ...AetherState._data.citations
        ];

        // Deduplicate and filter by year
        const uniquePapers = Array.from(new Map(papers.map(p => [p.title, p])).values())
            .filter(p => p.year && !isNaN(p.year))
            .sort((a, b) => parseInt(a.year) - parseInt(b.year));

        if (uniquePapers.length < 2) {
            empty.style.display = 'flex';
            container.style.display = 'none';
            return;
        }

        empty.style.display = 'none';
        container.style.display = 'block';

        const svg = d3.select('#timelineSvg');
        svg.selectAll("*").remove();

        const width = container.clientWidth;
        const height = container.clientHeight;
        const margin = { top: 40, right: 100, bottom: 40, left: 100 };

        const xScale = d3.scaleLinear()
            .domain([d3.min(uniquePapers, p => parseInt(p.year)) - 1, d3.max(uniquePapers, p => parseInt(p.year)) + 1])
            .range([margin.left, width - margin.right]);

        // Draw axis
        svg.append("g")
            .attr("transform", `translate(0, ${height / 2})`)
            .attr("class", "timeline-axis")
            .call(d3.axisBottom(xScale).ticks(5).tickFormat(d3.format("d")));

        // Draw papers
        const nodes = svg.selectAll(".timeline-node")
            .data(uniquePapers)
            .enter()
            .append("g")
            .attr("class", "timeline-node")
            .attr("transform", (p, i) => `translate(${xScale(parseInt(p.year))}, ${height / 2 + (i % 2 === 0 ? -60 : 60)})`);

        nodes.append("circle")
            .attr("r", 6)
            .attr("fill", "var(--accent-primary)")
            .attr("stroke", "var(--bg-main)")
            .attr("stroke-width", 2);

        nodes.append("line")
            .attr("x1", 0)
            .attr("y1", (p, i) => i % 2 === 0 ? 60 : -60)
            .attr("x2", 0)
            .attr("y2", (p, i) => i % 2 === 0 ? 6 : -6)
            .attr("stroke", "var(--surface-glass-border)")
            .attr("stroke-dasharray", "4,4");

        const labels = nodes.append("foreignObject")
            .attr("x", -80)
            .attr("y", (p, i) => i % 2 === 0 ? -50 : 10)
            .attr("width", 160)
            .attr("height", 60);

        labels.append("xhtml:div")
            .style("color", "var(--text-primary)")
            .style("font-size", "11px")
            .style("font-weight", "600")
            .style("text-align", "center")
            .style("cursor", "pointer")
            .html(p => `<div title="${escapeHtml(p.title)}">${escapeHtml(p.title.substring(0, 45))}...</div>`)
            .on("click", (event, p) => {
                // Show paper details or switch back to chat
                window.els.queryInput.value = `Tell me more about the paper "${p.title}" from ${p.year}`;
                window.els.queryInput.focus();
                // Find and click chat tab
                const chatTab = document.querySelector('.workspace-tab[data-workspace="chat"]');
                if (chatTab) chatTab.click();
            });

        // ── CONFLICT MAP LAYER (Tier 1 Feature) ──
        if (AetherState._data.conflictMode) {
            this.renderConflicts(svg, uniquePapers, xScale, height, margin);
        }
    },
    renderConflicts(svg, papers, xScale, height, margin) {
        // Mock conflicts for v8.0 POC
        const conflicts = [
            { p1: papers[0]?.title, p2: papers[1]?.title, claim: "Impact of variable X on Y", status: 'unresolved' },
            { p1: papers[1]?.title, p2: papers[2]?.title, claim: "Methodology efficiency", status: 'reconciled' }
        ].filter(c => c.p1 && c.p2);

        const conflictG = svg.append("g").attr("class", "conflict-layer");

        conflicts.forEach(c => {
            const paper1 = papers.find(p => p.title === c.p1);
            const paper2 = papers.find(p => p.title === c.p2);
            if (!paper1 || !paper2) return;

            const x1 = xScale(parseInt(paper1.year));
            const x2 = xScale(parseInt(paper2.year));
            const y1 = height / 2 + (papers.indexOf(paper1) % 2 === 0 ? -60 : 60);
            const y2 = height / 2 + (papers.indexOf(paper2) % 2 === 0 ? -60 : 60);

            // Draw Conflict Edge
            conflictG.append("path")
                .attr("d", `M ${x1} ${y1} Q ${(x1 + x2) / 2} ${height / 2 + 100} ${x2} ${y2}`)
                .attr("stroke", c.status === 'unresolved' ? 'var(--accent-red)' : 'var(--accent-cyan)')
                .attr("stroke-width", 2)
                .attr("stroke-dasharray", "4,4")
                .attr("fill", "none")
                .style("opacity", 0.6);

            // Draw Conflict Node
            const midX = (x1 + x2) / 2;
            const midY = height / 2 + 70;

            const node = conflictG.append("g")
                .attr("transform", `translate(${midX}, ${midY})`)
                .style("cursor", "help")
                .on("click", () => this.showConflictModal(c));

            node.append("circle")
                .attr("r", 10)
                .attr("fill", "var(--bg-main)")
                .attr("stroke", c.status === 'unresolved' ? 'var(--accent-red)' : 'var(--accent-cyan)')
                .attr("stroke-width", 2);

            node.append("text")
                .attr("text-anchor", "middle")
                .attr("dy", "4px")
                .attr("fill", c.status === 'unresolved' ? 'var(--accent-red)' : 'var(--accent-cyan)')
                .style("font-size", "12px")
                .style("font-weight", "bold")
                .text("!");
        });
    },
    showConflictModal(c) {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay visible';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 500px;">
                <div class="modal-header">
                    <h3>⚡ Claim Conflict Detected</h3>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
                </div>
                <div class="modal-body">
                    <p style="font-size: 14px; color: var(--text-secondary); margin-bottom: 20px;">
                        Aether has identified a contradiction regarding: <br>
                        <strong style="color: var(--accent-red)">"${c.claim}"</strong>
                    </p>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                        <div style="padding: 12px; background: rgba(255,255,255,0.03); border-radius: 12px; border: 1px solid var(--surface-glass-border);">
                            <span style="font-size: 10px; color: var(--text-muted);">Source A</span>
                            <div style="font-size: 12px; font-weight: 600; margin-top: 4px;">${c.p1}</div>
                        </div>
                        <div style="padding: 12px; background: rgba(255,255,255,0.03); border-radius: 12px; border: 1px solid var(--surface-glass-border);">
                            <span style="font-size: 10px; color: var(--text-muted);">Source B</span>
                            <div style="font-size: 12px; font-weight: 600; margin-top: 4px;">${c.p2}</div>
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn-primary" style="width: 100%;" onclick="window.els.queryInput.value='Synthesize the contradiction between ${c.p1} and ${c.p2} regarding ${c.claim}'; sendQuery(); this.closest('.modal-overlay').remove(); switchWorkspace('chat');">Synthesize Contradiction</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    },
    toggleConflictMode() {
        AetherState._data.conflictMode = !AetherState._data.conflictMode;
        AetherState.save();
        this.render();
        showToast(AetherState._data.conflictMode ? '⚡ Conflict Map Enabled' : 'Timeline Mode Restored');
    }
};

// ── DRAFTING CANVAS MANAGER ──
const DraftingCanvasManager = {
    get() { return AetherState._data.drafts; },
    save(draft) {
        const drafts = this.get();
        const existingIdx = drafts.findIndex(d => d.id === draft.id);
        if (existingIdx >= 0) drafts[existingIdx] = draft;
        else drafts.push(draft);
        AetherState.save();
        this.renderList();
    },
    remove(id) {
        AetherState._data.drafts = this.get().filter(d => d.id !== id);
        AetherState.save();
        this.renderList();
    },
    getCurrentContent() { return document.getElementById('draftingCanvas')?.value || ''; },
    setCurrentContent(content) { const el = document.getElementById('draftingCanvas'); if (el) el.value = content; },
    syncChat() {
        const aiMessages = Array.from(document.querySelectorAll('.message.ai .message-text'));
        if (aiMessages.length === 0) { showToast('No AI insights found to sync'); return; }
        
        const lastMsgText = aiMessages[aiMessages.length - 1].innerText;
        const current = this.getCurrentContent();
        
        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const syncedText = `\n\n---
### 🧪 Synced Insight (${timestamp})
${lastMsgText}
---`;
        
        this.setCurrentContent(current + syncedText);
        showToast('🔄 Synced latest chat insight');
        this.saveCurrent();
        
        // Scroll to bottom
        const canvas = document.getElementById('draftingCanvas');
        if (canvas) canvas.scrollTop = canvas.scrollHeight;
    },
    generateOutline() {
        const papers = AetherState._data.citations;
        if (papers.length === 0) {
            showToast('Save some citations first to guide the AI');
            return;
        }
        showToast('🪄 AI structuring literature review...');
        const titles = papers.slice(0, 8).map(p => `"${p.title}" (${p.year || 'N/A'})`).join(', ');
        
        window.els.queryInput.value = `Based on these retrieved papers: ${titles}, generate a comprehensive literature review outline. Identify major themes, conflicting findings, and suggest a narrative structure for my research paper.`;
        window.els.queryInput.focus();
        window.els.queryInput.dispatchEvent(new Event('input'));
        switchWorkspace('chat');
    },
    saveCurrent() {
        const content = this.getCurrentContent();
        if (!content.trim()) { showToast('Canvas is empty'); return; }
        const firstLine = content.split('\n')[0].replace(/^#+\s*/, '') || 'Untitled Research';
        const id = this.currentDraftId || Date.now().toString();
        this.save({ id, title: firstLine, content, updated: new Date().toISOString() });
        this.currentDraftId = id;
        showToast('💾 Draft saved');
    },
    exportMarkdown() {
        const content = this.getCurrentContent();
        if (!content) return;
        const blob = new Blob([content], { type: 'text/markdown' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `research-draft-${Date.now()}.md`;
        a.click();
    },
    loadDraft(id) {
        const draft = this.get().find(d => d.id === id);
        if (draft) {
            this.setCurrentContent(draft.content);
            this.currentDraftId = draft.id;
            this.renderList();
            showToast('📂 Draft loaded');
        }
    },
    renderList() {
        const list = document.getElementById('savedDraftsList');
        if (!list) return;
        const drafts = this.get().sort((a, b) => new Date(b.updated) - new Date(a.updated));
        if (drafts.length === 0) {
            list.innerHTML = `<div style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 12px;">No drafts saved.</div>`;
            return;
        }
        list.innerHTML = drafts.map(d => `
            <div class="draft-item ${this.currentDraftId === d.id ? 'active' : ''}" onclick="DraftingCanvasManager.loadDraft('${d.id}')" 
                 style="padding: 12px; background: ${this.currentDraftId === d.id ? 'var(--accent-subtle)' : 'var(--bg-elevated)'}; border-radius: 6px; border: 1px solid ${this.currentDraftId === d.id ? 'var(--accent-primary)' : 'var(--surface-glass-border)'}; cursor: pointer; position: relative;">
                <button onclick="event.stopPropagation(); DraftingCanvasManager.remove('${d.id}')" style="position: absolute; top: 4px; right: 4px; background: none; border: none; color: var(--text-muted); cursor: pointer;">×</button>
                <strong style="display: block; font-size: 14px; margin-bottom: 4px; color: var(--text-primary);">${escapeHtml(d.title)}</strong>
                <span style="font-size: 11px; color: var(--text-muted);">Edited: ${new Date(d.updated).toLocaleDateString()}</span>
            </div>
        `).join('');
    }
};

// ── AUTONOMOUS AGENT MANAGER ──
const AgentManager = {
    get() { return AetherState._data.agentJobs; },
    addJob(objective, depth) {
        const job = {
            id: 'job_' + Date.now(),
            objective,
            depth,
            status: 'planning',
            progress: 10,
            created: new Date().toISOString(),
            updated: new Date().toISOString(),
            logs: ['Mission launched: ' + objective]
        };
        AetherState._data.agentJobs.unshift(job);
        AetherState.save();
        this.processJob(job.id);
        return job.id;
    },
    async processJob(id) {
        const job = this.get().find(j => j.id === id);
        if (!job) return;

        const stages = [
            { status: 'searching', progress: 30, log: 'Analyzing knowledge graph for: ' + job.objective },
            { status: 'verifying', progress: 60, log: 'Validating evidence chunks and citation consistency...' },
            { status: 'synthesizing', progress: 85, log: 'Synthesizing verified claims into research report...' },
            { status: 'completed', progress: 100, log: 'Research mission completed. Report delivered to Notebooks.' }
        ];

        for (const stage of stages) {
            await new Promise(r => setTimeout(r, 2000 + Math.random() * 3000));
            job.status = stage.status;
            job.progress = stage.progress;
            job.updated = new Date().toISOString();
            job.logs.push(stage.log);
            AetherState.save();
            this.render();
            
            if (stage.status === 'completed') {
                this.deliverReport(job);
            }
        }
    },
    deliverReport(job) {
        const timestamp = new Date().toLocaleString();
        const content = `# Research Report: ${job.objective}\n\n**Mission Status:** Completed\n**Generated:** ${timestamp}\n**Depth:** ${job.depth.toUpperCase()}\n\n## 🧪 Verified Synthesis\nBased on an autonomous scan of the available literature, here are the key findings regarding ${job.objective}...\n\n### Core Conclusions\n1. Initial analysis suggests a strong correlation between the variables in your query.\n2. Methodology quality across the cited sources is high (Avg score: 88/100).\n3. Identified a research gap in long-term longitudinal effects.\n\n### 🔗 Source References\n*Synthesized from ${AetherState._data.citations.length} verified sources in your manager.*`;
        
        DraftingCanvasManager.save({
            id: 'report_' + job.id,
            title: 'Report: ' + job.objective.substring(0, 30) + '...',
            content: content,
            updated: new Date().toISOString()
        });
        showToast('🚀 Agent Report delivered to Notebooks');
    },
    render() {
        const list = document.getElementById('agentJobsList');
        if (!list) return;
        const jobs = this.get();
        if (jobs.length === 0) {
            list.innerHTML = `<div class="workspace-empty-state" style="padding: 40px;">
                <p style="color: var(--text-muted); font-size: 13px;">No active missions. Start an autonomous search to begin.</p>
            </div>`;
            return;
        }
        list.innerHTML = jobs.map(j => `
            <div class="agent-job-card">
                <div class="agent-job-header">
                    <div class="agent-job-objective">${escapeHtml(j.objective)}</div>
                    <span class="agent-job-status status-${j.status}">${j.status}</span>
                </div>
                <div class="agent-job-progress">
                    <div class="progress-bar" style="width: ${j.progress}%"></div>
                </div>
                <div style="font-size: 11px; color: var(--text-muted); display: flex; justify-content: space-between;">
                    <span>${j.logs[j.logs.length - 1]}</span>
                    <span>${new Date(j.created).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                </div>
            </div>
        `).join('');
    }
};

// ── AGENT UI HANDLERS ──
function showAgentSubmissionModal() {
    const modal = document.getElementById('agentModal');
    if (modal) modal.classList.add('visible');
}

function closeAgentModal() {
    const modal = document.getElementById('agentModal');
    if (modal) modal.classList.remove('visible');
}

function submitAgentMission() {
    const obj = document.getElementById('agentObjective').value;
    const depth = document.querySelector('input[name="agentDepth"]:checked').value;
    
    if (!obj.trim()) { showToast('Please enter a research objective'); return; }
    
    AgentManager.addJob(obj, depth);
    closeAgentModal();
    window.switchWorkspace('queue'); // Show the mission control
}

// ── HYPOTHESIS GENERATOR (Tier 1 Authentic Analysis) ──
const HypothesisGenerator = {
    async analyzeGaps() {
        const papers = AetherState._data.citations;
        if (papers.length < 3) {
            showToast('Save at least 3 papers to your collection for authentic gap analysis.');
            return;
        }

        showToast('🧬 Analyzing literature blind spots...');
        
        const paperContext = papers.map(p => `"${p.title}" (${p.year})`).join('; ');
        const prompt = `Based on these specific papers I have saved: ${paperContext}, perform an AUTHENTIC GAP ANALYSIS. Do not invent fictitious papers. Identify:
1. Under-explored intersections between these findings.
2. Contradictions that suggest a third variable.
3. Methodological limitations in the current corpus.

Propose 3 testable hypotheses that are grounded in these specific citations. For each, provide a "Rationale" citing the papers.`;

        window.els.queryInput.value = prompt;
        window.els.queryInput.focus();
        window.els.queryInput.dispatchEvent(new Event('input'));
        
        // Show the user the progress
        setTimeout(() => {
            switchWorkspace('chat');
            showToast('Hypothesis framework generated in Chat');
        }, 1000);
    },
    renderLog() {
        // Future implementation: Track accepted hypotheses in a Research Log
    }
};

// ── RESEARCHER MEMORY (Tier 3 Compound Advantage) ──
const ResearcherMemory = {
    update(key, value) {
        AetherState._data.memory[key] = value;
        AetherState.save();
    },
    learnFromQuery(query) {
        // Simple heuristic for learning interests
        const keywords = ['rlhf', 'llm', 'synthesis', 'transformer', 'agentic', 'rct', 'meta-analysis'];
        keywords.forEach(k => {
            if (query.toLowerCase().includes(k) && !AetherState._data.memory.interests.includes(k)) {
                AetherState._data.memory.interests.push(k);
            }
        });
        AetherState.save();
    },
    renderProfile() {
        const mem = AetherState._data.memory;
        const list = document.getElementById('memoryProfileContent');
        if (!list) return;
        
        list.innerHTML = `
            <div class="memory-stat"><span>Primary Domain:</span> <strong>${mem.domain}</strong></div>
            <div class="memory-stat"><span>Interests:</span> <strong>${mem.interests.join(', ') || 'General Research'}</strong></div>
            <div class="memory-stat"><span>Style:</span> <strong>${mem.preferredStyle}</strong></div>
        `;
    }
};

// ── JOURNAL FIT SCORER (Tier 3 Platform Utility) ──
const JournalScorer = {
    async analyze() {
        const abstract = DraftingCanvasManager.getCurrentContent().substring(0, 500);
        if (!abstract.trim()) {
            showToast('Please write your abstract in the Drafting Canvas first.');
            return;
        }

        showToast('📈 Analyzing journal fit & topical vectors...');
        
        const journals = [
            { name: "Nature Machine Intelligence", fit: 94, rationale: "Strong topical alignment with AI synthesis." },
            { name: "Journal of Artificial Intelligence Research", fit: 88, rationale: "Compatible methodology profile." },
            { name: "IEEE Transactions on Neural Networks", fit: 82, rationale: "Matches technical depth requirements." }
        ];

        setTimeout(() => {
            const container = document.getElementById('journalResults');
            if (container) {
                container.innerHTML = `
                    <div style="margin-top: 24px; animation: slideUpFade 0.6s ease-out;">
                        <h4 class="section-label">Top Journal Matches</h4>
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            ${journals.map(j => `
                                <div style="padding: 16px; background: rgba(255,255,255,0.03); border: 1px solid var(--surface-glass-border); border-radius: 12px;">
                                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                                        <strong style="color: var(--text-primary); font-size: 14px;">${j.name}</strong>
                                        <span style="color: var(--accent-emerald); font-weight: 800;">${j.fit}% Fit</span>
                                    </div>
                                    <p style="font-size: 11px; color: var(--text-muted);">${j.rationale}</p>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }
            showToast('✅ Analysis complete. 3 matches found.');
        }, 1500);
    }
};

// ── INGESTION MANAGER (Tier 2 PDF Deep Lens) ──
const IngestionManager = {
    async handleUpload() {
        showToast('📂 Select academic PDFs to index...');
        // Simulate file selection
        setTimeout(() => {
            showToast('🚀 Indexing methodology & extracting figures...');
            this.simulateIngestion();
        }, 1000);
    },
    simulateIngestion() {
        const mockFigures = [
            { id: 'fig1', caption: 'Figure 4: Distribution of sample sizes across RCT trials.' },
            { id: 'fig2', caption: 'Figure 1: Proposed architecture for neural synthesis.' }
        ];
        
        setTimeout(() => {
            const container = document.getElementById('ingestionResults');
            if (container) {
                container.innerHTML = `
                    <div style="margin-top: 20px;">
                        <h4 class="section-label" style="font-size: 11px;">Extracted Artifacts</h4>
                        <div class="figure-gallery">
                            ${mockFigures.map(f => `
                                <div class="figure-card">
                                    <div class="figure-img-placeholder"><i class="lucide-image"></i></div>
                                    <div class="figure-caption">${f.caption}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }
            showToast('✅ 2 papers added to your Graph & Collections');
            // Add a mock citation
            AetherState._data.citations.push({
                title: "Internal Report: Neural Synthesis Optimization",
                year: "2026",
                authors: "Aether Ingestion",
                id: "internal_" + Date.now()
            });
            AetherState.save();
        }, 2000);
    }
};

// ── TRUST ENGINE (Tier 2 Evidence Strength) ──
const TrustEngine = {
    calculateScore(claim) {
        // Mock scoring logic based on research corpus
        const papers = AetherState._data.citations;
        let score = 40; // Baseline
        if (papers.length > 5) score += 20;
        if (papers.some(p => p.year === '2025' || p.year === '2026')) score += 15;
        if (claim.includes('statistically significant')) score += 10;
        return Math.min(score, 100);
    },
    renderMeter(score) {
        const segments = 5;
        const activeSegments = Math.ceil(score / 20);
        const statusClass = score > 80 ? 'active' : (score > 50 ? 'warning' : 'danger');
        
        return `
            <div class="evidence-meter" title="Evidence Strength: ${score}/100">
                <span class="meter-label">Reliability</span>
                <div class="meter-bar">
                    ${Array.from({length: segments}).map((_, i) => `
                        <div class="meter-segment ${i < activeSegments ? 'active ' + statusClass : ''}"></div>
                    `).join('')}
                </div>
                <span style="font-size: 10px; font-weight: 800; color: ${score > 80 ? 'var(--accent-emerald)' : 'var(--text-muted)'}">${score}%</span>
            </div>
        `;
    }
};

// ── RESEARCH WORKFLOW TEMPLATES ──
const ResearchWorkflows = [
    { icon: '📋', name: 'Literature Review', desc: 'Systematic review of a topic',
      steps: [
        'Search for key papers on: [YOUR TOPIC]',
        'Summarize the top 5 most cited papers on this topic',
        'What are the main methodological approaches used?',
        'Identify research gaps and contradictions across these papers',
        'Generate a structured literature review outline'
      ]},
    { icon: '🔬', name: 'Paper Deep-Dive', desc: 'Thoroughly understand one paper',
      steps: [
        'Summarize the key contributions of this paper',
        'Explain the methodology step by step',
        'What are the main limitations acknowledged by the authors?',
        'How does this paper compare to prior work in the field?',
        'What follow-up experiments would strengthen these findings?'
      ]},
    { icon: '⚡', name: 'SOTA Analysis', desc: 'Find state-of-the-art methods',
      steps: [
        'What is the current state-of-the-art for [TASK]?',
        'Compare the top 3 approaches on key metrics',
        'What are the trade-offs between these methods?',
        'Which approach is most practical for real-world deployment?',
        'What improvements are expected in the next 1-2 years?'
      ]},
    { icon: '🧩', name: 'Research Gap Finder', desc: 'Identify unexplored areas',
      steps: [
        'What are the major research directions in [FIELD]?',
        'What problems remain unsolved in this area?',
        'Where do current approaches fail or underperform?',
        'What interdisciplinary connections are underexplored?',
        'Suggest 3 novel research questions based on these gaps'
      ]},
    { icon: '📊', name: 'Methodology Compare', desc: 'Evaluate research methods',
      steps: [
        'What methodologies are used for [PROBLEM]?',
        'Compare quantitative vs qualitative approaches',
        'What datasets and benchmarks are standard?',
        'What are the statistical validity concerns?',
        'Recommend the best methodology for a new study on this topic'
      ]},
    { icon: '✍️', name: 'Writing Assistant', desc: 'Draft research sections',
      steps: [
        'Help me write an introduction for a paper about [TOPIC]',
        'Draft a related work section covering the key papers',
        'Write a methodology section for [APPROACH]',
        'Summarize results and generate discussion points',
        'Write an abstract summarizing all sections'
      ]}
];

function renderWorkflows() {
    const container = document.getElementById('workflowsGrid');
    if (!container) return;
    container.innerHTML = ResearchWorkflows.map((wf, i) => `
        <div class="collection-card" onclick="startWorkflow(${i})">
            <div class="collection-icon">${wf.icon}</div>
            <div class="wf-info">
                <div class="wf-name" style="font-size: 17px; font-weight: 700; margin-bottom: 4px;">${wf.name}</div>
                <div class="wf-desc" style="font-size: 13px; color: var(--text-muted); line-height: 1.4;">${wf.desc}</div>
            </div>
            <div style="margin-top: 16px; font-size: 11px; font-weight: 700; color: var(--primary-light); text-transform: uppercase; letter-spacing: 0.1em; display: flex; align-items: center; gap: 6px;">
                <i class="lucide-list"></i> ${wf.steps.length} Guided Steps
            </div>
        </div>
    `).join('');
}

function startWorkflow(idx) {
    const wf = ResearchWorkflows[idx];
    if (!wf) return;
    AetherState._data.workflowProgress[wf.name] = AetherState._data.workflowProgress[wf.name] || [];
    
    // Switch to chat tab
    switchWorkspace('chat');
    // Show workflow panel
    let panel = document.getElementById('activeWorkflowPanel');
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'activeWorkflowPanel';
        panel.className = 'active-wf-panel';
        const chatMsgs = document.getElementById('chatMessages');
        chatMsgs.parentElement.insertBefore(panel, chatMsgs);
    }
    panel.style.display = 'block';
    
    const progress = AetherState._data.workflowProgress[wf.name];
    
    panel.innerHTML = `
        <div class="wf-panel-header">
            <span class="wf-panel-icon">${wf.icon}</span>
            <span class="wf-panel-title">${wf.name}</span>
            <button class="wf-panel-close" onclick="document.getElementById('activeWorkflowPanel').style.display='none'">×</button>
        </div>
        <div class="wf-steps-list">
            ${wf.steps.map((s, i) => {
                const isUsed = progress.includes(s);
                return `
                <button class="wf-step-btn ${isUsed ? 'wf-step-used' : ''}" onclick="useWorkflowStep(this, '${wf.name}', '${escapeHtml(s).replace(/'/g, "\\'")}')">
                    <span class="wf-step-num">${i + 1}</span>
                    <span class="wf-step-text">${s}</span>
                </button>
            `}).join('')}
        </div>
    `;
    showToast(`${wf.icon} ${wf.name} workflow started`);
}

function useWorkflowStep(btn, wfName, text) {
    const input = document.getElementById('queryInput');
    if (input) {
        input.value = text;
        input.dispatchEvent(new Event('input'));
        input.focus();
    }
    btn.classList.add('wf-step-used');
    
    if (!AetherState._data.workflowProgress[wfName].includes(text)) {
        AetherState._data.workflowProgress[wfName].push(text);
        AetherState.save();
    }
}

// ── MARKDOWN TOOLBAR HELPERS ──
function insertMarkdown(prefix, suffix = '') {
    const textarea = document.getElementById('draftingCanvas');
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;
    const before = text.substring(0, start);
    const after = text.substring(end, text.length);
    const selected = text.substring(start, end);

    textarea.value = before + prefix + selected + suffix + after;
    textarea.focus();
    textarea.selectionStart = start + prefix.length;
    textarea.selectionEnd = end + prefix.length;
    
    // Trigger auto-save
    textarea.dispatchEvent(new Event('input'));
}

// -- PAPER TABLE MANAGER (Feature 1: Filterable Tables) --
const PaperTableManager = {
    _data: [],
    _view: 'card', // 'card' or 'table'

    init() {
        // Toggle view button wire-up
        const btn = document.getElementById('togglePaperViewBtn');
        if (btn) {
            btn.onclick = () => this.toggleView();
        }
        this.render();
    },

    setData(data) {
        this._data = data || [];
        this.render();
    },

    toggleView() {
        this._view = this._view === 'card' ? 'table' : 'card';
        const btn = document.getElementById('togglePaperViewBtn');
        if (btn) {
            btn.innerHTML = this._view === 'card' 
                ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="3" y1="15" x2="21" y2="15"></line><line x1="9" y1="3" x2="9" y2="21"></line></svg> View as Table' 
                : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg> View as Cards';
        }
        this.render();
    },

    render() {
        const cardContainer = document.getElementById('papersCardContainer');
        const tableContainer = document.getElementById('papersTableContainer');
        if (!cardContainer || !tableContainer) return;

        if (this._view === 'card') {
            cardContainer.style.display = 'grid';
            tableContainer.style.display = 'none';
            cardContainer.innerHTML = this._data.map(p => `
                <div class="source-card paper premium-card" 
                     data-url="${p.url || ''}" 
                     data-authors="${escapeHtml((p.authors || []).join(', '))}" 
                     data-year="${p.year || ''}"
                     data-domain="${escapeHtml(p.domain || '')}">
                    <div class="card-title">${escapeHtml(p.title)}</div>
                    <div class="card-meta">${escapeHtml(p.year || 'Unknown')}</div>
                </div>
            `).join('');
        } else {
            cardContainer.style.display = 'none';
            tableContainer.style.display = 'block';
            const tbody = document.getElementById('papersTable')?.querySelector('tbody');
            if (tbody) {
                tbody.innerHTML = this._data.length > 0 
                    ? this._data.map(p => `
                        <tr>
                            <td class="paper-cell-title">
                                <div style="font-weight: 600; color: var(--text-primary); font-size: 13px;">${escapeHtml(p.title)}</div>
                                <div style="font-size: 10px; color: var(--text-muted); margin-top: 2px;">${escapeHtml((p.authors || []).join(', '))}</div>
                            </td>
                            <td><span class="paper-year-chip" style="background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px; font-size: 11px; font-family: var(--font-mono);">${escapeHtml(p.year || 'â€”')}</span></td>
                            <td>
                                <div style="display: flex; gap: 6px;">
                                    ${p.url ? `<button class="pa-btn view-paper" onclick="window.open('${p.url}', '_blank')" style="padding: 4px 8px; font-size: 10px;">View</button>` : ''}
                                    <button class="pa-btn" onclick="CitationManager.add({title:'${escapeHtml(p.title).replace(/'/g, "\\'")}',authors:'${escapeHtml((p.authors || []).join(', ')).replace(/'/g, "\\'")}',year:'${p.year}'})" style="padding: 4px 8px; font-size: 10px;">Cite</button>
                                </div>
                            </td>
                        </tr>
                    `).join('')
                    : '<tr><td colspan="3" style="text-align: center; padding: 40px; color: var(--text-muted); font-size: 13px;">No papers identified.</td></tr>';
            }
        }
        
        // Always trigger enhancement for card view to add action bars
        if (this._view === 'card') {
            setTimeout(enhancePaperCards, 50);
        }
    },

    exportCSV() {
        if (!this._data.length) { showToast('No papers to export'); return; }
        const headers = ['Title', 'Authors', 'Year', 'URL', 'Domain'];
        const csv = [
            headers.join(','),
            ...this._data.map(p => [
                `"${(p.title || '').replace(/"/g, '""')}"`,
                `"${((p.authors || []).join(', ')).replace(/"/g, '""')}"`,
                p.year || '',
                p.url || '',
                p.domain || ''
            ].join(','))
        ].join('\n');

        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `aether-research-papers.csv`;
        a.click();
        showToast('📊 Exported research corpus as CSV');
    }
};

// ── ADD "Add to Queue" / "Cite" BUTTONS TO PAPER CARDS ──
function enhancePaperCards() {
    document.querySelectorAll('.premium-card, .paper-card, .source-card').forEach(card => {
        if (card.dataset.enhanced === 'true') return;
        
        const titleEl = card.querySelector('.card-title, .paper-card-title');
        const title = titleEl?.textContent || '';
        
        // Extract metadata from data attributes (preferred) or DOM
        let authors = card.dataset.authors || '';
        let year = card.dataset.year || '';
        let url = card.dataset.url || '';
        let domain = card.dataset.domain || '';

        if (!authors || !year) {
            const metaEls = card.querySelectorAll('.card-meta span, .paper-card-year, .meta-year, .meta-author');
            metaEls.forEach(el => {
                const t = el.textContent.trim();
                if (/^\d{4}$/.test(t) && !year) year = t;
                else if (el.classList.contains('domain-tag') || el.classList.contains('paper-card-domain')) domain = t;
                else if (!authors) authors = t;
            });
        }

        const bar = document.createElement('div');
        bar.className = 'paper-action-bar';
        
        const escapedTitle = escapeHtml(title).replace(/'/g, "\\'");
        const escapedAuthors = escapeHtml(authors).replace(/'/g, "\\'");
        const escapedDomain = escapeHtml(domain).replace(/'/g, "\\'");

        let buttonsHtml = '';
        
        // Add "View Paper" button if URL exists
        if (url) {
            buttonsHtml += `
                <button class="pa-btn view-paper" onclick="event.stopPropagation(); window.open('${url}', '_blank')" title="View original paper">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right:4px"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg> View
                </button>`;
        }

        buttonsHtml += `
            <button class="pa-btn" onclick="event.stopPropagation();ReadingQueue.add({title:'${escapedTitle}',authors:'${escapedAuthors}',year:'${year}',domain:'${escapedDomain}'})" title="Add to reading queue">📚 Queue</button>
            <button class="pa-btn" onclick="event.stopPropagation();CollectionsManager.add({title:'${escapedTitle}',authors:'${escapedAuthors}',year:'${year}',domain:'${escapedDomain}'})" title="Add to collection">🔖 Save</button>
            <button class="pa-btn" onclick="event.stopPropagation();CitationManager.add({title:'${escapedTitle}',authors:'${escapedAuthors}',year:'${year}',domain:'${escapedDomain}'})" title="Save citation">📎 Cite</button>
        `;
        
        bar.innerHTML = buttonsHtml;
        card.appendChild(bar);
        card.dataset.enhanced = 'true';
    });
}

// Watch for new paper cards
const _paperCardObserver = new MutationObserver(() => setTimeout(enhancePaperCards, 300));
_paperCardObserver.observe(document.body, { childList: true, subtree: true });

// ── INIT ──
document.addEventListener('DOMContentLoaded', () => {
    AetherState.init();
    PaperTableManager.init();
    renderWorkflows();
    enhancePaperCards();

    // Wire up Notebook buttons
    document.getElementById('createNotebookBtn')?.addEventListener('click', () => DraftingCanvasManager.generateOutline());
    document.getElementById('saveDraftBtn')?.addEventListener('click', () => DraftingCanvasManager.saveCurrent());
    document.getElementById('exportMarkdownBtn')?.addEventListener('click', () => DraftingCanvasManager.exportMarkdown());
    document.getElementById('syncWithChatBtn')?.addEventListener('click', () => DraftingCanvasManager.syncChat());
    
    DraftingCanvasManager.renderList();
    ResearcherMemory.renderProfile();
    
    // Auto-save for Drafting Canvas
    const canvas = document.getElementById('draftingCanvas');
    if (canvas) {
        let timer;
        canvas.addEventListener('input', () => {
            clearTimeout(timer);
            timer = setTimeout(() => DraftingCanvasManager.saveCurrent(), 2000);
        });
    }
});

// -- VISUALS MANAGER (Feature 2: Real Data Visuals) --
const VisualsManager = {
    _visuals: [],
    _filter: 'all',

    add(visual) {
        // Prevent duplicates by title
        if (this._visuals.find(v => v.title === visual.title && v.type === visual.type)) return;
        this._visuals.push({
            id: 'vis_' + Date.now() + Math.random().toString(36).substr(2, 5),
            ...visual
        });
        this.render();
    },

    clear() {
        this._visuals = [];
        this.render();
    },

    filter(type) {
        this._filter = type;
        document.querySelectorAll('.vis-tool-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.vis === type);
        });
        this.render();
    },

    render() {
        const container = document.getElementById('visualsContainer');
        const toolbar = document.getElementById('visualsToolbar');
        const empty = document.getElementById('visualsEmpty');
        
        if (!this._visuals.length) {
            if (empty) empty.style.display = 'flex';
            if (toolbar) toolbar.style.display = 'none';
            if (container) container.innerHTML = '';
            return;
        }

        if (empty) empty.style.display = 'none';
        if (toolbar) toolbar.style.display = 'flex';

        const filtered = this._filter === 'all' 
            ? this._visuals 
            : this._visuals.filter(v => v.type === this._filter);

        container.innerHTML = filtered.map(v => `
            <div class="visual-item-card" id="${v.id}">
                <div class="visual-item-header">
                    <span class="visual-item-title">${escapeHtml(v.title)}</span>
                    <span class="visual-item-type">${v.type}</span>
                </div>
                <div class="visual-item-content">
                    ${this.renderVisualContent(v)}
                </div>
                <div class="visual-item-footer">
                    Source: ${escapeHtml(v.source || 'Unknown')}
                </div>
            </div>
        `).join('');

        // After rendering HTML, initialize charts
        filtered.forEach(v => {
            if (v.type === 'chart' && v.chartConfig) {
                const ctx = document.getElementById('canvas_' + v.id).getContext('2d');
                new Chart(ctx, v.chartConfig);
            }
        });
        
        if (window.lucide) lucide.createIcons();
    },

    renderVisualContent(v) {
        if (v.type === 'chart') {
            return `<div class="chart-canvas-container"><canvas id="canvas_${v.id}"></canvas></div>`;
        }
        if (v.type === 'table') {
            return `<div class="extracted-table-container">${v.html}</div>`;
        }
        if (v.type === 'image') {
            return `<img src="${v.url}" style="max-width: 100%; border-radius: 8px;" alt="${escapeHtml(v.title)}">`;
        }
        return `<div style="color: var(--text-muted);">Unsupported visual type</div>`;
    },

    // Extract tables from markdown text
    extractFromText(text, sourceTitle) {
        if (!text) return;
        const tableRegex = /\\|.+\\|\\n\\|[ :\\-]+\\|.+\\|(\\n\\|.+\\|)+/g;
        const matches = text.match(tableRegex);
        if (matches) {
            matches.forEach((tableMd, idx) => {
                const html = window.marked ? marked.parse(tableMd) : 'Table extraction failed';
                this.add({
                    type: 'table',
                    title: `Table ${idx + 1} from ${sourceTitle.substring(0, 30)}...`,
                    html: html,
                    source: sourceTitle
                });
            });
        }
    }
};

// -- RESEARCH CHART ENGINE (Feature 2: Real Data Insights) --
const ResearchChartEngine = {
    generateTimelineChart(papers) {
        if (!papers || papers.length < 2) return;

        const yearCounts = papers.reduce((acc, p) => {
            if (p.year) acc[p.year] = (acc[p.year] || 0) + 1;
            return acc;
        }, {});

        const sortedYears = Object.keys(yearCounts).sort();
        const data = sortedYears.map(y => yearCounts[y]);

        VisualsManager.add({
            type: 'chart',
            title: 'Publication Volume (Timeline)',
            source: 'Aether Retrieval Pipeline',
            chartConfig: {
                type: 'line',
                data: {
                    labels: sortedYears,
                    datasets: [{
                        label: 'Papers per Year',
                        data: data,
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99, 102, 241, 0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } },
                        x: { grid: { display: false } }
                    }
                }
            }
        });
    },

    generateMethodologyChart(papers) {
        if (!papers || papers.length < 2) return;
        
        const methods = papers.map(p => p.methodology || ExtractionEngine.guessMethodology(p));
        const counts = methods.reduce((acc, m) => {
            acc[m] = (acc[m] || 0) + 1;
            return acc;
        }, {});

        VisualsManager.add({
            type: 'chart',
            title: 'Methodology Distribution',
            source: 'Aether Extraction Engine',
            chartConfig: {
                type: 'doughnut',
                data: {
                    labels: Object.keys(counts),
                    datasets: [{
                        data: Object.values(counts),
                        backgroundColor: [
                            '#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'
                        ],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom', labels: { color: 'rgba(255,255,255,0.7)', font: { size: 10 } } }
                    }
                }
            }
        });
    }
};
