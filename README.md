# AI Repo Radar

매일 GitHub에 올라오는 AI 오픈소스를 **카테고리로 분류**하고 **실전투입 점수**로 거른 뒤, **한국어 한줄요약**과 **분야별 방향(트렌드)**까지 붙여 보여주는 정적 큐레이션 사이트.

## 구조
```
public/                 # 정적 사이트 (그대로 배포)
  index.html
  app.js
  styles.css
  data/
    repos.json          # 수집·점수·분류·요약 결과
    trends.json         # 카테고리별 + 전체 방향 요약
scripts/
  fetch_repos.py        # GitHub Search 수집 + 실전점수 + 17종 분류 + 홈페이지 + 스타속도
  categories.py         # 카테고리 정의·분류기
  summarize.py          # 로컬 gemma 한국어 한줄요약 (think:false)
  trends.py             # 카테고리별/전체 방향 요약 + 글로벌 부상토픽
```

## 파이프라인
```bash
cd scripts
GITHUB_TOKEN=ghp_xxx python3 fetch_repos.py   # 1) 수집·점수·분류
python3 summarize.py all                        # 2) 한국어 요약(로컬 gemma, ollama 필요)
python3 trends.py                               # 3) 방향 요약
```

## 배포
정적 사이트. 빌드 불필요. 출력 디렉터리 = `public/`.
- **Cloudflare Pages**: 빌드 명령 없음 / 출력 `public` / 정적자산 대역폭 무제한
- push마다 자동 재배포

## 카테고리 (17)
MCP · Browser · Agent · RAG · Fine-tuning · Multimodal · Code-AI · Robotics · RL ·
Vision · Audio-Speech · NLP · Eval · MLOps · Dataset · Prompt · LLM

## 점수(prod_score) 산식
유지보수 최신성(40) + 라이선스(20) + 인기 로그스케일(25) + 문서/메타(15). archived = 0.
근거를 `prod_reasons`로 함께 노출.
