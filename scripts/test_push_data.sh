#!/bin/bash
# test_push_data.sh — push_data 회귀 테스트(격리 샌드박스, 실제 origin 무관).
# 가짜 bare origin + CI 클론 + 로컬 클론을 만들고, 07-21·07-28 좌초 시나리오를 포함한
# 9케이스를 돌린다. 사용: bash scripts/test_push_data.sh [결과파일]
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
LIB="$HERE/push_data.sh"
RESULT="${1:-}"
SB=$(mktemp -d "${TMPDIR:-/tmp}/push_data_test.XXXXXX")
trap 'rm -rf "$SB"' EXIT
ORIGIN="$SB/origin.git"; CI="$SB/ci"; LOCAL="$SB/local"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  PASS: $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
check(){ if eval "$2"; then ok "$1"; else bad "$1 [$2]"; fi; }

gen() {  # gen <dir> <count> <tag>  — 생성물 통째 재생성(양쪽이 같은 파일을 다르게 바꿈)
  local d="$1" n="$2" t="$3"
  mkdir -p "$d/public/data" "$d/public/c/a" "$d/public/c/b"
  python3 - "$d" "$n" "$t" <<'PY'
import json,sys
d,n,t=sys.argv[1],int(sys.argv[2]),sys.argv[3]
json.dump({"generated_at":t,"count":n,"repos":[{"id":i,"summary_ko":f"{t}-{i}"} for i in range(n)]},open(f"{d}/public/data/repos.json","w"),indent=1)
json.dump({"generated_at":t,"overall":t},open(f"{d}/public/data/trends.json","w"),indent=1)
for c in ("a","b"):
    open(f"{d}/public/c/{c}/index.html","w").write(f"<html>{c} {t} {n}\n"+"\n".join(f"line {i} {t}" for i in range(20))+"</html>\n")
open(f"{d}/public/sitemap.xml","w").write(f"<urlset lastmod='{t}'/>\n")
open(f"{d}/public/index.html","w").write(f"<html>index {t}</html>\n")
PY
}
gitc() { git -c user.name=t -c user.email=t@t "$@"; }
count_of() { python3 -c "import json,sys;print(json.load(sys.stdin)['count'])"; }
origin_count() { (cd "$LOCAL" && git fetch -q origin main && git show origin/main:public/data/repos.json | count_of); }
origin_tip()   { (cd "$LOCAL" && git ls-remote -q origin main | cut -c1-40); }
ci_push() {  # CI 가 생성물 재생성 후 커밋·push (update.yml 과 동일한 방식: add/commit/push, pull 없음)
  (cd "$CI" && git pull -q --rebase origin main && gen "$CI" "$1" "ci-$1" \
   && gitc add public && gitc commit -q -m "chore: daily cloud refresh" && git push -q origin main)
}
run_push() { (cd "$LOCAL" && source "$LIB" && push_data); }

echo "샌드박스: $SB"
git init -q --bare "$ORIGIN"
git init -q "$LOCAL" && (cd "$LOCAL" && git checkout -q -b main && git remote add origin "$ORIGIN")
mkdir -p "$LOCAL/scripts"; echo 'echo v1' > "$LOCAL/scripts/x.sh"
gen "$LOCAL" 1 seed
(cd "$LOCAL" && gitc add -A && gitc commit -q -m init && git push -q -u origin main)
git clone -q "$ORIGIN" "$CI"

echo "[1] 기본: CI 커밋 없이 로컬 생성물 push"
gen "$LOCAL" 2 local-2; run_push; rc=$?
check "exit 0" "[ $rc = 0 ]"
check "origin count=2" "[ \$(origin_count) = 2 ]"
check "local main == origin" "[ \$(cd $LOCAL && git rev-parse main) = \$(origin_tip) ]"
check "HEAD attached to main" "[ \$(cd $LOCAL && git symbolic-ref -q HEAD) = refs/heads/main ]"
check "working tree clean" "(cd $LOCAL && git status --porcelain | grep -q . && exit 1 || exit 0)"

echo "[2] CI 커밋이 사이에 낀 뒤 로컬 push (07-28 재현 — 과거엔 23파일 충돌)"
ci_push 100
gen "$LOCAL" 3 local-3; run_push; rc=$?
check "exit 0" "[ $rc = 0 ]"
check "origin count=3 (로컬 생성물이 이김)" "[ \$(origin_count) = 3 ]"
check "origin tip 부모 = CI 커밋" "(cd $LOCAL && git log -1 --format=%s origin/main~1 | grep -q 'cloud refresh')"
check "rebase 디렉토리 없음" "[ ! -d $LOCAL/.git/rebase-merge ]"

echo "[3] 옛 방식으로 좌초시킨 상태(detached + .git/rebase-merge)에서 복구 push (09-02 실전 상태 재현)"
ci_push 101
gen "$LOCAL" 4 local-4
(cd "$LOCAL" && gitc add public && gitc commit -q -m "stranded" && git pull --rebase -q origin main >/dev/null 2>&1; true)
check "재현: rebase-merge 잔존" "[ -d $LOCAL/.git/rebase-merge ]"
check "재현: HEAD detached" "! (cd $LOCAL && git symbolic-ref -q HEAD >/dev/null)"
gen "$LOCAL" 5 local-5   # 다음날 런이 충돌 마커 위에 생성물을 다시 씀
(cd "$LOCAL" && gitc add public && gitc commit -q -m "piled on detached" >/dev/null 2>&1; true)
run_push; rc=$?
check "exit 0" "[ $rc = 0 ]"
check "rebase 디렉토리 정리됨" "[ ! -d $LOCAL/.git/rebase-merge ]"
check "HEAD attached to main" "[ \$(cd $LOCAL && git symbolic-ref -q HEAD) = refs/heads/main ]"
check "origin count=5" "[ \$(origin_count) = 5 ]"
check "local main == origin" "[ \$(cd $LOCAL && git rev-parse main) = \$(origin_tip) ]"
check "working tree clean" "(cd $LOCAL && git status --porcelain | grep -q . && exit 1 || exit 0)"

echo "[4] 비생성물 로컬 커밋(미푸시)이 있으면 중단 + 무손실"
(cd "$LOCAL" && echo 'echo v2-local' > scripts/x.sh && gitc commit -q -am "local script change (unpushed)")
before_tip=$(origin_tip); before_head=$(cd "$LOCAL" && git rev-parse HEAD)
gen "$LOCAL" 6 local-6; run_push; rc=$?
check "exit 1" "[ $rc = 1 ]"
check "origin 불변" "[ \$(origin_tip) = $before_tip ]"
check "로컬 커밋 보존(HEAD 불변)" "[ \$(cd $LOCAL && git rev-parse HEAD) = $before_head ]"
check "생성물 작업트리 보존(count=6)" "[ \$(count_of < $LOCAL/public/data/repos.json) = 6 ]"
(cd "$LOCAL" && git push -q origin main)   # 사람이 푸시했다고 치고 정리

echo "[5] push 레이스: fetch 직후 CI 가 끼어들어 non-FF → 1회 재시도로 성공"
INJECT=1
git() {  # fetch 직후 CI 커밋 주입(1회)
  if [ "$1" = fetch ] && [ "$INJECT" = 1 ]; then command git "$@"; INJECT=0; ci_push 102 >/dev/null 2>&1; return 0; fi
  command git "$@"
}
gen "$LOCAL" 7 local-7; (cd "$LOCAL" && source "$LIB" && push_data); rc=$?
unset -f git
check "exit 0" "[ $rc = 0 ]"
check "origin count=7" "[ \$(origin_count) = 7 ]"
check "origin tip 부모 = 끼어든 CI 커밋" "(cd $LOCAL && git show origin/main~1:public/data/repos.json | count_of | grep -qx 102)"

echo "[6] 깨진 JSON(충돌 마커)은 push 하지 않는다"
before_tip=$(origin_tip)
printf '{\n<<<<<<< HEAD\n"count": 1\n=======\n"count": 2\n>>>>>>> x\n}\n' > "$LOCAL/public/data/repos.json"
run_push; rc=$?
check "exit 1" "[ $rc = 1 ]"
check "origin 불변" "[ \$(origin_tip) = $before_tip ]"
check "PUSH_STAGE=sanity" "[ \"\$(cd $LOCAL && source $LIB && push_data >/dev/null 2>&1; echo \$PUSH_STAGE)\" = sanity ]"

echo "[7] 변경없음이면 스킵(exit 0)"
gen "$LOCAL" 8 local-8; run_push >/dev/null; before_tip=$(origin_tip)
out=$(run_push); rc=$?
check "exit 0" "[ $rc = 0 ]"
check "스킵 메시지" "echo \"$out\" | grep -q '변경없음'"
check "origin 불변" "[ \$(origin_tip) = $before_tip ]"

echo "[8] origin 의 스크립트 변경 흡수(로컬 편집 없음) / 로컬 편집 보존"
(cd "$CI" && git pull -q --rebase origin main && echo 'echo v3-origin' > scripts/x.sh && gitc commit -q -am "script from other pc" && git push -q origin main)
gen "$LOCAL" 9 local-9; run_push >/dev/null; rc=$?
check "exit 0" "[ $rc = 0 ]"
check "작업트리 스크립트 = origin 판(v3)" "grep -q v3-origin $LOCAL/scripts/x.sh"
(cd "$CI" && git pull -q --rebase origin main && echo 'echo v4-origin' > scripts/x.sh && gitc commit -q -am "script from other pc 2" && git push -q origin main)
echo 'echo v4-LOCAL-EDIT' > "$LOCAL/scripts/x.sh"     # 로컬 미커밋 편집
gen "$LOCAL" 10 local-10; out=$(run_push); rc=$?
check "exit 0" "[ $rc = 0 ]"
check "origin count=10" "[ \$(origin_count) = 10 ]"
check "로컬 미커밋 편집 보존" "grep -q v4-LOCAL-EDIT $LOCAL/scripts/x.sh"
check "보존 안내 출력" "echo \"$out\" | grep -q '작업트리 보존'"

echo "[9] 생성물 누락 시 중단"
(cd "$LOCAL" && git checkout -q -- scripts/x.sh)
rm -f "$LOCAL/public/sitemap.xml"; before_tip=$(origin_tip)
run_push >/dev/null; rc=$?
check "exit 1" "[ $rc = 1 ]"
check "origin 불변" "[ \$(origin_tip) = $before_tip ]"

echo "===== 결과: PASS=$PASS FAIL=$FAIL ====="
[ -n "$RESULT" ] && printf 'PASS=%s\nFAIL=%s\n' "$PASS" "$FAIL" > "$RESULT"
[ "$FAIL" = 0 ]
