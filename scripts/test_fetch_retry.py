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

    def test_http_error_raises_immediately(self):
        """403/5xx는 search_topic이 직접 처리한다 — gh_get에서 재시도하면 안 됨."""
        err = urllib.error.HTTPError("u", 403, "rate limit", {}, None)
        se = urlopen_raising(*[err] * 10)
        with mock.patch.object(fetch_repos.urllib.request, "urlopen", side_effect=se):
            with self.assertRaises(urllib.error.HTTPError):
                fetch_repos.gh_get("https://example.invalid/x")
        self.assertEqual(se.calls, 1, "HTTPError는 재시도 없이 즉시 raise")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
