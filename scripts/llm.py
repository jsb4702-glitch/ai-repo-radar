"""
LLM 백엔드 스위치 — 클라우드 OpenRouter(기본) ↔ 로컬 ollama(gemma).
환경변수로 전환:
  LLM_BACKEND=openrouter (기본)  또는  ollama
  OpenRouter: OPENROUTER_API_KEY·OPENROUTER_MODEL — env 없으면 ~/.ai-repo-radar.env,
              ~/.config/secrets.env 에서 자동 흡수. 모델 기본값=google/gemma-4-31b-it:free.

★ 기본을 openrouter(31B)로 고정한 이유: 자동화(Actions)·로컬 cron·수동 재생성이
  '같은 모델'을 써야 배포 트렌드/요약 경향이 일관됨. 과거 수동 실행 시 LLM_BACKEND
  미지정 → 기본 ollama 8B로 떨어져 31B와 톤·내용이 달라진 사고가 있었음.
  로컬 8B를 의도적으로 쓸 때만 LLM_BACKEND=ollama 명시.

OpenRouter 무료모델은 ~20req/min·200req/day 한도 → 호출 간 sleep + 429 백오프 내장.
모델 ID는 자주 바뀜(:free 들고남) → OPENROUTER_MODEL env로 override 가능.
"""
import json
import os
import time
import urllib.error
import urllib.request


def _load_secret(name, default=""):
    """env 우선, 없으면 로컬 비밀파일에서 KEY 추출(값은 repo에 커밋 안 됨)."""
    if os.environ.get(name):
        return os.environ[name]
    for path in (os.path.expanduser("~/.ai-repo-radar.env"),
                 os.path.expanduser("~/.config/secrets.env")):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("export "):
                        line = line[7:]
                    if line.startswith(name + "="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except OSError:
            continue
    return default


BACKEND = os.environ.get("LLM_BACKEND", "openrouter").lower()
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:latest")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
OR_KEY = _load_secret("OPENROUTER_API_KEY")
OR_MODEL = _load_secret("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
OR_SLEEP = float(os.environ.get("OPENROUTER_SLEEP", "3.2"))  # 20/min 안전마진


def _ollama(prompt, max_tokens, temperature):
    body = json.dumps({
        "model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "think": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read()).get("response", "").strip()


def _openrouter(prompt, max_tokens, temperature):
    if not OR_KEY or not OR_MODEL:
        raise RuntimeError("OPENROUTER_API_KEY / OPENROUTER_MODEL 미설정")
    body = json.dumps({
        "model": OR_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature, "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(OR_URL, data=body, headers={
        "Authorization": f"Bearer {OR_KEY}",
        "Content-Type": "application/json",
        "X-Title": "AI Repo Radar",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out = json.loads(r.read())
            time.sleep(OR_SLEEP)  # rate limit 존중
            return (out["choices"][0]["message"]["content"] or "").strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:  # 한도 → 백오프
                time.sleep(8 * (attempt + 1))
                continue
            raise
    return ""


def complete(prompt, max_tokens=120, temperature=0.2):
    """프롬프트 → 응답 텍스트(raw). 백엔드 자동 선택. 일시오류 시 ''.
    설정오류(키/모델 미설정)는 raise — 조용히 묻혀 엉뚱한 결과 나는 것 방지."""
    fn = _openrouter if BACKEND == "openrouter" else _ollama
    try:
        return fn(prompt, max_tokens, temperature)
    except RuntimeError:
        raise
    except Exception:
        return ""
