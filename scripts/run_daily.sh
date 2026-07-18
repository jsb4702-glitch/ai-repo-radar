#!/bin/bash
# AI Repo Radar 일일 자동 갱신 — 로컬 실행(gemma 요약 때문에 CI 불가).
# 흐름: fetch(요약보존 merge) → summarize(신규 repo만) → trends → wrangler 배포 → ntfy 알림
# 토큰: ~/.ai-repo-radar.env 에 GITHUB_TOKEN=ghp_xxx 저장(필수). CLOUDFLARE_API_TOKEN 있으면 무인배포 안정.
# LLM: OpenRouter 31B 강제(자동화와 같은 모델 → 트렌드/요약 경향 일관). 키=~/.config/secrets.env
set -uo pipefail

ROOT="$HOME/ai-github-curation"
SCRIPTS="$ROOT/scripts"
LOG="$ROOT/daily.log"
NTFY_TOPIC="harness-f1f6240ce583"   # 기존 ntfy 토픽 재사용
ENVFILE="$HOME/.ai-repo-radar.env"

exec >>"$LOG" 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 일일 갱신 시작 ====="

# 동시실행 가드 (수동런 vs launchd 07:00 레이스로 repos.json 이중쓰기 방지)
LOCKDIR="$ROOT/.run_daily.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  OLDPID=$(cat "$LOCKDIR/pid" 2>/dev/null)
  if [ -n "$OLDPID" ] && kill -0 "$OLDPID" 2>/dev/null; then
    echo "이미 실행 중(pid=$OLDPID) — 스킵"; exit 0
  fi
  echo "스테일 락 제거(pid=$OLDPID)"; rm -rf "$LOCKDIR"; mkdir "$LOCKDIR" || exit 1
fi
echo $$ > "$LOCKDIR/pid"
trap 'rm -rf "$LOCKDIR"' EXIT

[ -f "$ENVFILE" ] && source "$ENVFILE"
# OpenRouter 31B 강제 + 키 로드(요약·트렌드 모델 일관성)
[ -f "$HOME/.config/secrets.env" ] && source "$HOME/.config/secrets.env"
export LLM_BACKEND=openrouter
export OPENROUTER_MODEL="${OPENROUTER_MODEL:-google/gemma-4-31b-it:free}"
export LLM_FALLBACK_OLLAMA=1   # :free 캡 소진 시 로컬 gemma4 폴백 (llm.py, 로컬 전용)

fail() {  # 실패 = ntfy 알림 + exit 1 (침묵실패 금지)
  echo "ERROR: $1"
  curl -s -d "❌ AI Repo Radar 갱신 실패: $1" -H "Title: AI Repo Radar" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null
  echo "===== $(date '+%H:%M:%S') 실패 종료 ====="
  exit 1
}

[ -n "${GITHUB_TOKEN:-}" ] || fail "GITHUB_TOKEN 없음 ($ENVFILE 확인)"

# 07:00 wake 직후 네트워크 미준비 → 최대 5분 대기 (일주일 연속 fetch 사망 원인)
NET_OK=0
for _ in $(seq 1 30); do
  curl -sf --max-time 5 https://api.github.com/rate_limit -o /dev/null && { NET_OK=1; break; }
  sleep 10
done
[ "$NET_OK" = 1 ] || fail "네트워크 미준비 (api.github.com 5분 무응답)"

# ollama 데몬 보장 (폴백용)
if ! pgrep -x ollama >/dev/null; then
  (ollama serve >/dev/null 2>&1 &)
  sleep 3
fi

cd "$SCRIPTS" || fail "scripts 디렉토리 없음"
echo "[1/5] 수집(요약보존)..."; GITHUB_TOKEN="$GITHUB_TOKEN" python3 fetch_repos.py || fail "fetch_repos.py 실패"
echo "[2/5] 한글요약(신규만)...";  python3 summarize.py all || true   # 신규 null만 채움
echo "[3/5] 트렌드...";          python3 trends.py || true
# 카테고리 정적페이지 + sitemap. 실패 시 중단 — 스테일 페이지 배포 방지
echo "[4/5] 정적페이지·사이트맵..."; python3 prerender.py || fail "prerender.py 실패"
echo "[5/5] 배포...";            cd "$ROOT" || fail "ROOT 이동 실패"
npx --yes wrangler@4 pages deploy public --project-name ai-repo-radar --branch main --commit-dirty=true \
  || fail "wrangler 배포 실패"   # 배포 실패면 ✅ 금지 (거짓성공 방지)

COUNT=$(python3 -c "import json;print(json.load(open('$ROOT/public/data/repos.json'))['count'])" 2>/dev/null)
echo "완료: ${COUNT}개"
curl -s -d "✅ AI Repo Radar 갱신 완료: ${COUNT}개 repo (https://ai-repo-radar-1u7.pages.dev)" \
     -H "Title: AI Repo Radar" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null
echo "===== $(date '+%H:%M:%S') 끝 ====="
