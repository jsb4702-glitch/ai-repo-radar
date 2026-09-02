#!/bin/bash
# push_data.sh — 로컬 생성 산출물을 origin/main 위에 "덮어쓰기"로 반영하는 라이브러리.
# run_daily.sh 가 $ROOT 에서 source 해서 push_data 를 호출한다. 회귀 테스트: scripts/test_push_data.sh
#
# 왜 pull --rebase 를 버렸나 (2026-07-21·07-28 좌초, 09-02 진단: 연속 33회 실패):
#   CI(update.yml)와 로컬이 매일 같은 파일(repos.json·/c/*.html·sitemap)을 통째로 재생성해
#   커밋한다. 양쪽이 바꾼 파일을 3-way rebase 하면 사실상 매번 내용 충돌이고, 충돌로 좌초한
#   .git/rebase-merge 가 남으면 이후 런은 전부 "already a rebase-merge directory"로 죽는다.
#   생성물은 머지 대상이 아니라 최신본으로 갈아끼우는 게 원래 의도다. 그래서 origin/main
#   트리 위에 로컬 생성물만 얹은 커밋을 plumbing(read-tree/write-tree/commit-tree)으로 만들어
#   push 한다. 작업트리는 커밋 생성 중에 건드리지 않는다.
#
# 안전장치:
#   (1) 잔존 rebase/merge 상태는 --quit 로 정리하고 진행(작업트리 불변).
#   (2) 깨진 JSON(충돌 마커 등)은 절대 push 하지 않는다.
#   (3) origin 에 없는 "비생성물" 로컬 커밋이 있으면 중단 — 자동 push 가 사람게이트 대기
#       커밋을 실어 나르거나, main 을 되감아 그 커밋을 잃는 사고 방지.
#   (4) push 가 non-fast-forward 로 거부되면(그 사이 CI 커밋) fetch 부터 1회 재시도.
#   (5) 성공 후 로컬 main/HEAD 를 push 된 커밋으로 맞춘다. 비생성물에 로컬 편집이 없으면
#       작업트리도 동기화(origin 의 스크립트 변경 흡수), 있으면 작업트리는 보존.

GEN_PATHS=(public/data/repos.json public/data/trends.json public/c public/sitemap.xml public/index.html)
GEN_EXCLUDES=()
for _p in "${GEN_PATHS[@]}"; do GEN_EXCLUDES+=(":(exclude)$_p"); done
unset _p
PUSH_STAGE=""   # 실패 지점(알림용): preflight / sanity / fetch / guard / build / push / finalize

push_data() {
  local remote="${PUSH_REMOTE:-origin}" branch="${PUSH_BRANCH:-main}"
  local name="ai-repo-radar (local)" email="jsb4702@gmail.com"
  local msg="chore: daily local refresh (요약·트렌드 포함)"
  local gitdir; gitdir=$(git rev-parse --git-dir) || return 1

  PUSH_STAGE="preflight"
  if [ -d "$gitdir/rebase-merge" ] || [ -d "$gitdir/rebase-apply" ]; then
    echo "  ⚠️ 잔존 rebase 상태 발견 → git rebase --quit 로 정리(작업트리 불변)"
    git rebase --quit >/dev/null 2>&1 || rm -rf "$gitdir/rebase-merge" "$gitdir/rebase-apply"
  fi
  if [ -f "$gitdir/MERGE_HEAD" ]; then
    echo "  ⚠️ 잔존 merge 상태 발견 → 정리"
    git merge --quit >/dev/null 2>&1 || rm -f "$gitdir/MERGE_HEAD"
  fi

  PUSH_STAGE="sanity"
  local p
  for p in "${GEN_PATHS[@]}"; do
    [ -e "$p" ] || { echo "  생성물 없음: $p"; return 1; }
  done
  python3 -c "import json,sys; d=json.load(open('public/data/repos.json')); sys.exit(0 if d.get('count',0)>0 and d.get('repos') else 1)" 2>/dev/null \
    || { echo "  repos.json 파싱 실패/빈 데이터 — push 중단(깨진 데이터 전파 방지)"; return 1; }
  python3 -c "import json; json.load(open('public/data/trends.json'))" 2>/dev/null \
    || { echo "  trends.json 파싱 실패 — push 중단"; return 1; }

  local attempt base stray tmpidx tree commit oldhead
  oldhead=$(git rev-parse HEAD) || return 1
  for attempt in 1 2; do
    PUSH_STAGE="fetch"
    git fetch -q "$remote" "$branch" || return 1
    base=$(git rev-parse "refs/remotes/$remote/$branch") || return 1

    PUSH_STAGE="guard"
    stray=$(git rev-list "$base..HEAD" -- . "${GEN_EXCLUDES[@]}" | head -1)
    if [ -n "$stray" ]; then
      echo "  ❌ origin 에 없는 비생성물 로컬 커밋 있음(${stray:0:7}) — 자동 push 중단. 수동으로 push 하거나 정리 후 재실행"
      return 1
    fi

    PUSH_STAGE="build"
    tmpidx="$gitdir/index.push-data.$$"
    rm -f "$tmpidx"
    GIT_INDEX_FILE="$tmpidx" git read-tree "$base" || { rm -f "$tmpidx"; return 1; }
    GIT_INDEX_FILE="$tmpidx" git add -A -- "${GEN_PATHS[@]}" || { rm -f "$tmpidx"; return 1; }
    tree=$(GIT_INDEX_FILE="$tmpidx" git write-tree) || { rm -f "$tmpidx"; return 1; }
    rm -f "$tmpidx"
    if [ "$tree" = "$(git rev-parse "$base^{tree}")" ]; then
      echo "  변경없음(origin 과 동일) — 스킵"
      _push_data_finalize "$base" "$oldhead" "$branch"
      return $?
    fi
    commit=$(GIT_AUTHOR_NAME="$name" GIT_AUTHOR_EMAIL="$email" \
             GIT_COMMITTER_NAME="$name" GIT_COMMITTER_EMAIL="$email" \
             git commit-tree "$tree" -p "$base" -m "$msg") || return 1

    PUSH_STAGE="push"
    if git push -q "$remote" "$commit:refs/heads/$branch"; then
      _push_data_finalize "$commit" "$oldhead" "$branch" || return 1
      echo "  push 완료: ${commit:0:7} (base ${base:0:7})"
      return 0
    fi
    echo "  push 거부(시도 $attempt/2) — 그 사이 origin 이 움직였으면 fetch 부터 재시도"
  done
  return 1
}

# 로컬 main/HEAD 를 지정 커밋으로 맞춘다. 비생성물에 로컬 편집이 없으면 작업트리까지 동기화.
_push_data_finalize() {
  local commit="$1" oldhead="$2" branch="$3"
  PUSH_STAGE="finalize"
  git update-ref "refs/heads/$branch" "$commit" || return 1
  git symbolic-ref HEAD "refs/heads/$branch" || return 1
  if git diff --quiet "$oldhead" -- . "${GEN_EXCLUDES[@]}"; then
    git reset -q --hard "$commit" || return 1
  else
    git reset -q --mixed "$commit" || return 1
    echo "  ℹ️ 비생성물에 로컬 편집 있음 — 작업트리 보존(git status 확인)"
  fi
  return 0
}
