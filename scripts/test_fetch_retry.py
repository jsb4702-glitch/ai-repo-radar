#!/usr/bin/env python3
"""
gh_get() 재시도 그물 회귀 테스트 — 표준 라이브러리만 (실행: python3 scripts/test_fetch_retry.py)

배경: 2026-07-19 일일 갱신이 http.client.IncompleteRead(응답 절단)로 죽었다.
재시도 4회가 이미 있었는데 잡는 예외가 (URLError, TimeoutError, OSError)뿐이라
HTTPException 계열인 IncompleteRead가 그물을 빠져나가 재시도 0회로 즉사했다.
"""

import http.client
import io
import unittest
import urllib.error
from unittest import mock

import fetch_repos

BODY = b'{"items": [{"full_name": "octocat/hello"}]}'


class FakeResponse(io.BytesIO):
    """urlopen 반환값 흉내 — with 문 + .headers 지원."""

    def __init__(self, body=BODY):
        super().__init__(body)
        self.headers = {"X-RateLimit-Remaining": "42"}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def urlopen_raising(*errors_then_ok):
    """앞선 호출은 순서대로 예외, 이후는 정상 응답. 호출 횟수를 세는 mock 반환."""

    seq = list(errors_then_ok)

    def _open(req, timeout=None):
        if _open.calls <= len(seq):
            raise seq[_open.calls - 1]
        return FakeResponse()

    def side_effect(req, timeout=None):
        side_effect.calls += 1
        _open.calls = side_effect.calls
        return _open(req, timeout)

    side_effect.calls = 0
    return side_effect


class GhGetRetryTest(unittest.TestCase):
    def setUp(self):
        # 백오프 sleep 제거 — 테스트가 60초 걸리면 안 된다
        patcher = mock.patch.object(fetch_repos.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, side_effect):
        with mock.patch.object(fetch_repos.urllib.request, "urlopen",
                               side_effect=side_effect) as m:
            return m

    # ---- 이번 수정의 핵심: 절단 응답이 재시도된다 --------------------------
    def test_incomplete_read_is_retried_then_succeeds(self):
        se = urlopen_raising(
            http.client.IncompleteRead(b"x" * 100, 200),
            http.client.IncompleteRead(b"x" * 100, 200),
        )
        with mock.patch.object(fetch_repos.urllib.request, "urlopen", side_effect=se):
            data, remaining = fetch_repos.gh_get("https://example.invalid/x")
        self.assertEqual(data["items"][0]["full_name"], "octocat/hello")
        self.assertEqual(remaining, "42")
        self.assertEqual(se.calls, 3, "2회 절단 후 3번째에 성공해야 함")

    def test_incomplete_read_exhausts_retries_and_raises(self):
        """계속 절단이면 4회 다 쓰고 원래 예외를 올린다 (무한반복 없음)."""
        se = urlopen_raising(*[http.client.IncompleteRead(b"", 1) for _ in range(10)])
        with mock.patch.object(fetch_repos.urllib.request, "urlopen", side_effect=se):
            with self.assertRaises(http.client.IncompleteRead):
                fetch_repos.gh_get("https://example.invalid/x")
        self.assertEqual(se.calls, 4, "retries=4 를 넘어 반복하면 안 됨")

    def test_bad_status_line_is_retried(self):
        se = urlopen_raising(http.client.BadStatusLine("garbage"))
        with mock.patch.object(fetch_repos.urllib.request, "urlopen", side_effect=se):
            data, _ = fetch_repos.gh_get("https://example.invalid/x")
        self.assertEqual(se.calls, 2)
        self.assertIn("items", data)

    # ---- 회귀: 기존 동작이 그대로인가 -------------------------------------
    def test_url_error_still_retried(self):
        se = urlopen_raising(urllib.error.URLError("dns"))
        with mock.patch.object(fetch_repos.urllib.request, "urlopen", side_effect=se):
            fetch_repos.gh_get("https://example.invalid/x")
        self.assertEqual(se.calls, 2)

    def test_http_4xx_raises_immediately(self):
        """403(rate limit)은 search_topic이 60초 대기로 처리한다 — gh_get이 삼키면 안 됨."""
        err = urllib.error.HTTPError("u", 403, "rate limit", {}, None)
        se = urlopen_raising(*[err] * 10)
        with mock.patch.object(fetch_repos.urllib.request, "urlopen", side_effect=se):
            with self.assertRaises(urllib.error.HTTPError):
                fetch_repos.gh_get("https://example.invalid/x")
        self.assertEqual(se.calls, 1, "4xx는 재시도 없이 즉시 raise")

    # ---- 5xx 재시도 (2026-07-17 붕괴 대응) --------------------------------
    def test_http_503_is_retried_then_succeeds(self):
        err = urllib.error.HTTPError("u", 503, "unavailable", {}, None)
        se = urlopen_raising(err, err)
        with mock.patch.object(fetch_repos.urllib.request, "urlopen", side_effect=se):
            data, _ = fetch_repos.gh_get("https://example.invalid/x")
        self.assertEqual(se.calls, 3, "503은 일시장애 → 재시도해야 함")
        self.assertIn("items", data)

    def test_http_503_exhausts_retries_and_raises(self):
        """계속 503이면 4회 쓰고 raise → search_topic이 skip 처리한다."""
        err = urllib.error.HTTPError("u", 503, "unavailable", {}, None)
        se = urlopen_raising(*[err] * 10)
        with mock.patch.object(fetch_repos.urllib.request, "urlopen", side_effect=se):
            with self.assertRaises(urllib.error.HTTPError):
                fetch_repos.gh_get("https://example.invalid/x")
        self.assertEqual(se.calls, 4)

    def test_deterministic_httpexception_not_retried(self):
        """InvalidURL 같은 결정론적 오류는 재시도로 삼키지 않는다 (원인 은폐 방지)."""
        se = urlopen_raising(*[http.client.InvalidURL("bad")] * 10)
        with mock.patch.object(fetch_repos.urllib.request, "urlopen", side_effect=se):
            with self.assertRaises(http.client.InvalidURL):
                fetch_repos.gh_get("https://example.invalid/x")
        self.assertEqual(se.calls, 1)

    def test_happy_path_single_call(self):
        se = urlopen_raising()
        with mock.patch.object(fetch_repos.urllib.request, "urlopen", side_effect=se):
            data, remaining = fetch_repos.gh_get("https://example.invalid/x")
        self.assertEqual(se.calls, 1)
        self.assertEqual(remaining, "42")


def fake_repo(i):
    return {
        "full_name": f"owner/repo{i}", "html_url": f"https://x/{i}",
        "description": "d", "stargazers_count": 100, "language": "Python",
        "topics": ["llm"], "license": {"spdx_id": "MIT"},
        "pushed_at": "2026-07-18T00:00:00Z", "created_at": "2025-01-01T00:00:00Z",
        "archived": False, "open_issues_count": 0,
    }


class ShrinkGuardTest(unittest.TestCase):
    """2026-07-17: 503 연속 skip으로 4,578→701개(15%)를 조용히 덮어써 요약이 날아갔다.
    수집이 붕괴하면 저장을 거부하고 기존 파일을 지켜야 한다."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.out = f"{self.tmp}/repos.json"
        for p, v in [("OUT_PATH", self.out), ("SEED_TOPICS", ["llm"]), ("SLEEP_SEC", 0)]:
            patcher = mock.patch.object(fetch_repos, p, v)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(fetch_repos.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def _seed(self, n):
        """기존 repos.json 을 n개로 깔아둔다 (요약 포함)."""
        import json as j
        with open(self.out, "w", encoding="utf-8") as f:
            j.dump({"count": n, "repos": [
                {"name": f"owner/repo{i}", "summary_ko": "요약", "summary_en": "s"}
                for i in range(n)]}, f)

    def _run_with(self, n_collected, env=None):
        with mock.patch.object(fetch_repos, "search_topic",
                               return_value=[fake_repo(i) for i in range(n_collected)]), \
             mock.patch.dict(fetch_repos.os.environ, env or {}, clear=False):
            fetch_repos.main()

    def _saved_count(self):
        import json as j
        return len(j.load(open(self.out, encoding="utf-8"))["repos"])

    def test_collapse_refuses_to_save(self):
        self._seed(100)
        with self.assertRaises(SystemExit) as cm:
            self._run_with(10)          # 10%  ← 07-17 시나리오
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(self._saved_count(), 100, "기존 파일이 덮어써지면 안 된다")

    def test_normal_variation_saves(self):
        self._seed(100)
        self._run_with(90)              # 90% — 평시 변동은 ±3% 이내
        self.assertEqual(self._saved_count(), 90)

    def test_allow_shrink_overrides(self):
        self._seed(100)
        self._run_with(10, env={"ALLOW_SHRINK": "1"})
        self.assertEqual(self._saved_count(), 10, "의도적 축소는 통과해야 한다")

    def test_first_run_has_no_baseline(self):
        self._run_with(5)               # 기존 파일 없음 → 붕괴 판정 대상 아님
        self.assertEqual(self._saved_count(), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
