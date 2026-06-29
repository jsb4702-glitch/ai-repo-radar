// AI Repo Radar — 클라이언트 렌더. repos.json 먹고 필터/검색/정렬 + 상세 시트.
const state = {
  repos: [],
  byName: new Map(),
  trends: null,
  category: "All",
  query: "",
  sort: "prod_score",
  minScore: 0,
  generatedAt: null,
};

const el = (id) => document.getElementById(id);

async function load() {
  try {
    const res = await fetch("./data/repos.json", { cache: "no-store" });
    const data = await res.json();
    state.repos = data.repos || [];
    state.repos.forEach((r) => state.byName.set(r.name, r));
    state.generatedAt = data.generated_at;
    el("meta").textContent = `총 ${state.repos.length}개 repo · 카테고리 ${countCategories().length}종`;
    el("genat").textContent = state.generatedAt
      ? `갱신 ${new Date(state.generatedAt).toLocaleString("ko-KR")}` : "";
    try {
      const tr = await fetch("./data/trends.json", { cache: "no-store" });
      if (tr.ok) state.trends = await tr.json();
    } catch (_) { /* 트렌드 없으면 배너 생략 */ }
    buildTabs();
    renderTrend();
    render(true);
    openFromHash(); // 딥링크 #repo=owner/name 자동오픈
  } catch (e) {
    el("meta").textContent = "데이터 로드 실패 — data/repos.json 확인";
    console.error(e);
  }
}

function renderTrend() {
  const box = el("trend");
  if (!state.trends) { box.hidden = true; return; }
  let summary, count, eyebrow, keywords = [];
  if (state.category === "All") {
    summary = state.trends.overall;
    count = state.repos.length;
    eyebrow = "📡 지금 AI 오픈소스는 어디로?";
    keywords = state.trends.trending_topics || [];
  } else {
    const t = (state.trends.categories || {})[state.category];
    if (!t || !t.summary) { box.hidden = true; return; }
    summary = t.summary;
    count = t.count;
    keywords = t.keywords || [];
    eyebrow = `📡 ${state.category} — 어디로 가고 있나`;
  }
  if (!summary) { box.hidden = true; return; }
  el("trend-eyebrow").textContent = eyebrow;
  el("trend-count").textContent = `${count}개`;
  el("trend-summary").textContent = summary;
  el("trend-keywords").innerHTML = keywords
    .map((k) => `<span class="kw">${escapeHtml(k)}</span>`).join("");
  box.hidden = false;
}

function countCategories() {
  const m = {};
  state.repos.forEach((r) => (m[r.category] = (m[r.category] || 0) + 1));
  return Object.entries(m).sort((a, b) => b[1] - a[1]);
}

function buildTabs() {
  const cats = countCategories();
  const tabs = [["All", state.repos.length], ...cats];
  el("tabs").innerHTML = tabs
    .map(([c, n]) => `<span class="tab ${c === state.category ? "active" : ""}" data-cat="${c}">${c}<span class="n">${n}</span></span>`)
    .join("");
  el("tabs").querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => {
      state.category = t.dataset.cat;
      buildTabs();
      renderTrend();
      render(true);
    })
  );
}

const scoreClass = (s) => (s >= 70 ? "good" : s >= 40 ? "mid" : "bad");

function filtered() {
  const q = state.query.trim().toLowerCase();
  let list = state.repos.filter((r) => {
    if (state.category !== "All" && r.category !== state.category) return false;
    if (r.prod_score < state.minScore) return false;
    if (q) {
      const hay = `${r.name} ${r.description || ""} ${(r.topics || []).join(" ")}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const key = state.sort;
  list.sort((a, b) =>
    key === "last_push"
      ? (b.last_push || "").localeCompare(a.last_push || "")
      : key === "created_at"
      ? (b.created_at || "").localeCompare(a.created_at || "")
      : (b[key] || 0) - (a[key] || 0)
  );
  return list;
}

function card(r, i, animate) {
  const sc = scoreClass(r.prod_score);
  const reasons = (r.prod_reasons || []).slice(0, 3).join(" · ");
  const summary = r.summary_ko || r.description || "(설명 없음)";
  const delay = animate ? Math.min(i, 12) * 28 : 0;
  const anim = animate ? `style="animation-delay:${delay}ms"` : "";
  const cls = animate ? "card enter" : "card";
  const flags =
    (r.star_velocity >= 100 ? `<span class="flag" title="급상승 — 일평균 ${fmt(r.star_velocity)}⭐/일">🚀</span>` : "") +
    (r.is_new ? `<span class="flag" title="최근 90일 내 생성">🆕</span>` : "");
  return `
    <article class="${cls}" ${anim} data-name="${escapeAttr(r.name)}">
      <div class="card-top">
        <div class="card-name">${flags}${escapeHtml(r.name)}</div>
        <div class="score ${sc}" title="${escapeAttr(reasons)}">${r.prod_score}</div>
      </div>
      <div class="card-desc">${escapeHtml(summary)}</div>
      <div class="badges">
        <span class="badge cat">${r.category}</span>
        ${r.language ? `<span class="badge">${escapeHtml(r.language)}</span>` : ""}
        ${r.license ? `<span class="badge">${escapeHtml(r.license)}</span>` : ""}
      </div>
      <div class="reasons">${escapeHtml(reasons)}</div>
      <div class="card-foot">
        <span>★ ${fmt(r.stars)}</span>
        <span>${r.last_push || "?"}</span>
        <span>이슈 ${fmt(r.open_issues)}</span>
      </div>
    </article>`;
}

const RENDER_CAP = 120; // 한 화면에 그리는 최대 카드 수(성능). 정렬돼 있어 상위부터.

function render(animate) {
  const list = filtered();
  const shown = list.slice(0, RENDER_CAP);
  el("grid").innerHTML = shown.map((r, i) => card(r, i, animate)).join("");
  el("empty").hidden = list.length > 0;
  const note = el("cap-note");
  if (list.length > RENDER_CAP) {
    note.hidden = false;
    note.textContent = `상위 ${RENDER_CAP}개 표시 · 전체 ${list.length}개 — 검색·카테고리·정렬로 좁혀봐`;
  } else {
    note.hidden = true;
  }
}

// ---- 상세 시트 ----
function openSheet(name) {
  const r = state.byName.get(name);
  if (!r) return;
  const sc = scoreClass(r.prod_score);
  const topics = (r.topics || []).map((t) => `<span class="chip">${escapeHtml(t)}</span>`).join("");
  const reasons = (r.prod_reasons || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  const home = r.homepage
    ? `<a class="btn btn-2" href="${escapeAttr(r.homepage)}" target="_blank" rel="noopener">홈페이지 ↗</a>`
    : "";
  el("sheet-body").innerHTML = `
    <div class="sheet-head">
      <h2><a href="${escapeAttr(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.name)}</a></h2>
      <div class="score ${sc} big">${r.prod_score}</div>
    </div>
    <p class="sheet-desc">${escapeHtml(r.summary_ko || r.description || "(설명 없음)")}</p>
    ${r.summary_ko && r.description ? `<p class="sheet-en">${escapeHtml(r.description)}</p>` : ""}
    <div class="sheet-actions">
      <a class="btn btn-1" href="${escapeAttr(r.url)}" target="_blank" rel="noopener">GitHub에서 열기 ↗</a>
      ${home}
    </div>
    <div class="sheet-stats">
      <div><span>카테고리</span><b>${r.category}</b></div>
      <div><span>언어</span><b>${escapeHtml(r.language || "—")}</b></div>
      <div><span>라이선스</span><b>${escapeHtml(r.license || "—")}</b></div>
      <div><span>스타</span><b>${fmt(r.stars)}</b></div>
      <div><span>일평균 ⭐</span><b>${fmt(r.star_velocity || 0)}${r.star_velocity >= 100 ? " 🚀" : ""}</b></div>
      <div><span>열린 이슈</span><b>${fmt(r.open_issues)}</b></div>
      <div><span>생성</span><b>${r.created_at || "—"}</b></div>
      <div><span>최근 푸시</span><b>${r.last_push || "—"}</b></div>
    </div>
    <div class="sheet-section">
      <h3>실전점수 근거</h3>
      <ul class="reason-list">${reasons || "<li>—</li>"}</ul>
    </div>
    ${topics ? `<div class="sheet-section"><h3>토픽</h3><div class="chips">${topics}</div></div>` : ""}`;
  const s = el("sheet");
  s.hidden = false;
  requestAnimationFrame(() => s.classList.add("open"));
  document.body.style.overflow = "hidden";
  if (location.hash !== "#repo=" + name) history.replaceState(null, "", "#repo=" + name);
}

function closeSheet() {
  const s = el("sheet");
  s.classList.remove("open");
  document.body.style.overflow = "";
  setTimeout(() => (s.hidden = true), 220);
  if (location.hash.startsWith("#repo=")) history.replaceState(null, "", location.pathname);
}

function openFromHash() {
  const m = decodeURIComponent(location.hash).match(/^#repo=(.+)$/);
  if (m && state.byName.has(m[1])) {
    openSheet(m[1]);
    // 딥링크 직접 진입은 애니 없이 즉시 표시
    const s = el("sheet");
    s.style.transition = "none";
    s.classList.add("open");
    s.querySelector(".sheet-card").style.transition = "none";
    s.querySelector(".sheet-backdrop").style.transition = "none";
    requestAnimationFrame(() => {
      s.style.transition = "";
      s.querySelector(".sheet-card").style.transition = "";
      s.querySelector(".sheet-backdrop").style.transition = "";
    });
  }
}

// ---- 유틸 ----
function fmt(n) {
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n ?? 0);
}
const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const escapeAttr = escapeHtml;

// ---- 이벤트 ----
let searchTimer;
el("search").addEventListener("input", (e) => {
  state.query = e.target.value;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => render(false), 120); // 검색은 애니 없이(깜빡임 방지)
});
el("sort").addEventListener("change", (e) => { state.sort = e.target.value; render(true); });
el("minScore").addEventListener("input", (e) => {
  state.minScore = +e.target.value;
  el("minOut").textContent = e.target.value;
  render(false);
});
el("grid").addEventListener("click", (e) => {
  const c = e.target.closest(".card");
  if (c) openSheet(c.dataset.name);
});
el("sheet").addEventListener("click", (e) => { if (e.target.dataset.close !== undefined) closeSheet(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSheet(); });

load();
