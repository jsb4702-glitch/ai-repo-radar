"""
카테고리별 정적 페이지 프리렌더 — SEO 색인 URL 확장용.

배경: SPA 단일페이지라 구글 색인 URL이 1개뿐(GSC 실측 2026-07-18).
repo 4,589개 데이터가 있는데 검색 진입점이 1개 = 롱테일 유입 0.

출력:
  public/c/<slug>/index.html   카테고리별 정적 페이지 (21개)
  public/sitemap.xml           lastmod 포함 재생성
  public/index.html            카테고리 링크 블록 주입(마커 사이)

각 페이지 고유 콘텐츠 = trends.json의 LLM 생성 카테고리 요약 + 키워드 + repo 목록.
(thin content 회피: 페이지마다 실제 다른 본문이 실린다)

실행: python3 prerender.py   (run_daily.sh [4/5] 단계)
"""
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
BASE = "https://ai-repo-radar-1u7.pages.dev"

# 페이지당 카드 수 상한. 741개 전부 뿌리면 HTML이 비대해지고
# 색인 가치도 늘지 않는다(상위권이 검색의도 대부분을 커버).
CARDS_PER_PAGE = 200

# 한국어 검색어 대응 — title/description에 국문 병기.
# 카테고리 키는 categories.py의 CATEGORIES 순서와 일치해야 한다.
KO_LABEL = {
    "Security": "AI 보안",
    "MCP": "MCP 서버",
    "Browser": "브라우저 자동화",
    "Agent": "AI 에이전트",
    "RAG": "RAG 검색증강",
    "Fine-tuning": "파인튜닝",
    "Multimodal": "멀티모달",
    "Code-AI": "코딩 AI",
    "Robotics": "로보틱스",
    "RL": "강화학습",
    "Vision": "컴퓨터 비전",
    "Audio-Speech": "음성·오디오",
    "NLP": "자연어처리",
    "Eval": "모델 평가",
    "MLOps": "MLOps",
    "Dataset": "데이터셋",
    "Prompt": "프롬프트 엔지니어링",
    "LLM": "LLM",
    "Learning": "학습자료",
    "Framework": "프레임워크",
    "Other": "기타",
}

NAV_START = "<!-- PRERENDER:CATNAV:START -->"
NAV_END = "<!-- PRERENDER:CATNAV:END -->"


def slugify(cat: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", cat.lower()).strip("-")


def css_version() -> str:
    """styles.css 내용 해시 — 캐시 무효화용.
    내용이 바뀔 때만 값이 변한다(날짜 기반이면 매일 무의미하게 캐시가 깨진다)."""
    data = (PUBLIC / "styles.css").read_bytes()
    return hashlib.md5(data).hexdigest()[:8]


def e(s) -> str:
    """HTML 텍스트 이스케이프 (None 안전)."""
    return html.escape(str(s if s is not None else ""), quote=True)


def fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "?"


def score_class(s) -> str:
    """app.js:157 scoreClass와 동일 임계 — 색상 일관성 유지."""
    s = s or 0
    return "good" if s >= 70 else "mid" if s >= 40 else "bad"


def card_html(r: dict) -> str:
    """app.js:184 card()와 같은 클래스 구조 — styles.css 재사용.
    단, 정적 페이지에서는 <article> 대신 <a>로 감싸 GitHub으로 직접 링크한다
    (JS 없이도 동작 + 크롤러가 따라갈 아웃링크 확보)."""
    reasons = " · ".join((r.get("prod_reasons") or [])[:3])
    flags = ""
    if (r.get("star_velocity") or 0) >= 100:
        flags += '<span class="flag">🚀</span>'
    if r.get("is_new"):
        flags += '<span class="flag">🆕</span>'
    badges = f'<span class="badge cat">{e(r.get("category"))}</span>'
    if r.get("language"):
        badges += f'<span class="badge">{e(r["language"])}</span>'
    if r.get("license"):
        badges += f'<span class="badge">{e(r["license"])}</span>'
    return f"""      <a class="card" href="{e(r.get('url'))}" target="_blank" rel="noopener">
        <div class="card-top">
          <div class="card-name">{flags}{e(r.get('name'))}</div>
          <div class="score {score_class(r.get('prod_score'))}">{e(r.get('prod_score'))}</div>
        </div>
        <div class="card-desc">{e(r.get('summary_ko') or r.get('description'))}</div>
        <div class="badges">{badges}</div>
        <div class="reasons">{e(reasons)}</div>
        <div class="card-foot"><span>★ {fmt(r.get('stars'))}</span><span>{e(r.get('last_push') or '?')}</span><span>이슈 {fmt(r.get('open_issues'))}</span></div>
      </a>"""


def cat_nav(cats: list, current: str | None, prefix: str) -> str:
    """전 카테고리 상호링크 — 크롤러 발견 경로 확보(사이트맵만으론 약하다)."""
    out = []
    for c in cats:
        if c == current:
            out.append(f'<span class="tab active">{e(c)}</span>')
        else:
            out.append(f'<a class="tab" href="{prefix}c/{slugify(c)}/">{e(c)}</a>')
    return '<div class="tabs">' + "".join(out) + "</div>"


def build_page(cat: str, repos: list, trend: dict, cats: list, gen_date: str, cssv: str) -> str:
    ko = KO_LABEL.get(cat, cat)
    n = len(repos)
    slug = slugify(cat)
    url = f"{BASE}/c/{slug}/"
    summary = (trend or {}).get("summary") or ""
    keywords = (trend or {}).get("keywords") or []

    title = f"{cat} ({ko}) AI 오픈소스 {fmt(n)}개 — 실전점수 순위 | AI Repo Radar"
    # description은 LLM 요약 앞부분을 쓴다 → 카테고리마다 실제로 다른 문구
    desc_body = summary[:110] if summary else f"{ko} 관련 GitHub 오픈소스를 실전투입 점수로 정렬했다."
    description = f"{cat}({ko}) 분야 GitHub 오픈소스 {fmt(n)}개를 실전투입 점수로 큐레이션. {desc_body}"

    kw_html = "".join(f'<span class="kw">{e(k)}</span>' for k in keywords)
    shown = repos[:CARDS_PER_PAGE]
    more = (
        f'<p class="cap-note">상위 {fmt(len(shown))}개 표시 · 전체 {fmt(n)}개는 '
        f'<a href="../../">메인에서 검색·정렬</a></p>'
        if n > len(shown)
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}" />
  <link rel="canonical" href="{url}" />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="{url}" />
  <meta property="og:title" content="{e(title)}" />
  <meta property="og:description" content="{e(description)}" />
  <meta property="og:image" content="{BASE}/og.png" />
  <meta property="og:site_name" content="AI Repo Radar" />
  <meta property="og:locale" content="ko_KR" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:image" content="{BASE}/og.png" />
  <link rel="stylesheet" href="../../styles.css?v={cssv}" />
</head>
<body>
  <header class="hero">
    <div class="wrap">
      <p class="meta"><a href="../../">AI Repo Radar</a> › {e(cat)}</p>
      <h1>{e(cat)} <span class="accent">{e(ko)}</span></h1>
      <p class="tagline">GitHub {e(cat)} 오픈소스 {fmt(n)}개 — 실전투입 점수 순</p>
      <div class="meta">기준일 {e(gen_date)} · 매일 갱신</div>
    </div>
  </header>

  <main class="wrap">
    <section class="trend">
      <div class="trend-head"><span class="trend-eyebrow">📡 {e(cat)} 지금 흐름</span></div>
      <p class="trend-summary">{e(summary)}</p>
      <div class="trend-keywords">{kw_html}</div>
    </section>

    <div class="grid">
{chr(10).join(card_html(r) for r in shown)}
    </div>
    {more}

    <nav class="catnav">
      <p class="meta">다른 카테고리</p>
      {cat_nav(cats, cat, "../../")}
    </nav>
  </main>

  <footer class="wrap">
    <p><a href="../../">← AI Repo Radar 메인 — 전체 검색·정렬·트렌드</a></p>
  </footer>
  <script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "586d5cd0250c468eb51f71072866e8fc"}}'></script>
</body>
</html>
"""


def build_sitemap(cats: list, lastmod: str) -> str:
    urls = [(BASE + "/", "daily", "1.0")]
    urls += [(f"{BASE}/c/{slugify(c)}/", "daily", "0.8") for c in cats]
    body = "\n".join(
        f"""  <url>
    <loc>{u}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{pri}</priority>
  </url>"""
        for u, freq, pri in urls
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{body}
</urlset>
"""


def inject_nav(cats: list, cssv: str) -> bool:
    """index.html 푸터에 정적 카테고리 링크 주입 + styles.css 캐시버전 갱신.
    app.js는 #tabs / #grid / #footer-data 만 건드리므로 충돌하지 않는다."""
    path = PUBLIC / "index.html"
    orig = path.read_text(encoding="utf-8")
    # 나브가 그대로여도 CSS 버전만 바뀔 수 있다 → 비교는 반드시 원본(orig) 기준
    src = re.sub(
        r'(<link rel="stylesheet" href="\./styles\.css)(\?v=[a-f0-9]+)?(")',
        rf"\1?v={cssv}\3",
        orig,
    )
    block = (
        f'{NAV_START}\n    <nav class="catnav">\n      <p class="meta">카테고리별 보기</p>\n      '
        f"{cat_nav(cats, None, './')}\n    </nav>\n    {NAV_END}"
    )
    if NAV_START in src and NAV_END in src:
        new = re.sub(
            re.escape(NAV_START) + r".*?" + re.escape(NAV_END), block, src, flags=re.S
        )
    else:
        anchor = '<p id="footer-data"></p>'
        if anchor not in src:
            print("  ⚠️ index.html 앵커 미발견 — 나브 주입 생략")
            return False
        new = src.replace(anchor, anchor + "\n    " + block, 1)
    if new == orig:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main() -> None:
    repos_data = json.loads((PUBLIC / "data" / "repos.json").read_text(encoding="utf-8"))
    trends = json.loads((PUBLIC / "data" / "trends.json").read_text(encoding="utf-8"))
    repos = repos_data["repos"]

    gen_at = repos_data.get("generated_at") or datetime.now(timezone.utc).isoformat()
    gen_date = gen_at[:10]

    by_cat: dict[str, list] = {}
    for r in repos:
        by_cat.setdefault(r.get("category") or "Other", []).append(r)

    # 정렬 = 실전점수 → stars. 사이트 기본 정렬(prod_score)과 동일.
    for lst in by_cat.values():
        lst.sort(key=lambda x: (x.get("prod_score") or 0, x.get("stars") or 0), reverse=True)

    # repo 많은 순 = 나브 노출 순서(사이트 탭 순서와 무관하게 중요도 반영)
    cats = sorted(by_cat, key=lambda c: len(by_cat[c]), reverse=True)

    cssv = css_version()

    for cat in cats:
        out = PUBLIC / "c" / slugify(cat) / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            build_page(
                cat, by_cat[cat], (trends.get("categories") or {}).get(cat), cats, gen_date, cssv
            ),
            encoding="utf-8",
        )
        print(f"  /c/{slugify(cat)}/  {len(by_cat[cat]):>4}개  {out.stat().st_size // 1024}KB")

    (PUBLIC / "sitemap.xml").write_text(build_sitemap(cats, gen_date), encoding="utf-8")
    print(f"  sitemap.xml  {len(cats) + 1} URL  lastmod={gen_date}")
    print(f"  styles.css?v={cssv}")
    print(f"  index.html 나브 주입: {'갱신' if inject_nav(cats, cssv) else '변경없음'}")
    print(f"완료: 카테고리 {len(cats)}개 · 색인 URL 1 → {len(cats) + 1}")


if __name__ == "__main__":
    main()
