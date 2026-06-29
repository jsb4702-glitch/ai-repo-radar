#!/usr/bin/env python3
"""
Week 1 수집 스크립트 — GitHub Search API로 AI repo를 긁어서
실전투입 점수(prod_score)까지 매겨 public/data/repos.json 으로 저장.

의존성: 파이썬 표준 라이브러리만 (pip 설치 불필요).
실행:  GITHUB_TOKEN=ghp_xxx python3 fetch_repos.py
토큰:  github.com/settings/tokens 에서 read-only PAT 발급 (repo 권한 불필요, public_repo만)

설계 메모:
- 신규/급상승(daily) = pushed 최근 N일 + stars 일정 이상
- 점수화(4번) = prod_score()  ← 투명한 휴리스틱, 화면에 근거 같이 노출 권장
- 한/영 요약 자리(summary_ko/en)는 None으로 비워둠 → 나중에 로컬 LLM이 채움
- Search API 30 req/min 제한 → 호출 사이 SLEEP 으로 보수적 대기
"""

import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from categories import SEED_TOPICS, classify

# ---- 설정 -------------------------------------------------------------
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
RECENT_DAYS = 30          # 최근 N일 안에 push된 repo만 (살아있는 것)
MIN_STARS = 50            # 노이즈 컷
PER_PAGE = 100            # Search 최대
MAX_PAGES = 3            # topic당 최대 페이지 (3 = 최대 300개)
SLEEP_SEC = 2.5           # Search 호출 간 대기 (30/min 안전마진)
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "public", "data", "repos.json")

API = "https://api.github.com/search/repositories"


# ---- HTTP -------------------------------------------------------------
def gh_get(url):
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "ai-github-curation")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        remaining = resp.headers.get("X-RateLimit-Remaining")
        return json.loads(resp.read().decode("utf-8")), remaining


def search_topic(topic, since_iso):
    """한 topic에 대해 최근 push + 별점 필터로 검색, repo dict 리스트 반환."""
    q = f"topic:{topic} pushed:>={since_iso} stars:>={MIN_STARS}"
    results = []
    for page in range(1, MAX_PAGES + 1):
        params = urllib.parse.urlencode({
            "q": q, "sort": "stars", "order": "desc",
            "per_page": PER_PAGE, "page": page,
        })
        url = f"{API}?{params}"
        try:
            data, remaining = gh_get(url)
        except urllib.error.HTTPError as e:
            if e.code == 403:  # rate limit
                print(f"  [403] rate limited on {topic} p{page} — 60s 대기", file=sys.stderr)
                time.sleep(60)
                continue
            print(f"  [HTTP {e.code}] {topic} p{page} skip", file=sys.stderr)
            break
        items = data.get("items", [])
        results.extend(items)
        if len(items) < PER_PAGE:
            break  # 마지막 페이지
        time.sleep(SLEEP_SEC)
    return results


# ---- 실전투입 점수 (4번) ----------------------------------------------
def prod_score(repo):
    """
    0~100. 투명한 휴리스틱 — 화면에 "왜 이 점수인지" 같이 보여주면 신뢰 ↑.
    구성: 유지보수(40) + 라이선스(20) + 인기(25) + 문서/메타(15)
    """
    score = 0
    reasons = []

    # 1) archived = 사실상 죽음 → 즉시 바닥
    if repo.get("archived"):
        return 0, ["archived (보관됨)"]

    # 2) 유지보수 — 마지막 push 최신성 (40점)
    pushed = repo.get("pushed_at")
    if pushed:
        days = (datetime.now(timezone.utc) - _parse(pushed)).days
        if days <= 30:
            score += 40; reasons.append("최근 30일 내 활발")
        elif days <= 90:
            score += 28; reasons.append("최근 90일 내 활동")
        elif days <= 365:
            score += 12; reasons.append("1년 내 활동")
        else:
            reasons.append("1년+ 방치")

    # 3) 라이선스 (20점) — OSI 라이선스 있으면 실전 채택 쉬움
    lic = (repo.get("license") or {}).get("spdx_id")
    if lic and lic not in ("NOASSERTION", None):
        score += 20; reasons.append(f"라이선스 {lic}")
    else:
        reasons.append("라이선스 불명확")

    # 4) 인기 — stars 로그스케일 (25점)
    stars = repo.get("stargazers_count", 0)
    if stars > 0:
        pts = min(25, round(math.log10(stars + 1) / 5 * 25))
        score += pts; reasons.append(f"stars {stars}")

    # 5) 문서/메타 (15점) — description + topics 있으면 관리되는 repo
    if repo.get("description"):
        score += 8; reasons.append("설명 있음")
    if repo.get("topics"):
        score += 7; reasons.append("topics 태깅됨")

    return min(100, score), reasons


def _parse(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


# ---- 메인 -------------------------------------------------------------
def main():
    if not TOKEN:
        print("⚠️  GITHUB_TOKEN 없음 — 미인증은 60req/h라 금방 막힘. "
              "GITHUB_TOKEN=ghp_xxx 로 다시 실행 권장.", file=sys.stderr)

    since = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).date().isoformat()
    print(f"수집 시작: 최근 {RECENT_DAYS}일(push>={since}), stars>={MIN_STARS}, topics={len(SEED_TOPICS)}개")

    seen = {}  # full_name -> record (dedupe)
    for topic in SEED_TOPICS:
        print(f"[topic] {topic} ...", end="", flush=True)
        items = search_topic(topic, since)
        added = 0
        for r in items:
            fn = r.get("full_name")
            if not fn or fn in seen:
                continue
            score, reasons = prod_score(r)
            created = r.get("created_at")
            age_days = max((datetime.now(timezone.utc) - _parse(created)).days, 1) if created else 9999
            seen[fn] = {
                "name": fn,
                "url": r.get("html_url"),
                "homepage": (r.get("homepage") or "").strip() or None,
                "description": r.get("description"),
                "stars": r.get("stargazers_count", 0),
                "language": r.get("language"),
                "topics": r.get("topics", []),
                "license": (r.get("license") or {}).get("spdx_id"),
                "last_push": (r.get("pushed_at") or "")[:10],
                "created_at": (r.get("created_at") or "")[:10],
                "archived": r.get("archived", False),
                "open_issues": r.get("open_issues_count", 0),
                "category": classify(r.get("topics"), r.get("description"), r.get("language")),
                "prod_score": score,
                "prod_reasons": reasons,
                "star_velocity": round(r.get("stargazers_count", 0) / age_days, 1),  # 일평균 ⭐(급상승 프록시)
                "is_new": age_days <= 90,
                "summary_ko": None,   # 나중에 로컬 LLM
                "summary_en": None,   # 나중에 로컬 LLM
            }
            added += 1
        print(f" +{added} (누적 {len(seen)})")
        time.sleep(SLEEP_SEC)

    # ── 기존 요약 보존(merge) ── fetch는 통째 덮어쓰므로, 이미 만든 한글요약을
    # 같은 repo에 그대로 이어붙인다. 새 repo만 summary_ko=None → 다음 summarize가 채움.
    carried = 0
    if os.path.exists(OUT_PATH):
        try:
            old = json.load(open(OUT_PATH, encoding="utf-8"))
            old_sum = {r["name"]: (r.get("summary_ko"), r.get("summary_en"))
                       for r in old.get("repos", [])}
            for fn, rec in seen.items():
                if fn in old_sum and old_sum[fn][0]:
                    rec["summary_ko"], rec["summary_en"] = old_sum[fn]
                    carried += 1
        except Exception as e:
            print(f"  [merge skip] {e}", file=sys.stderr)
    print(f"기존 요약 보존: {carried}개 / 신규 요약대상: {len(seen) - carried}개")

    repos = sorted(seen.values(), key=lambda x: (x["prod_score"], x["stars"]), reverse=True)

    # 카테고리 분포 출력 (검증용)
    dist = {}
    for r in repos:
        dist[r["category"]] = dist.get(r["category"], 0) + 1
    print("\n카테고리 분포:", dict(sorted(dist.items(), key=lambda x: -x[1])))
    print(f"총 {len(repos)}개 / Other(미분류) {dist.get('Other', 0)}개 ← LLM 분류 대상")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(repos),
        "params": {"recent_days": RECENT_DAYS, "min_stars": MIN_STARS},
        "repos": repos,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {os.path.normpath(OUT_PATH)} ({len(repos)}개)")


if __name__ == "__main__":
    main()
