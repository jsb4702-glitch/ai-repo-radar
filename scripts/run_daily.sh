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

[ -f "$ENVFILE" ] && source "$ENVFILE"
# OpenRouter 31B 강제 + 키 로드(요약·트렌드 모델 일관성)
[ -f "$HOME/.config/secrets.env" ] && source "$HOME/.config/secrets.env"
export LLM_BACKEND=openrouter
export OPENROUTER_MODEL="${OPENROUTER_MODEL:-google/gemma-4-31b-it:free}"
if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "ERROR: GITHUB_TOKEN 없음 ($ENVFILE 확인)"
  curl -s -d "AI Repo Radar 갱신 실패: GITHUB_TOKEN 없음" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null
  exit 1
fi

# ollama 데몬 보장
pgrep -x ollama >/dev/null || (ollama serve >/dev/null 2>&1 &) && sleep 3

cd "$SCRIPTS" || exit 1
echo "[1/4] 수집(요약보존)..."; GITHUB_TOKEN="$GITHUB_TOKEN" python3 fetch_repos.py || exit 1
echo "[2/4] 한글요약(신규만)...";  python3 summarize.py all || true   # 신규 null만 채움
echo "[3/4] 트렌드...";          python3 trends.py || true
echo "[4/4] 배포...";            cd "$ROOT" && npx wrangler pages deploy public --project-name ai-repo-radar --branch main --commit-dirty=true

COUNT=$(python3 -c "import json;print(json.load(open('$ROOT/public/data/repos.json'))['count'])" 2>/dev/null)
echo "완료: ${COUNT}개"
curl -s -d "✅ AI Repo Radar 갱신 완료: ${COUNT}개 repo (https://ai-repo-radar-1u7.pages.dev)" \
     -H "Title: AI Repo Radar" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null
echo "===== $(date '+%H:%M:%S') 끝 ====="
