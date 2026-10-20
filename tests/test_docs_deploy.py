"""Regression tests for PR-visible docs deployment outcomes."""

import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import docs_deploy as deploy


def archive(result):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("result.json", json.dumps(result))
    return buffer.getvalue()


class FakeGitHub:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []
        self.watched = []

    def api(self, path, **kwargs):
        self.requests.append((path, kwargs))
        response = self.responses[path]
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)

    def items(self, path, key, **query):
        self.requests.append((path, query))
        return iter(copy.deepcopy(self.responses[path]))

    def watch(self, run_id):
        self.watched.append(run_id)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.pull = {
            "number": 42,
            "state": "open",
            "head": {"sha": "a" * 40, "ref": "docs-change", "repo": {"id": 123}},
        }
        self.builder = {
            "id": 100,
            "run_attempt": 2,
            "workflow_id": 10,
            "path": ".github/workflows/docs-pr.yml",
            "head_sha": self.pull["head"]["sha"],
            "head_branch": "docs-change",
            "head_repository": {"id": 123},
            "event": "pull_request",
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-10-20T00:00:00Z",
        }
        self.bridge = {
            "id": 200,
            "display_title": deploy.bridge_title(self.builder),
            "status": "completed",
            "conclusion": "success",
        }
        self.result = {
            "source_run_id": 100,
            "source_run_attempt": 2,
            "source_sha": self.builder["head_sha"],
            "publisher_run_id": 300,
            "target": "preview",
            "published": True,
            "url": "https://pr-42.msgspec.pages.dev",
        }
        self.source = FakeGitHub(
            {
                "pulls/42": self.pull,
                "actions/workflows/docs-pr.yml": {"id": 10},
                "actions/runs/100": self.builder,
                "actions/workflows/docs-pr.yml/runs": [self.builder],
                "actions/workflows/docs-deploy.yml/runs": [self.bridge],
                "actions/runs/200/artifacts": [
                    {"id": 400, "name": "docs-deployment", "expired": False}
                ],
                "actions/artifacts/400/zip": archive(self.result),
            }
        )
        self.event = {"pull_request": copy.deepcopy(self.pull)}

    def inspect(self):
        return deploy.inspect_preview(self.source, self.event)

    def test_successful_preview(self):
        self.assertEqual(self.inspect().result, self.result)

    def test_fork_approval_is_pending(self):
        self.builder["conclusion"] = "action_required"
        self.assertIn("fork-workflow approval", self.inspect().message)
        self.assertIsNone(self.inspect().result)

    def test_build_failure_is_visible(self):
        for conclusion in ("failure", "cancelled", "timed_out", "skipped"):
            with self.subTest(conclusion=conclusion):
                self.builder["conclusion"] = conclusion
                with self.assertRaisesRegex(
                    deploy.DeploymentError, "build did not succeed"
                ):
                    self.inspect()

    def test_bridge_failure_is_visible(self):
        self.bridge["conclusion"] = "failure"
        with self.assertRaisesRegex(
            deploy.DeploymentError, "publishing did not succeed"
        ):
            self.inspect()

    def test_missing_bridge_is_pending(self):
        self.source.responses["actions/workflows/docs-deploy.yml/runs"] = []
        self.assertIsNone(self.inspect().result)

    def test_old_attempt_bridge_cannot_satisfy_check(self):
        self.bridge["display_title"] = "Docs deploy for source run 100 attempt 1"
        self.assertIsNone(self.inspect().result)

    def test_same_sha_in_other_fork_cannot_satisfy_check(self):
        self.builder["head_repository"]["id"] = 999
        self.assertIsNone(self.inspect().result)

    def test_changed_pr_fails(self):
        self.pull["head"]["sha"] = "b" * 40
        with self.assertRaisesRegex(deploy.DeploymentError, "superseded"):
            self.inspect()

    def test_missing_result_fails(self):
        self.source.responses["actions/runs/200/artifacts"] = []
        with self.assertRaisesRegex(deploy.DeploymentError, "one unexpired"):
            self.inspect()

    def test_mismatched_result_fails(self):
        for field, value in (
            ("source_run_id", 101),
            ("source_run_attempt", 1),
            ("source_sha", "b" * 40),
            ("target", "production"),
            ("published", False),
            ("publisher_run_id", True),
            ("url", "https://pr-43.msgspec.pages.dev"),
            ("url", "https://pr-42.msgspec.pages.dev.evil.example"),
            ("url", "https://pr-42.msgspec.pages.dev:443"),
            ("url", "https://pr-42.msgspec.pages.dev/path"),
        ):
            with self.subTest(field=field, value=value):
                result = {**self.result, field: value}
                with self.assertRaises(deploy.DeploymentError):
                    deploy.validate_result(
                        result, self.builder, target="preview", pull_number=42
                    )

    def test_result_zip_requires_exact_file(self):
        with self.assertRaises(deploy.DeploymentError):
            deploy.result_from_archive(b"not a zip")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("../result.json", "{}")
        with self.assertRaises(deploy.DeploymentError):
            deploy.result_from_archive(buffer.getvalue())

    def test_request_uses_exact_dispatch_response(self):
        publisher = FakeGitHub(
            {
                "actions/workflows/publish.yml/dispatches": {"workflow_run_id": 300},
                "actions/runs/300": {
                    "event": "workflow_dispatch",
                    "path": ".github/workflows/publish.yml",
                    "head_branch": "main",
                    "status": "completed",
                    "conclusion": "success",
                },
                "actions/runs/300/artifacts": [
                    {"id": 500, "name": "docs-deployment", "expired": False}
                ],
                "actions/artifacts/500/zip": archive(self.result),
            }
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(deploy, "set_output"),
            patch.object(deploy, "summarize"),
        ):
            deploy.publish_request(
                {"workflow_run": self.builder}, self.source, publisher, Path(directory)
            )
            self.assertEqual(
                json.loads((Path(directory) / "result.json").read_text()), self.result
            )
        self.assertEqual(publisher.watched, [300])
        self.assertEqual(
            publisher.requests[0][1]["body"],
            {
                "ref": "main",
                "return_run_details": True,
                "inputs": {"source-run-id": "100", "source-run-attempt": "2"},
            },
        )

    def test_stale_builder_attempt_cannot_dispatch(self):
        trigger = copy.deepcopy(self.builder)
        self.builder["run_attempt"] = 3
        publisher = FakeGitHub({})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(deploy.DeploymentError, "no longer"):
                deploy.publish_request(
                    {"workflow_run": trigger}, self.source, publisher, Path(directory)
                )
        self.assertEqual(publisher.requests, [])

    def test_timeout_fails(self):
        with patch.object(deploy.time, "monotonic", side_effect=[0, 1]):
            with self.assertRaisesRegex(deploy.DeploymentError, "Timed out"):
                deploy.wait_for_preview(self.source, self.event, timeout=0.5)


if __name__ == "__main__":
    unittest.main()
