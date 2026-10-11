(function () {
  'use strict';

  const { check, applyReplacement, stats, resolveOverlaps } = window.GrammarChecker;
  const LT = window.LanguageToolClient;

  const CATEGORIES = ['spelling', 'grammar', 'punctuation', 'style', 'clarity'];
  const WEIGHTS = { spelling: 3, grammar: 3, punctuation: 1.5, style: 1, clarity: 0.5 };
  const STORAGE = { draft: 'grammarhelp:draft', lt: 'grammarhelp:lt', lang: 'grammarhelp:lang' };
  const SAMPLE =
    'welcome to GrammarHelp! i think its a  free alternative to paid writing tools. ' +
    'It catches alot of common mistakes,like spelling errors, a incorrect article, ' +
    'and the the repeated words. You could of written this better then me.\n\n' +
    'In order to get started, just paste your text here. The text is checked by your browser ' +
    'due to the fact that privacy matters.';

  const $ = (id) => document.getElementById(id);
  const input = $('input');
  const backdrop = $('backdrop');
  const issuesEl = $('issues');
  const filtersEl = $('filters');
  const statusEl = $('status');
  const scoreEl = $('score');
  const statsEl = $('stats');
  const ltToggle = $('lt-toggle');
  const ltLanguage = $('lt-language');
  const fixAllBtn = $('fix-all-btn');

  const state = {
    localIssues: [],
    ltIssues: [],
    issues: [],
    ignored: new Set(),
    filter: 'all',
    activeKey: null,
    ltError: null,
    ltPending: false,
    lastText: '',
  };

  // --- storage (best-effort; may be unavailable) -------------------------

  function load(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* ignore */ }
  }

  // --- helpers ------------------------------------------------------------

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // Make whitespace-only suggestions visible: "" -> "remove", " " -> "␣".
  function showText(s) {
    if (s === '') return '<em>remove</em>';
    if (/^\s+$/.test(s)) return '␣'.repeat(s.length);
    return escapeHtml(s).replace(/ /g, '&nbsp;');
  }

  function issueKey(issue, text) {
    return issue.rule + ':' + text.substr(issue.offset, issue.length);
  }

  function issueId(issue) {
    return issue.rule + '@' + issue.offset + ':' + issue.length;
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  // Shift previously-fetched LanguageTool issues to follow an edit so they
  // stay aligned until the next server response. Issues touching the edited
  // region are dropped.
  function rebaseIssues(issues, oldText, newText) {
    if (oldText === newText) return issues;
    let start = 0;
    while (start < oldText.length && start < newText.length && oldText[start] === newText[start]) start++;
    let oldEnd = oldText.length, newEnd = newText.length;
    while (oldEnd > start && newEnd > start && oldText[oldEnd - 1] === newText[newEnd - 1]) { oldEnd--; newEnd--; }
    const delta = newEnd - oldEnd;
    return issues.flatMap((i) => {
      if (i.offset + i.length <= start) return [i];
      if (i.offset >= oldEnd) return [{ ...i, offset: i.offset + delta }];
      return [];
    });
  }

  // --- checking -----------------------------------------------------------

  function runLocal() {
    const text = input.value;
    state.ltIssues = rebaseIssues(state.ltIssues, state.lastText, text);
    state.lastText = text;
    state.localIssues = check(text);
    merge();
  }

  let ltController = null;
  async function runLanguageTool() {
    if (!ltToggle.checked) return;
    const text = input.value;
    if (ltController) ltController.abort();
    ltController = new AbortController();
    state.ltPending = true;
    state.ltError = null;
    renderStatus();
    try {
      const issues = await LT.check(text, { language: ltLanguage.value, signal: ltController.signal });
      // The text may have changed while we waited: align results with the text
      // the local checker last saw (runLocal rebases from there on later edits).
      state.ltIssues = rebaseIssues(issues, text, state.lastText);
      state.ltPending = false;
      merge();
    } catch (err) {
      if (err.name === 'AbortError') return;
      state.ltPending = false;
      state.ltError = err.message || 'Could not reach LanguageTool.';
      renderStatus();
    }
  }

  const runLocalDebounced = debounce(runLocal, 250);
  const runLanguageToolDebounced = debounce(runLanguageTool, 1500);

  function merge() {
    const text = input.value;
    const all = resolveOverlaps(state.localIssues.concat(ltToggle.checked ? state.ltIssues : []));
    state.issues = all.filter((i) => !state.ignored.has(issueKey(i, text)));
    render();
  }

  // --- rendering ----------------------------------------------------------

  function visibleIssues() {
    return state.filter === 'all' ? state.issues : state.issues.filter((i) => i.category === state.filter);
  }

  function render() {
    renderBackdrop();
    renderFilters();
    renderIssues();
    renderStats();
    renderStatus();
  }

  function renderBackdrop() {
    const text = input.value;
    // Long-sentence hints span whole sentences; underlining them would hide
    // other marks, so they only appear in the sidebar.
    const marks = visibleIssues().filter((i) => i.rule !== 'LONG_SENTENCE');
    let html = '';
    let pos = 0;
    for (const issue of marks) {
      if (issue.offset < pos) continue;
      const id = issueId(issue);
      html += escapeHtml(text.slice(pos, issue.offset));
      html += `<mark class="${issue.category}${id === state.activeKey ? ' active' : ''}">` +
        escapeHtml(text.substr(issue.offset, issue.length)) + '</mark>';
      pos = issue.offset + issue.length;
    }
    // A trailing newline in a textarea needs an extra character to take up space.
    html += escapeHtml(text.slice(pos)) + '\n ';
    backdrop.innerHTML = html;
    backdrop.scrollTop = input.scrollTop;
  }

  function renderFilters() {
    const counts = { all: state.issues.length };
    for (const c of CATEGORIES) counts[c] = state.issues.filter((i) => i.category === c).length;
    filtersEl.innerHTML = ['all'].concat(CATEGORIES)
      .filter((c) => c === 'all' || counts[c] > 0 || state.filter === c)
      .map((c) => `<button type="button" role="tab" data-filter="${c}" aria-selected="${state.filter === c}">` +
        (c === 'all' ? '' : `<span class="dot ${c}"></span>`) +
        `${c === 'all' ? 'All' : c[0].toUpperCase() + c.slice(1)} ${counts[c]}</button>`)
      .join('');
  }

  function renderIssues() {
    const text = input.value;
    const list = visibleIssues();
    if (!text.trim()) {
      issuesEl.innerHTML = '<li class="empty">Nothing to check yet.</li>';
    } else if (!list.length) {
      issuesEl.innerHTML = '<li class="empty">✅ No issues found. Nice writing!</li>';
    } else {
      issuesEl.innerHTML = list.map((issue) => {
        const id = issueId(issue);
        const original = text.substr(issue.offset, issue.length);
        const shown = original.length > 60 ? original.slice(0, 57) + '…' : original;
        const fixes = issue.replacements.map((r) =>
          `<button type="button" class="suggestion" data-id="${escapeHtml(id)}" data-value="${escapeHtml(r)}">` +
          `${showText(r)}</button>`).join('');
        return `<li class="issue ${issue.category}${id === state.activeKey ? ' active' : ''}" data-id="${escapeHtml(id)}">` +
          `<div class="issue-head"><span>${issue.category}</span><span>${issue.source || ''}</span></div>` +
          `<div class="issue-msg">${escapeHtml(issue.message)}</div>` +
          `<div class="issue-fix">` +
          (issue.replacements.length ? `<span class="original">${showText(shown)}</span> → ` : '') +
          fixes +
          `<button type="button" class="ignore" data-id="${escapeHtml(id)}">Ignore</button>` +
          `</div></li>`;
      }).join('');
    }
    fixAllBtn.hidden = !list.some((i) => i.replacements.length);
  }

  function renderStats() {
    const s = stats(input.value);
    const mins = s.readingTimeMinutes;
    const reading = mins < 1 ? `${Math.max(1, Math.round(mins * 60))} sec` : `${Math.round(mins)} min`;
    statsEl.innerHTML = [
      `${s.words} words`,
      `${s.characters} characters`,
      `${s.sentences} sentences`,
      s.words ? `${reading} read` : null,
      s.readability != null ? `Readability ${s.readability}/100 (${readabilityLabel(s.readability)})` : null,
    ].filter(Boolean).map((t) => `<span>${t}</span>`).join('');

    if (!s.words) {
      scoreEl.textContent = '–';
      return;
    }
    const penalty = state.issues.reduce((n, i) => n + (WEIGHTS[i.category] || 1), 0);
    const per100 = (penalty / Math.max(s.words, 30)) * 100;
    scoreEl.textContent = Math.max(0, Math.round(100 - per100));
  }

  function readabilityLabel(score) {
    if (score >= 80) return 'very easy';
    if (score >= 60) return 'easy';
    if (score >= 50) return 'fairly hard';
    if (score >= 30) return 'hard';
    return 'very hard';
  }

  function renderStatus() {
    statusEl.classList.toggle('error', !!state.ltError);
    if (state.ltError) {
      statusEl.textContent = state.ltError;
    } else if (!input.value.trim()) {
      statusEl.textContent = 'Start typing to check your writing.';
    } else if (state.ltPending) {
      statusEl.textContent = 'Running deep check…';
    } else {
      const n = state.issues.length;
      statusEl.textContent = n === 0 ? 'Looking good!' : `${n} suggestion${n === 1 ? '' : 's'}`;
    }
  }

  // --- actions ------------------------------------------------------------

  function findIssue(id) {
    return state.issues.find((i) => issueId(i) === id);
  }

  function setText(text, caret) {
    input.value = text;
    if (caret != null) input.setSelectionRange(caret, caret);
    onInput();
  }

  function applyFix(issue, value) {
    const text = applyReplacement(input.value, issue, value);
    state.activeKey = null;
    setText(text, issue.offset + value.length);
    input.focus();
  }

  function fixAll() {
    let text = input.value;
    const fixable = visibleIssues()
      .filter((i) => i.replacements.length)
      .sort((a, b) => b.offset - a.offset);
    for (const issue of fixable) text = applyReplacement(text, issue, issue.replacements[0]);
    setText(text);
  }

  function selectIssue(issue) {
    state.activeKey = issueId(issue);
    input.focus();
    input.setSelectionRange(issue.offset, issue.offset + issue.length);
    render();
    const card = issuesEl.querySelector(`.issue.active`);
    if (card) card.scrollIntoView({ block: 'nearest' });
  }

  function syncActiveFromCaret() {
    const caret = input.selectionStart;
    const hit = visibleIssues().find((i) =>
      i.rule !== 'LONG_SENTENCE' && caret >= i.offset && caret <= i.offset + i.length);
    const key = hit ? issueId(hit) : null;
    if (key !== state.activeKey) {
      state.activeKey = key;
      renderBackdrop();
      renderIssues();
      const card = issuesEl.querySelector('.issue.active');
      if (card) card.scrollIntoView({ block: 'nearest' });
    }
  }

  function onInput() {
    save(STORAGE.draft, input.value);
    runLocalDebounced();
    runLanguageToolDebounced();
  }

  // --- events -------------------------------------------------------------

  input.addEventListener('input', onInput);
  input.addEventListener('scroll', () => { backdrop.scrollTop = input.scrollTop; });
  input.addEventListener('click', syncActiveFromCaret);
  input.addEventListener('keyup', (e) => {
    if (e.key.startsWith('Arrow') || e.key === 'Home' || e.key === 'End') syncActiveFromCaret();
  });
  new ResizeObserver(() => renderBackdrop()).observe(input);

  issuesEl.addEventListener('click', (e) => {
    const target = e.target.closest('button, .issue');
    if (!target) return;
    const issue = findIssue(target.dataset.id);
    if (!issue) return;
    if (target.classList.contains('suggestion')) {
      applyFix(issue, target.dataset.value);
    } else if (target.classList.contains('ignore')) {
      state.ignored.add(issueKey(issue, input.value));
      merge();
    } else {
      selectIssue(issue);
    }
  });

  filtersEl.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-filter]');
    if (!btn) return;
    state.filter = btn.dataset.filter;
    render();
  });

  fixAllBtn.addEventListener('click', fixAll);

  $('copy-btn').addEventListener('click', async () => {
    const btn = $('copy-btn');
    try {
      await navigator.clipboard.writeText(input.value);
      btn.textContent = 'Copied!';
    } catch (e) {
      input.select();
      document.execCommand('copy');
      btn.textContent = 'Copied!';
    }
    setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
  });

  $('clear-btn').addEventListener('click', () => {
    state.ignored.clear();
    setText('');
    input.focus();
  });

  ltToggle.addEventListener('change', () => {
    save(STORAGE.lt, ltToggle.checked ? '1' : '0');
    state.ltError = null;
    if (ltToggle.checked) runLanguageTool();
    merge();
  });

  ltLanguage.addEventListener('change', () => {
    save(STORAGE.lang, ltLanguage.value);
    state.ltIssues = [];
    runLanguageTool();
  });

  // --- init ---------------------------------------------------------------

  ltToggle.checked = load(STORAGE.lt) === '1';
  const lang = load(STORAGE.lang);
  if (lang) ltLanguage.value = lang;
  const draft = load(STORAGE.draft);
  input.value = draft != null ? draft : SAMPLE;
  state.lastText = input.value;
  runLocal();
  runLanguageTool();
})();
