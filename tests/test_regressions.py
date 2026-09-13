"""Regression coverage for polling deadlines and release metadata."""

import io
import os
from unittest.mock import patch

import pytest
from urllib3.response import HTTPResponse

from ixspy_ai_api import ImageClient, TaskTimeoutError, VideoClient, wait_for_task
from ixspy_ai_api.ai_client import _DeadlineRetry, _DeadlineTimeout, _polling_budget
from ixspy_ai_api.version import get_version
from tests.fakes import FakeSession


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("ixspy_ai_api.ai_client.time.monotonic", lambda: now[0])

    def sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr("ixspy_ai_api.ai_client.time.sleep", sleep)
    return now


def test_no_query_starts_at_deadline(clock):
    starts = []

    def fetch():
        starts.append(clock[0])
        clock[0] += 2
        return {"status": "processing"}

    with pytest.raises(TaskTimeoutError) as error:
        wait_for_task(fetch, 7, poll_interval=10, timeout=5)
    assert starts == [0]
    assert clock[0] == 5
    assert error.value.task_id == 7


@pytest.mark.parametrize("kind", ["image", "video", "hd"])
def test_all_sdk_pollers_pass_remaining_budget_to_http(clock, kind):
    client = VideoClient("dummy") if kind == "video" else ImageClient("dummy")
    session = FakeSession()
    client.session = session
    session.enqueue_envelope({"status": "processing"})
    if kind == "hd":
        session.enqueue_envelope({"status": "completed"})
    poll = {"image": "wait_for_completion", "video": "wait_for_video_completion", "hd": "wait_for_hd_image"}[kind]
    with pytest.raises(TaskTimeoutError):
        getattr(client, poll)(7, poll_interval=10, timeout=5)
    assert session.call_count == (2 if kind == "hd" else 1)
    assert all(call["timeout"].total == 5 for call in session.calls)
    # Deadline state must not leak into the next ordinary request.
    session.enqueue_envelope({"status": "completed"})
    client._request("GET", "/status")
    assert session.last_call["timeout"] == 90


def test_retry_after_cannot_extend_polling_budget(clock):
    retry = _DeadlineRetry(total=3, respect_retry_after_header=True)
    with _polling_budget(5, 9, "task"), pytest.raises(TaskTimeoutError):
        retry.sleep(HTTPResponse(status=429, headers={"Retry-After": "120"}))
    assert clock[0] == 5


def test_each_retry_recalculates_http_timeout(clock):
    with _polling_budget(5, 9, "task"):
        timeout = _DeadlineTimeout(total=5, connect=5, read=4)
        clock[0] += 3
        attempt = timeout.clone()
        assert attempt.total == 2
        assert attempt.connect_timeout == 2
        clock[0] = 5
        with pytest.raises(TaskTimeoutError):
            timeout.clone()


@pytest.mark.parametrize("upload,expected_calls", [(False, 1), (True, 2)])
def test_real_http_stack_only_retries_upload_posts(clock, upload, expected_calls):
    from ixspy_ai_api import ServerError

    responses = [
        HTTPResponse(body=io.BytesIO(b"failed"), status=503, preload_content=False),
        HTTPResponse(body=io.BytesIO(b'{"error":{"code":0},"data":{"url":"https://cdn.example/a"}}'),
                     status=200, preload_content=False),
    ]
    with ImageClient("dummy", base_url="http://example.invalid") as client:
        client.session.trust_env = False
        with patch("urllib3.connectionpool.HTTPConnectionPool._make_request", side_effect=responses) as send:
            if upload:
                assert client.upload_image_base64("aGVsbG8=") == "https://cdn.example/a"
            else:
                with pytest.raises(ServerError):
                    client.create_custom_composition(prompt="test")
            assert send.call_count == expected_calls


def test_real_http_stack_stops_retry_after_at_deadline(clock):
    response = HTTPResponse(body=io.BytesIO(b"busy"), status=429,
                            headers={"Retry-After": "120"}, preload_content=False)
    with ImageClient("dummy", base_url="http://example.invalid") as client:
        client.session.trust_env = False
        with patch("urllib3.connectionpool.HTTPConnectionPool._make_request", return_value=response) as send:
            with pytest.raises(TaskTimeoutError):
                client.wait_for_completion(7, timeout=5)
            assert send.call_count == 1
            assert clock[0] == 5


def test_late_success_is_not_returned_after_deadline(clock):
    def fetch():
        clock[0] += 6
        return {"status": "completed"}

    with pytest.raises(TaskTimeoutError):
        wait_for_task(fetch, 1, timeout=5)


@pytest.mark.parametrize("ref,name", [("refs/heads/main", "main"), ("refs/pull/123/merge", "123/merge"),
                                      ("refs/heads/1.2.3", "1.2.3")])
def test_branch_and_pr_refs_do_not_set_release_version(ref, name):
    with patch.dict(os.environ, {"GITHUB_REF": ref, "GITHUB_REF_NAME": name}, clear=True), \
            patch("ixspy_ai_api.version._version_from_metadata", return_value="0.0.0"):
        assert get_version() == "0.0.0"


def test_ci_development_version_and_release_tag():
    with patch.dict(os.environ, {"GITHUB_REF": "refs/heads/main", "IXSPY_AI_API_VERSION": "0.0.0.dev123"}, clear=True):
        assert get_version() == "0.0.0.dev123"
    with patch.dict(os.environ, {"GITHUB_REF": "refs/tags/v1.2.3rc1"}, clear=True):
        assert get_version() == "1.2.3rc1"
    with patch.dict(os.environ, {"GITHUB_REF": "refs/tags/v1.2.3-broken"}, clear=True), pytest.raises(ValueError):
        get_version()


def test_sdist_version_wins_over_installed_package(tmp_path):
    source = tmp_path / "ixspy_ai_api"
    source.mkdir()
    (tmp_path / "PKG-INFO").write_text("Name: ixspy-ai-api\nVersion: 1.2.3rc1\n", encoding="utf-8")
    with patch.dict(os.environ, {}, clear=True), \
            patch("ixspy_ai_api.version.__file__", str(source / "version.py")), \
            patch("importlib.metadata.version", return_value="1.1.2"):
        assert get_version() == "1.2.3rc1"
