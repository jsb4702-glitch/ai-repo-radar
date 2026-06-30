// AI Repo Radar — 클라이언트 렌더 + KO/EN i18n + 필터/검색/정렬 + 상세 시트 + 피드백.

const WEB3FORMS_KEY = '80d86c46-c769-4d58-ac9d-e046af5c2925'; // web3forms (공개 키 — 발송 전용, 읽기 불가)

const I18N = {
  ko: {
    tagline: '매일 뜨는 AI 오픈소스를 카테고리로 분류하고 <b>실전투입 점수</b>로 거른다.',
    search: '검색 — 이름 · 설명 · 태그',
    sortLabel: '정렬',
    minScore: '최소점수',
    sort: { prod_score: '실전점수순', star_velocity: '🚀 급상승순(일평균⭐)', stars: '스타순', created_at: '🆕 신규순', last_push: '최근 업데이트순' },
    meta: (n, c) => `총 ${n}개 repo · 카테고리 ${c}종`,
    trendAll: '📡 지금 AI 오픈소스는 어디로?',
    trendCat: (c) => `📡 ${c} — 어디로 가고 있나`,
    trendCount: (n) => `${n}개`,
    capNote: (cap, tot) => `상위 ${cap}개 표시 · 전체 ${tot}개 — 검색·카테고리·정렬로 좁혀봐`,
    empty: '조건에 맞는 repo가 없다 🤷',
    footer: '데이터: GitHub Search API · 점수는 유지보수·라이선스·인기·문서 휴리스틱 합산',
    updated: (s) => `갱신 ${s}`,
    sheet: { category: '카테고리', language: '언어', license: '라이선스', stars: '스타', velocity: '일평균 ⭐', issues: '열린 이슈', created: '생성', push: '최근 푸시', reasons: '실전점수 근거', topics: '토픽', github: 'GitHub에서 열기 ↗', home: '홈페이지 ↗' },
    none: '(설명 없음)',
    toggle: 'EN',
    kofi: 'Ko-fi 후원', kakao: '카카오페이 후원',
    fb: { open: '피드백', title: '피드백 보내기', sub: '버그·제안·추가했으면 하는 repo, 편하게 남겨줘.', placeholder: '내용을 적어줘…', contact: '회신받을 이메일·연락처 (선택)', send: '보내기', sending: '보내는 중…', ok: '✅ 보냈다. 고마워!', err: '❌ 전송 실패 — 잠시 후 다시', empty: '내용을 입력해줘', noKey: '아직 준비 중 (설정 필요)' },
  },
  en: {
    tagline: 'Daily-trending AI open source, sorted by category and filtered by a <b>production-readiness score</b>.',
    search: 'Search — name · description · tag',
    sortLabel: 'Sort',
    minScore: 'Min score',
    sort: { prod_score: 'Production score', star_velocity: '🚀 Fastest rising (⭐/day)', stars: 'Stars', created_at: '🆕 Newest', last_push: 'Recently updated' },
    meta: (n, c) => `${n} repos · ${c} categories`,
    trendAll: '📡 Where is AI open source heading?',
    trendCat: (c) => `📡 ${c} — where it's heading`,
    trendCount: (n) => `${n} repos`,
    capNote: (cap, tot) => `Showing top ${cap} of ${tot} — narrow with search · category · sort`,
    empty: 'No repos match 🤷',
    footer: 'Data: GitHub Search API · score = maintenance + license + popularity + docs heuristic',
    updated: (s) => `Updated ${s}`,
    sheet: { category: 'Category', language: 'Language', license: 'License', stars: 'Stars', velocity: '⭐/day', issues: 'Open issues', created: 'Created', push: 'Last push', reasons: 'Score basis', topics: 'Topics', github: 'Open on GitHub ↗', home: 'Homepage ↗' },
    none: '(no description)',
    toggle: '한국어',
    kofi: 'Support (Ko-fi)', kakao: 'Donate (KakaoPay)',
    fb: { open: 'Feedback', title: 'Send feedback', sub: 'Bugs, suggestions, repos to add — anything.', placeholder: 'Your message…', contact: 'Your email/contact (optional)', send: 'Send', sending: 'Sending…', ok: '✅ Sent. Thanks!', err: '❌ Failed — try again', empty: 'Please enter a message', noKey: 'Not set up yet' },
  },
};

// prod_reasons(한국어 데이터) → 표시 언어 변환
function reasonText(r) {
  if (state.lang === 'ko') return r;
  const map = {
    '최근 30일 내 활발': 'Active in last 30 days',
    '최근 90일 내 활동': 'Active in last 90 days',
    '1년 내 활동': 'Active within a year',
    '1년+ 방치': 'Inactive 1y+',
    '라이선스 불명확': 'License unclear',
    '설명 있음': 'Has description',
    'topics 태깅됨': 'Topics tagged',
    'archived (보관됨)': 'archived',
  };
  if (map[r]) return map[r];
  if (r.startsWith('라이선스 ')) return 'License ' + r.slice(5);
  return r; // "stars N" 등은 그대로
}

const state = {
  repos: [], byName: new Map(), trends: null,
  category: 'All', query: '', sort: 'prod_score', minScore: 0,
  generatedAt: null, lang: 'ko',
};
const el = (id) => document.getElementById(id);
const T = () => I18N[state.lang];

function detectLang() {
  const saved = localStorage.getItem('arr_lang');
  if (saved === 'ko' || saved === 'en') return saved;
  return (navigator.language || '').toLowerCase().startsWith('ko') ? 'ko' : 'en';
}

function initTheme() {
  const saved = localStorage.getItem('arr_theme');
  const theme = (saved === 'light' || saved === 'dark')
    ? saved
    : (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  setTheme(theme, false);
}
function setTheme(theme, persist = true) {
  document.documentElement.dataset.theme = theme;
  if (persist) localStorage.setItem('arr_theme', theme);
  const btn = el('theme-toggle');
  if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
}

async function load() {
  initTheme();
  state.lang = detectLang();
  try {
    const res = await fetch('./data/repos.json', { cache: 'no-store' });
    const data = await res.json();
    state.repos = data.repos || [];
    state.repos.forEach((r) => state.byName.set(r.name, r));
    state.generatedAt = data.generated_at;
    try {
      const tr = await fetch('./data/trends.json', { cache: 'no-store' });
      if (tr.ok) state.trends = await tr.json();
    } catch (_) {}
    applyI18n();
    buildTabs();
    renderTrend();
    render(true);
    openFromHash();
  } catch (e) {
    el('meta').textContent = '데이터 로드 실패 — data/repos.json';
    console.error(e);
  }
}

function applyI18n() {
  const t = T();
  document.documentElement.lang = state.lang;
  el('tagline').innerHTML = t.tagline;
  el('search').placeholder = t.search;
  el('sort-label').textContent = t.sortLabel;
  el('minscore-label').textContent = t.minScore;
  el('lang-toggle').textContent = t.toggle;
  el('empty').textContent = t.empty;
  el('kofi-label').textContent = t.kofi;
  el('kakao-label').textContent = t.kakao;
  el('fb-open-label').textContent = t.fb.open;
  el('fb-title').textContent = t.fb.title;
  el('fb-sub').textContent = t.fb.sub;
  el('fb-msg').placeholder = t.fb.placeholder;
  el('fb-contact').placeholder = t.fb.contact;
  el('fb-send').textContent = t.fb.send;
  el('meta').textContent = t.meta(state.repos.length, countCategories().length);
  el('footer-data').innerHTML = `${t.footer} · <span id="genat"></span>`;
  if (state.generatedAt) el('genat').textContent = t.updated(new Date(state.generatedAt).toLocaleString(state.lang === 'ko' ? 'ko-KR' : 'en-US'));
  // 정렬 옵션 텍스트
  [...el('sort').options].forEach((o) => { o.textContent = t.sort[o.value] || o.value; });
}

function countCategories() {
  const m = {};
  state.repos.forEach((r) => (m[r.category] = (m[r.category] || 0) + 1));
  return Object.entries(m).sort((a, b) => b[1] - a[1]);
}

function buildTabs() {
  const tabs = [['All', state.repos.length], ...countCategories()];
  el('tabs').innerHTML = tabs
    .map(([c, n]) => `<span class="tab ${c === state.category ? 'active' : ''}" data-cat="${c}">${c}<span class="n">${n}</span></span>`)
    .join('');
  el('tabs').querySelectorAll('.tab').forEach((t) =>
    t.addEventListener('click', () => { state.category = t.dataset.cat; buildTabs(); renderTrend(); render(true); }));
}

const scoreClass = (s) => (s >= 70 ? 'good' : s >= 40 ? 'mid' : 'bad');

function summaryOf(r) {
  return state.lang === 'ko'
    ? (r.summary_ko || r.description || T().none)
    : (r.description || r.summary_ko || T().none);
}

function filtered() {
  const q = state.query.trim().toLowerCase();
  let list = state.repos.filter((r) => {
    if (state.category !== 'All' && r.category !== state.category) return false;
    if (r.prod_score < state.minScore) return false;
    if (q) {
      const hay = `${r.name} ${r.description || ''} ${r.summary_ko || ''} ${(r.topics || []).join(' ')}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const key = state.sort;
  list.sort((a, b) =>
    key === 'last_push' ? (b.last_push || '').localeCompare(a.last_push || '')
    : key === 'created_at' ? (b.created_at || '').localeCompare(a.created_at || '')
    : (b[key] || 0) - (a[key] || 0));
  return list;
}

function card(r, i, animate) {
  const sc = scoreClass(r.prod_score);
  const reasons = (r.prod_reasons || []).slice(0, 3).map(reasonText).join(' · ');
  const flags = (r.star_velocity >= 100 ? `<span class="flag" title="${fmt(r.star_velocity)}⭐/day">🚀</span>` : '') + (r.is_new ? `<span class="flag">🆕</span>` : '');
  const delay = animate ? Math.min(i, 12) * 28 : 0;
  return `
    <article class="${animate ? 'card enter' : 'card'}" ${animate ? `style="animation-delay:${delay}ms"` : ''} data-name="${escapeAttr(r.name)}">
      <div class="card-top">
        <div class="card-name">${flags}${escapeHtml(r.name)}</div>
        <div class="score ${sc}" title="${escapeAttr(reasons)}">${r.prod_score}</div>
      </div>
      <div class="card-desc">${escapeHtml(summaryOf(r))}</div>
      <div class="badges">
        <span class="badge cat">${r.category}</span>
        ${r.language ? `<span class="badge">${escapeHtml(r.language)}</span>` : ''}
        ${r.license ? `<span class="badge">${escapeHtml(r.license)}</span>` : ''}
      </div>
      <div class="reasons">${escapeHtml(reasons)}</div>
      <div class="card-foot"><span>★ ${fmt(r.stars)}</span><span>${r.last_push || '?'}</span><span>${state.lang === 'ko' ? '이슈' : 'issues'} ${fmt(r.open_issues)}</span></div>
    </article>`;
}

const RENDER_CAP = 120;
function render(animate) {
  const list = filtered();
  el('grid').innerHTML = list.slice(0, RENDER_CAP).map((r, i) => card(r, i, animate)).join('');
  el('empty').hidden = list.length > 0;
  const note = el('cap-note');
  if (list.length > RENDER_CAP) { note.hidden = false; note.textContent = T().capNote(RENDER_CAP, list.length); }
  else note.hidden = true;
}

function renderTrend() {
  const box = el('trend');
  if (!state.trends || state.query.trim()) { box.hidden = true; return; } // 검색 중엔 숨김
  const t = T();
  let summary, count, eyebrow, keywords = [];
  if (state.category === 'All') {
    summary = state.lang === 'ko' ? state.trends.overall : (state.trends.overall_en || state.trends.overall);
    count = state.repos.length; eyebrow = t.trendAll; keywords = state.trends.trending_topics || [];
  } else {
    const c = (state.trends.categories || {})[state.category];
    if (!c) { box.hidden = true; return; }
    summary = state.lang === 'ko' ? c.summary : (c.summary_en || c.summary);
    count = c.count; keywords = c.keywords || []; eyebrow = t.trendCat(state.category);
  }
  if (!summary) { box.hidden = true; return; }
  el('trend-eyebrow').textContent = eyebrow;
  el('trend-count').textContent = t.trendCount(count);
  el('trend-summary').textContent = summary;
  el('trend-keywords').innerHTML = keywords.map((k) => `<span class="kw">${escapeHtml(k)}</span>`).join('');
  box.hidden = false;
}

function openSheet(name) {
  const r = state.byName.get(name); if (!r) return;
  const t = T(), sc = scoreClass(r.prod_score);
  const topics = (r.topics || []).map((x) => `<span class="chip">${escapeHtml(x)}</span>`).join('');
  const reasons = (r.prod_reasons || []).map((x) => `<li>${escapeHtml(reasonText(x))}</li>`).join('');
  const home = r.homepage ? `<a class="btn btn-2" href="${escapeAttr(r.homepage)}" target="_blank" rel="noopener">${t.sheet.home}</a>` : '';
  const ko = state.lang === 'ko' ? (r.summary_ko || r.description) : (r.description || r.summary_ko);
  const second = state.lang === 'ko' ? (r.summary_ko && r.description ? r.description : '') : '';
  el('sheet-body').innerHTML = `
    <div class="sheet-head"><h2><a href="${escapeAttr(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.name)}</a></h2><div class="score ${sc} big">${r.prod_score}</div></div>
    <p class="sheet-desc">${escapeHtml(ko || t.none)}</p>
    ${second ? `<p class="sheet-en">${escapeHtml(second)}</p>` : ''}
    <div class="sheet-actions"><a class="btn btn-1" href="${escapeAttr(r.url)}" target="_blank" rel="noopener">${t.sheet.github}</a>${home}</div>
    <div class="sheet-stats">
      <div><span>${t.sheet.category}</span><b>${r.category}</b></div>
      <div><span>${t.sheet.language}</span><b>${escapeHtml(r.language || '—')}</b></div>
      <div><span>${t.sheet.license}</span><b>${escapeHtml(r.license || '—')}</b></div>
      <div><span>${t.sheet.stars}</span><b>${fmt(r.stars)}</b></div>
      <div><span>${t.sheet.velocity}</span><b>${fmt(r.star_velocity || 0)}${r.star_velocity >= 100 ? ' 🚀' : ''}</b></div>
      <div><span>${t.sheet.issues}</span><b>${fmt(r.open_issues)}</b></div>
      <div><span>${t.sheet.created}</span><b>${r.created_at || '—'}</b></div>
      <div><span>${t.sheet.push}</span><b>${r.last_push || '—'}</b></div>
    </div>
    <div class="sheet-section"><h3>${t.sheet.reasons}</h3><ul class="reason-list">${reasons || '<li>—</li>'}</ul></div>
    ${topics ? `<div class="sheet-section"><h3>${t.sheet.topics}</h3><div class="chips">${topics}</div></div>` : ''}`;
  const s = el('sheet'); s.hidden = false;
  requestAnimationFrame(() => s.classList.add('open'));
  document.body.style.overflow = 'hidden';
  if (location.hash !== '#repo=' + name) history.replaceState(null, '', '#repo=' + name);
}
function closeSheet() {
  const s = el('sheet'); s.classList.remove('open'); document.body.style.overflow = '';
  setTimeout(() => (s.hidden = true), 220);
  if (location.hash.startsWith('#repo=')) history.replaceState(null, '', location.pathname);
}
function openFromHash() {
  const m = decodeURIComponent(location.hash).match(/^#repo=(.+)$/);
  if (m && state.byName.has(m[1])) {
    openSheet(m[1]);
    const s = el('sheet'); s.style.transition = 'none'; s.classList.add('open');
    s.querySelector('.sheet-card').style.transition = 'none'; s.querySelector('.sheet-backdrop').style.transition = 'none';
    requestAnimationFrame(() => { s.style.transition = ''; s.querySelector('.sheet-card').style.transition = ''; s.querySelector('.sheet-backdrop').style.transition = ''; });
  }
}

// ---- 피드백 모달 ----
function openFb() {
  const f = el('fb'); f.hidden = false;
  requestAnimationFrame(() => f.classList.add('open'));
  document.body.style.overflow = 'hidden';
  el('fb-status').textContent = '';
  setTimeout(() => el('fb-msg').focus(), 50);
}
function closeFb() {
  const f = el('fb'); f.classList.remove('open');
  document.body.style.overflow = '';
  setTimeout(() => (f.hidden = true), 220);
}
async function sendFeedback() {
  const t = T(), msg = el('fb-msg').value.trim();
  const status = el('fb-status');
  if (!msg) { status.textContent = t.fb.empty; return; }
  if (!WEB3FORMS_KEY || WEB3FORMS_KEY === 'WEB3FORMS_KEY') { status.textContent = t.fb.noKey; return; }
  if (el('fb-bot').checked) return; // honeypot
  status.textContent = t.fb.sending;
  el('fb-send').disabled = true;
  try {
    const res = await fetch('https://api.web3forms.com/submit', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        access_key: WEB3FORMS_KEY,
        subject: 'AI Repo Radar 피드백',
        from_name: 'AI Repo Radar',
        message: msg,
        contact: el('fb-contact').value.trim() || '(미기재)',
        lang: state.lang,
      }),
    });
    const j = await res.json();
    if (j.success) {
      status.textContent = t.fb.ok;
      el('fb-msg').value = ''; el('fb-contact').value = '';
      setTimeout(closeFb, 1400);
    } else status.textContent = t.fb.err;
  } catch (e) { status.textContent = t.fb.err; }
  el('fb-send').disabled = false;
}

function fmt(n) { return n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k' : String(n ?? 0); }
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const escapeAttr = escapeHtml;

function setLang(lang) {
  state.lang = lang; localStorage.setItem('arr_lang', lang);
  applyI18n(); buildTabs(); renderTrend(); render(false);
}

let searchTimer;
el('search').addEventListener('input', (e) => { state.query = e.target.value; clearTimeout(searchTimer); searchTimer = setTimeout(() => { renderTrend(); render(false); }, 120); });
el('sort').addEventListener('change', (e) => { state.sort = e.target.value; render(true); });
el('minScore').addEventListener('input', (e) => { state.minScore = +e.target.value; el('minOut').textContent = e.target.value; render(false); });
el('grid').addEventListener('click', (e) => { const c = e.target.closest('.card'); if (c) openSheet(c.dataset.name); });
el('sheet').addEventListener('click', (e) => { if (e.target.dataset.close !== undefined) closeSheet(); });
el('lang-toggle').addEventListener('click', () => setLang(state.lang === 'ko' ? 'en' : 'ko'));
el('theme-toggle').addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
el('fb-open').addEventListener('click', openFb);
el('fb-send').addEventListener('click', sendFeedback);
el('fb').addEventListener('click', (e) => { if (e.target.dataset.fbclose !== undefined) closeFb(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeSheet(); closeFb(); } });

load();
