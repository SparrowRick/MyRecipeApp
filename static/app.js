(function () {
    'use strict';

    const body = document.body;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const userId = body.dataset.userId || '';
    let lastTrigger = null;

    function syncDrawerViewport() {
        const viewport = window.visualViewport;
        const height = viewport ? viewport.height : window.innerHeight;
        document.documentElement.style.setProperty('--drawer-viewport-height', `${Math.round(height)}px`);
    }

    function icons() {
        if (window.lucide) window.lucide.createIcons({ attrs: { 'aria-hidden': 'true' } });
    }

    function showToast(message) {
        const region = document.getElementById('toastRegion');
        if (!region) return;
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        region.appendChild(toast);
        window.setTimeout(() => toast.remove(), 3200);
    }
    window.showToast = showToast;

    function addCsrfToForms() {
        document.querySelectorAll('form[method="POST"], form[method="post"]').forEach((form) => {
            if (form.querySelector('input[name="csrf_token"]')) return;
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'csrf_token';
            input.value = csrfToken;
            form.appendChild(input);
        });
    }

    function focusables(container) {
        return Array.from(container.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])')).filter((item) => !item.hidden && !item.classList.contains('drawer-scrim'));
    }

    function openDrawer(name, trigger) {
        const drawer = document.querySelector(`[data-drawer="${name}"]`);
        if (!drawer) return;
        syncDrawerViewport();
        lastTrigger = trigger || document.activeElement;
        drawer.hidden = false;
        body.classList.add('drawer-open');
        const targets = focusables(drawer);
        if (targets.length) window.setTimeout(() => targets[0].focus(), 40);
    }

    function closeDrawer(drawer) {
        if (!drawer) return;
        drawer.hidden = true;
        if (!document.querySelector('.drawer:not([hidden])')) body.classList.remove('drawer-open');
        if (lastTrigger && typeof lastTrigger.focus === 'function') lastTrigger.focus();
    }

    function setupDrawers() {
        document.querySelectorAll('[data-open-drawer]').forEach((button) => {
            button.addEventListener('click', () => openDrawer(button.dataset.openDrawer, button));
        });
        document.querySelectorAll('[data-close-drawer]').forEach((button) => {
            button.addEventListener('click', () => closeDrawer(button.closest('.drawer')));
        });
        document.querySelectorAll('.drawer').forEach((drawer) => {
            drawer.addEventListener('focusin', (event) => {
                if (!event.target.matches('input, select, textarea')) return;
                window.requestAnimationFrame(() => event.target.scrollIntoView({ block: 'nearest' }));
            });
            drawer.addEventListener('keydown', (event) => {
                if (event.key !== 'Tab') return;
                const targets = focusables(drawer);
                if (!targets.length) return;
                const first = targets[0];
                const last = targets[targets.length - 1];
                if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
            });
        });
    }

    function setupMenus() {
        document.querySelectorAll('[data-toggle-menu]').forEach((button) => {
            button.addEventListener('click', (event) => {
                event.stopPropagation();
                const panel = document.getElementById(button.dataset.toggleMenu);
                if (!panel) return;
                const next = panel.hidden;
                document.querySelectorAll('[data-menu-panel]').forEach((item) => { if (item !== panel) item.hidden = true; });
                panel.hidden = !next;
                button.setAttribute('aria-expanded', String(next));
            });
        });
        document.addEventListener('click', (event) => {
            if (event.target.closest('[data-menu-panel]')) return;
            document.querySelectorAll('[data-menu-panel]').forEach((panel) => { panel.hidden = true; });
        });
        document.querySelectorAll('.life-menu').forEach((menu) => {
            document.addEventListener('click', (event) => { if (!menu.contains(event.target)) menu.removeAttribute('open'); });
        });
    }

    function setupTabs() {
        document.querySelectorAll('[data-tabs]').forEach((root) => {
            root.querySelectorAll('[data-tab-target]').forEach((button) => {
                button.addEventListener('click', () => {
                    const target = button.dataset.tabTarget;
                    root.querySelectorAll('[data-tab-target]').forEach((item) => item.classList.toggle('active', item === button));
                    root.querySelectorAll('[data-tab-panel]').forEach((panel) => { panel.hidden = panel.dataset.tabPanel !== target; });
                });
            });
        });
    }

    function setupSubmitStates() {
        document.querySelectorAll('form:not(#journal-form)').forEach((form) => {
            if (form.hasAttribute('onsubmit')) return;
            form.addEventListener('submit', () => {
                const button = form.querySelector('button[type="submit"]');
                if (!button || button.disabled) return;
                button.disabled = true;
                button.dataset.originalText = button.textContent;
                button.textContent = '正在收好…';
            });
        });
    }

    function setupReveal() {
        const items = document.querySelectorAll('[data-reveal]');
        body.classList.add('reveal-ready');
        if (!items.length || !('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            items.forEach((item) => item.classList.add('revealed'));
            return;
        }
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) { entry.target.classList.add('revealed'); observer.unobserve(entry.target); }
            });
        }, { threshold: 0.08, rootMargin: '0px 0px -24px' });
        items.forEach((item) => observer.observe(item));
    }

    function addDynamicRow(containerId, nameField, quantityField) {
        const container = document.getElementById(containerId);
        if (!container) return;
        const row = document.createElement('div');
        row.className = 'dynamic-row';
        row.innerHTML = `<input type="text" name="${nameField}" placeholder="名称" aria-label="名称"><input type="text" name="${quantityField}" placeholder="用量" aria-label="用量"><button class="icon-button" type="button" aria-label="移除这一项"><i data-lucide="minus"></i></button>`;
        row.querySelector('button').addEventListener('click', () => row.remove());
        container.appendChild(row);
        icons();
        row.querySelector('input').focus();
    }
    window.addIngredient = () => addDynamicRow('ingredients-container', 'ingredient_name[]', 'ingredient_qty[]');
    window.addSeasoning = () => addDynamicRow('seasonings-container', 'seasoning_name[]', 'seasoning_qty[]');
    window.removeItem = (button) => button.closest('.dynamic-row')?.remove();

    const journal = { modal: null, form: null, content: null, date: null, status: null, currentDate: null, pendingDraft: null, previousFocus: null };
    function draftKey(date) { return `couple-journal-draft:${userId}:${date}`; }
    function readDraft(date) { try { return JSON.parse(localStorage.getItem(draftKey(date)) || 'null'); } catch (_) { return null; } }
    function writeDraft() {
        if (!journal.currentDate || !journal.content) return;
        const value = journal.content.value;
        const previous = readDraft(journal.currentDate) || {};
        localStorage.setItem(draftKey(journal.currentDate), JSON.stringify({ content: value, updated_at: Date.now(), request_id: previous.request_id || null }));
        journal.status.textContent = '草稿已留在本机';
        document.getElementById('journal-char-count').textContent = `${value.length} 字`;
    }
    function setJournalMode(editing) {
        document.getElementById('journal-view').hidden = editing;
        document.getElementById('journal-edit').hidden = !editing;
        if (editing) window.setTimeout(() => journal.content.focus(), 60);
    }
    function closeJournal() {
        if (!journal.modal) return;
        if (!document.getElementById('journal-edit').hidden) writeDraft();
        journal.modal.hidden = true;
        body.classList.remove('drawer-open');
        journal.previousFocus?.focus();
    }
    function openJournal(element) {
        if (!journal.modal) return;
        const data = element.dataset;
        journal.previousFocus = document.activeElement;
        journal.currentDate = data.date;
        journal.date.value = data.date;
        journal.content.value = data.meContent || '';
        document.getElementById('modal-title').textContent = data.date;
        const hasMe = data.me === 'true';
        const hasPartner = data.partner === 'true';
        const viewMe = document.getElementById('view-me');
        const viewPartner = document.getElementById('view-partner');
        viewMe.hidden = !hasMe;
        viewPartner.hidden = !hasPartner;
        document.getElementById('view-me-content').textContent = data.meContent || '';
        document.getElementById('view-partner-content').textContent = data.partnerContent || '';
        document.getElementById('edit-my-entry-btn').querySelector('span').textContent = hasMe ? '续写我的日记' : '写我的日记';
        const draft = readDraft(data.date);
        journal.pendingDraft = draft && draft.content !== journal.content.value ? draft : null;
        document.getElementById('draft-recovery').hidden = !journal.pendingDraft;
        journal.status.textContent = journal.pendingDraft ? '发现一份未保存的草稿' : '还没有改动';
        document.getElementById('journal-char-count').textContent = `${journal.content.value.length} 字`;
        setJournalMode(!hasMe && !hasPartner);
        journal.modal.hidden = false;
        body.classList.add('drawer-open');
        const targets = focusables(journal.modal);
        if (targets.length) window.setTimeout(() => targets[0].focus(), 40);
    }
    window.openModal = openJournal;
    async function saveJournal(event) {
        event.preventDefault();
        const content = journal.content.value.trim();
        if (!content) { journal.status.textContent = '先留下一点文字吧'; journal.content.focus(); return; }
        const button = journal.form.querySelector('button[type="submit"]');
        const buttonText = button.querySelector('span');
        button.disabled = true;
        buttonText.textContent = '正在收进日记…';
        journal.status.textContent = '正在保存';
        const draft = readDraft(journal.currentDate) || {};
        const requestId = draft.request_id || (window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
        localStorage.setItem(draftKey(journal.currentDate), JSON.stringify({ content, updated_at: Date.now(), request_id: requestId }));
        try {
            const response = await fetch(body.dataset.journalUrl, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRFToken': csrfToken }, body: JSON.stringify({ date: journal.currentDate, content, request_id: requestId }) });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || result.status !== 'success') throw new Error(result.message || `HTTP ${response.status}`);
            localStorage.removeItem(draftKey(journal.currentDate));
            journal.status.textContent = '已经收进日记';
            showToast('日记已经好好收下');
            window.setTimeout(() => window.location.reload(), 350);
        } catch (error) {
            console.error('journal save failed', error);
            journal.status.textContent = '暂时没能同步，草稿还在本机';
            showToast('网络不太稳定，文字没有丢失');
        } finally {
            button.disabled = false;
            buttonText.textContent = '收进日记';
        }
    }
    function setupJournal() {
        journal.modal = document.getElementById('journalModal');
        journal.form = document.getElementById('journal-form');
        if (!journal.modal || !journal.form) return;
        journal.content = document.getElementById('journal-content');
        journal.date = document.getElementById('journal-date');
        journal.status = document.getElementById('journal-save-status');
        journal.form.addEventListener('submit', saveJournal);
        journal.content.addEventListener('input', writeDraft);
        document.getElementById('edit-my-entry-btn').addEventListener('click', () => setJournalMode(true));
        document.querySelectorAll('[data-close-journal]').forEach((button) => button.addEventListener('click', closeJournal));
        document.querySelector('[data-restore-draft]').addEventListener('click', () => { if (journal.pendingDraft) journal.content.value = journal.pendingDraft.content; document.getElementById('draft-recovery').hidden = true; writeDraft(); journal.content.focus(); });
        document.querySelector('[data-discard-draft]').addEventListener('click', () => { localStorage.removeItem(draftKey(journal.currentDate)); journal.pendingDraft = null; document.getElementById('draft-recovery').hidden = true; journal.status.textContent = '已忽略本地草稿'; });
        window.addEventListener('pagehide', () => { if (!document.getElementById('journal-edit').hidden) writeDraft(); });
    }

    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        const openDrawerElement = document.querySelector('.drawer:not([hidden])');
        if (openDrawerElement?.id === 'journalModal') closeJournal();
        else if (openDrawerElement) closeDrawer(openDrawerElement);
    });

    document.addEventListener('DOMContentLoaded', () => {
        syncDrawerViewport();
        window.addEventListener('resize', syncDrawerViewport);
        window.visualViewport?.addEventListener('resize', syncDrawerViewport);
        window.visualViewport?.addEventListener('scroll', syncDrawerViewport);
        addCsrfToForms();
        setupDrawers();
        setupMenus();
        setupTabs();
        setupSubmitStates();
        setupJournal();
        setupReveal();
        icons();
        if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(console.error);
    });
})();
