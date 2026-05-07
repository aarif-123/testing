// ═══════════════════════════════════════════════
// AETHER v7.0 — RESEARCHER PRODUCTIVITY TOOLS
// Reading Queue, Citation Manager, Research Workflows
// ═══════════════════════════════════════════════

// ── READING QUEUE ──
const ReadingQueue = {
    KEY: 'aether_reading_queue',
    get() { try { return JSON.parse(localStorage.getItem(this.KEY) || '[]'); } catch { return []; } },
    save(q) { localStorage.setItem(this.KEY, JSON.stringify(q)); this.updateBadge(); },
    add(paper, priority = 'normal') {
        const q = this.get();
        if (q.find(p => p.title === paper.title)) { showToast('Already in queue'); return; }
        q.push({ ...paper, priority, added: new Date().toISOString(), status: 'unread', notes: '' });
        this.save(q);
        showToast('📚 Added to reading queue');
    },
    remove(idx) { const q = this.get(); q.splice(idx, 1); this.save(q); },
    toggleStatus(idx) {
        const q = this.get();
        q[idx].status = q[idx].status === 'read' ? 'unread' : 'read';
        this.save(q);
    },
    setPriority(idx, p) { const q = this.get(); q[idx].priority = p; this.save(q); },
    updateBadge() {
        const badge = document.getElementById('queueBadge');
        if (badge) badge.textContent = this.get().filter(p => p.status === 'unread').length;
    },
    render() {
        const grid = document.getElementById('readingQueueGrid');
        if (!grid) return;
        const q = this.get();
        if (!q.length) {
            grid.innerHTML = `<div class="notebook-empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>
                <h3>Reading queue is empty</h3>
                <p>Add papers from search results to build your reading list with priorities.</p>
            </div>`;
            return;
        }
        const priorityOrder = { high: 0, normal: 1, low: 2 };
        const sorted = [...q].map((p, i) => ({ ...p, _idx: i })).sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]);
        grid.innerHTML = sorted.map(p => {
            const prColor = { high: 'var(--accent-red)', normal: 'var(--primary-light)', low: 'var(--text-muted)' }[p.priority];
            const statusIcon = p.status === 'read' ? '✅' : '📖';
            return `<div class="rq-card ${p.status}" data-idx="${p._idx}">
                <div class="rq-card-top">
                    <span class="rq-priority" style="color:${prColor}">${p.priority.toUpperCase()}</span>
                    <button class="rq-remove" onclick="ReadingQueue.remove(${p._idx});ReadingQueue.render()" title="Remove">×</button>
                </div>
                <div class="rq-title">${escapeHtml(p.title || 'Untitled')}</div>
                <div class="rq-meta">${p.authors ? escapeHtml(p.authors.substring(0, 40)) : 'Unknown'} · ${p.year || '—'}</div>
                ${p.domain ? `<span class="rq-domain">${escapeHtml(p.domain)}</span>` : ''}
                <div class="rq-actions">
                    <button onclick="ReadingQueue.toggleStatus(${p._idx});ReadingQueue.render()" class="rq-btn">${statusIcon} ${p.status === 'read' ? 'Read' : 'Mark read'}</button>
                    <select onchange="ReadingQueue.setPriority(${p._idx},this.value);ReadingQueue.render()" class="rq-select">
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
    KEY: 'aether_citations',
    get() { try { return JSON.parse(localStorage.getItem(this.KEY) || '[]'); } catch { return []; } },
    save(c) { localStorage.setItem(this.KEY, JSON.stringify(c)); this.updateBadge(); },
    add(paper) {
        const c = this.get();
        if (c.find(p => p.title === paper.title)) { showToast('Citation already saved'); return; }
        c.push({ ...paper, added: new Date().toISOString() });
        this.save(c);
        showToast('📎 Citation saved');
    },
    remove(idx) { const c = this.get(); c.splice(idx, 1); this.save(c); },
    updateBadge() {
        const badge = document.getElementById('citeBadge');
        if (badge) badge.textContent = this.get().length;
    },
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
            grid.innerHTML = `<div class="notebook-empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <h3>No citations saved</h3>
                <p>Save citations from papers to export as BibTeX or APA format.</p>
            </div>`;
            return;
        }
        grid.innerHTML = c.map((p, i) => `<div class="cite-card">
            <button class="notebook-card-delete" onclick="CitationManager.remove(${i});CitationManager.render()" title="Remove">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
            <div class="cite-title">${escapeHtml(p.title || 'Untitled')}</div>
            <div class="cite-meta">${escapeHtml(p.authors || 'Unknown')} · ${p.year || '—'}</div>
            ${p.domain ? `<span class="rq-domain">${escapeHtml(p.domain)}</span>` : ''}
            <div class="cite-preview">${escapeHtml(this.toAPA(p))}</div>
        </div>`).join('');
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
        <div class="wf-card" onclick="startWorkflow(${i})">
            <div class="wf-icon">${wf.icon}</div>
            <div class="wf-info">
                <div class="wf-name">${wf.name}</div>
                <div class="wf-desc">${wf.desc}</div>
            </div>
            <div class="wf-steps-count">${wf.steps.length} steps</div>
        </div>
    `).join('');
}

function startWorkflow(idx) {
    const wf = ResearchWorkflows[idx];
    if (!wf) return;
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
    panel.innerHTML = `
        <div class="wf-panel-header">
            <span class="wf-panel-icon">${wf.icon}</span>
            <span class="wf-panel-title">${wf.name}</span>
            <button class="wf-panel-close" onclick="document.getElementById('activeWorkflowPanel').style.display='none'">×</button>
        </div>
        <div class="wf-steps-list">
            ${wf.steps.map((s, i) => `
                <button class="wf-step-btn" onclick="useWorkflowStep(this, '${escapeHtml(s).replace(/'/g, "\\'")}')">
                    <span class="wf-step-num">${i + 1}</span>
                    <span class="wf-step-text">${s}</span>
                </button>
            `).join('')}
        </div>
    `;
    showToast(`${wf.icon} ${wf.name} workflow started`);
}

function useWorkflowStep(btn, text) {
    const input = document.getElementById('queryInput');
    if (input) {
        input.value = text;
        input.dispatchEvent(new Event('input'));
        input.focus();
    }
    btn.classList.add('wf-step-used');
}

// ── ADD "Add to Queue" / "Cite" BUTTONS TO PAPER CARDS ──
function enhancePaperCards() {
    document.querySelectorAll('.premium-card, .paper-card, .source-card').forEach(card => {
        if (card.dataset.enhanced) return;
        card.dataset.enhanced = 'true';
        const titleEl = card.querySelector('.card-title, .paper-card-title');
        const title = titleEl?.textContent || '';
        const metaEls = card.querySelectorAll('.card-meta span, .paper-card-year, .meta-year, .meta-author');
        let authors = '', year = '', domain = '';
        metaEls.forEach(el => {
            const t = el.textContent.trim();
            if (/^\d{4}$/.test(t)) year = t;
            else if (el.classList.contains('domain-tag') || el.classList.contains('paper-card-domain') || el.classList.contains('premium-tag')) domain = t;
            else if (!authors) authors = t;
        });
        const domainEl = card.querySelector('.domain-tag, .paper-card-domain, .premium-tag');
        if (domainEl) domain = domainEl.textContent.trim();
        
        const bar = document.createElement('div');
        bar.className = 'paper-action-bar';
        bar.innerHTML = `
            <button class="pa-btn" onclick="event.stopPropagation();ReadingQueue.add({title:'${escapeHtml(title).replace(/'/g,"\\'")}',authors:'${escapeHtml(authors).replace(/'/g,"\\'")}',year:'${year}',domain:'${escapeHtml(domain).replace(/'/g,"\\'")}'})" title="Add to reading queue">📚 Queue</button>
            <button class="pa-btn" onclick="event.stopPropagation();CitationManager.add({title:'${escapeHtml(title).replace(/'/g,"\\'")}',authors:'${escapeHtml(authors).replace(/'/g,"\\'")}',year:'${year}',domain:'${escapeHtml(domain).replace(/'/g,"\\'")}'})" title="Save citation">📎 Cite</button>
        `;
        card.appendChild(bar);
    });
}

// Watch for new paper cards
const _paperCardObserver = new MutationObserver(() => setTimeout(enhancePaperCards, 300));
_paperCardObserver.observe(document.body, { childList: true, subtree: true });

// ── INIT ──
document.addEventListener('DOMContentLoaded', () => {
    ReadingQueue.updateBadge();
    CitationManager.updateBadge();
    renderWorkflows();
    enhancePaperCards();
});
