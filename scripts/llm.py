"""
LLM 백엔드 스위치 — 로컬 ollama(gemma) ↔ 클라우드 OpenRouter.
환경변수로 전환:
  LLM_BACKEND=ollama (기본)  또는  openrouter
  OpenRouter 사용 시: OPENROUTER_API_KEY (필수), OPENROUTER_MODEL (필수, 예: 무료모델 ID)

OpenRouter 무료모델은 ~20req/min·200req/day 한도 → 호출 간 sleep + 429 백오프 내장.
모델 ID는 자주 바뀌므로(:free 들고남) env로 주입 — openrouter.ai/models 에서 Price=Free 골라 넣을 것.
"""
import json
import os
import time
import urllib.error
import urllib.request

BACKEND = os.environ.get("LLM_BACKEND", "ollama").lower()
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:latest")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_MODEL = os.environ.get("OPENROUTER_MODEL", "")
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
    """프롬프트 → 응답 텍스트(raw). 백엔드 자동 선택. 실패/빈응답 시 ''."""
    try:
        return (_openrouter if BACKEND == "openrouter" else _ollama)(prompt, max_tokens, temperature)
    except Exception:
        return ""
