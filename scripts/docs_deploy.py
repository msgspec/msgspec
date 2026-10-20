"""Request isolated docs publishing and expose its outcome on pull requests."""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit

SOURCE = "msgspec/msgspec"
PUBLISHER = "msgspec/docs-deploy"
BUILDER = "docs-pr.yml"
BRIDGE = "docs-deploy.yml"
RESULT_ARTIFACT = "docs-deployment"
API_VERSION = "2026-03-10"


class DeploymentError(Exception):
    """A deployment prerequisite or result failed validation."""


class GitHub:
    def __init__(self, repository: str, token: str | None = None):
        self.repository = repository
        self.environment = os.environ.copy()
        if token is not None:
            self.environment["GH_TOKEN"] = token

    def api(self, path: str, *, body: dict | None = None, binary: bool = False):
        command = [
            "gh",
            "api",
            "--method",
            "POST" if body is not None else "GET",
            "--header",
            f"X-GitHub-Api-Version: {API_VERSION}",
            f"repos/{self.repository}/{path}",
        ]
        data = None
        if body is not None:
            command.extend(["--input", "-"])
            data = json.dumps(body).encode()
        process = subprocess.run(
            command, input=data, capture_output=True, env=self.environment
        )
        if process.returncode:
            raise DeploymentError(
                f"GitHub request failed for {self.repository}/{path}: "
                f"{process.stderr.decode(errors='replace').strip()}"
            )
        return process.stdout if binary else json.loads(process.stdout)

    def items(self, path: str, key: str, **query):
        for page in range(1, 11):
            parameters = urlencode({**query, "per_page": 100, "page": page})
            items = self.api(f"{path}?{parameters}")[key]
            yield from items
            if len(items) < 100:
                return
        raise DeploymentError(f"GitHub pagination limit reached for {path}")

    def watch(self, run_id: int):
        process = subprocess.run(
            [
                "gh",
                "run",
                "watch",
                str(run_id),
                "--repo",
                self.repository,
                "--compact",
                "--exit-status",
                "--interval",
                "15",
            ],
            env=self.environment,
        )
        if process.returncode:
            raise DeploymentError(
                f"Publishing failed or was canceled: "
                f"https://github.com/{self.repository}/actions/runs/{run_id}"
            )


def positive_integer(value, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise DeploymentError(f"Expected a positive integer for {field}")
    return value


def bridge_title(run: dict) -> str:
    return (
        f"Docs deploy for source run {positive_integer(run['id'], 'run ID')} "
        f"attempt {positive_integer(run['run_attempt'], 'run attempt')}"
    )


def result_from_archive(archive: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            entries = bundle.infolist()
            if len(entries) != 1 or entries[0].filename != "result.json":
                raise DeploymentError(
                    "Expected exactly result.json in deployment result"
                )
            if entries[0].file_size > 65536:
                raise DeploymentError("Deployment result is unexpectedly large")
            result = json.loads(bundle.read(entries[0]))
    except (zipfile.BadZipFile, UnicodeError, ValueError, KeyError) as exc:
        raise DeploymentError("Invalid deployment result archive") from exc
    if not isinstance(result, dict):
        raise DeploymentError("Deployment result must be a JSON object")
    return result


def download_result(client: GitHub, run_id: int) -> dict:
    artifacts = [
        artifact
        for artifact in client.items(f"actions/runs/{run_id}/artifacts", "artifacts")
        if artifact["name"] == RESULT_ARTIFACT
    ]
    if len(artifacts) != 1 or artifacts[0]["expired"]:
        raise DeploymentError(
            f"Expected one unexpired {RESULT_ARTIFACT} artifact for run {run_id}"
        )
    artifact_id = positive_integer(artifacts[0]["id"], "artifact ID")
    return result_from_archive(
        client.api(f"actions/artifacts/{artifact_id}/zip", binary=True)
    )


def validate_result(
    result: dict,
    builder: dict,
    *,
    target: str,
    publisher_run_id: int | None = None,
    pull_number: int | None = None,
):
    for field, expected in (
        ("source_run_id", builder["id"]),
        ("source_run_attempt", builder["run_attempt"]),
    ):
        if positive_integer(result.get(field), field) != expected:
            raise DeploymentError(f"Deployment result has an unexpected {field}")
    if result.get("source_sha") != builder["head_sha"]:
        raise DeploymentError("Deployment result belongs to a different source commit")
    if result.get("target") != target:
        raise DeploymentError("Deployment result has an unexpected target kind")
    actual_publisher = positive_integer(
        result.get("publisher_run_id"), "publisher run ID"
    )
    if publisher_run_id is not None and actual_publisher != publisher_run_id:
        raise DeploymentError("Deployment result belongs to a different publisher run")
    if type(result.get("published")) is not bool:
        raise DeploymentError(
            "Deployment result must state whether publishing occurred"
        )
    if target == "preview" and not result["published"]:
        raise DeploymentError("The preview was not published")
    url = result.get("url")
    if not isinstance(url, str) or any(character in url for character in "\r\n"):
        raise DeploymentError("Invalid deployment URL")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.netloc != parsed.hostname
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise DeploymentError("Invalid deployment URL")
    if target == "production" and parsed.hostname != "msgspec.dev":
        raise DeploymentError("Unexpected production URL")
    if target == "preview":
        expected = (
            f"pr-{pull_number}.msgspec.pages.dev" if pull_number is not None else None
        )
        if expected is not None and parsed.hostname != expected:
            raise DeploymentError("Unexpected preview URL")
        if expected is None and not (
            parsed.hostname
            and parsed.hostname.startswith("pr-")
            and parsed.hostname.endswith(".msgspec.pages.dev")
        ):
            raise DeploymentError("Unexpected preview URL")


def set_output(name: str, value: str):
    if any(character in value for character in "\r\n"):
        raise DeploymentError(f"Invalid multiline workflow output: {name}")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write(f"{name}={value}\n")


def summarize(message: str):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
        stream.write(message + "\n")


def publish_request(event: dict, source: GitHub, publisher: GitHub, directory: Path):
    trigger = event["workflow_run"]
    run_id = positive_integer(trigger["id"], "source run ID")
    attempt = positive_integer(trigger["run_attempt"], "source run attempt")
    workflow = source.api(f"actions/workflows/{BUILDER}")
    builder = source.api(f"actions/runs/{run_id}")
    if (
        builder["workflow_id"] != workflow["id"]
        or builder["path"] != f".github/workflows/{BUILDER}"
        or builder["run_attempt"] != attempt
        or builder["head_sha"] != trigger["head_sha"]
        or builder["status"] != "completed"
        or builder["conclusion"] != "success"
    ):
        raise DeploymentError(
            "The triggering docs build is no longer the successful attempt"
        )
    if builder["event"] == "pull_request":
        target = "preview"
    elif (
        builder["event"] == "push"
        and builder["head_branch"] == "main"
        and builder["head_repository"]["full_name"] == SOURCE
    ):
        target = "production"
    else:
        raise DeploymentError("Unsupported docs build event")
    response = publisher.api(
        "actions/workflows/publish.yml/dispatches",
        body={
            "ref": "main",
            "return_run_details": True,
            "inputs": {
                "source-run-id": str(run_id),
                "source-run-attempt": str(attempt),
            },
        },
    )
    publisher_run = positive_integer(response["workflow_run_id"], "publisher run ID")
    publisher_url = f"https://github.com/{PUBLISHER}/actions/runs/{publisher_run}"
    print(f"Requested publisher: {publisher_url}", flush=True)
    summarize(f"Publisher run: [{publisher_run}]({publisher_url}).")
    publisher.watch(publisher_run)
    outcome = publisher.api(f"actions/runs/{publisher_run}")
    if (
        outcome["event"] != "workflow_dispatch"
        or outcome["path"] != ".github/workflows/publish.yml"
        or outcome["head_branch"] != "main"
        or outcome["status"] != "completed"
        or outcome["conclusion"] != "success"
    ):
        raise DeploymentError(f"Publisher did not succeed: {publisher_url}")
    result = download_result(publisher, publisher_run)
    validate_result(result, builder, target=target, publisher_run_id=publisher_run)
    latest = source.api(f"actions/runs/{run_id}")
    if latest["run_attempt"] != attempt or latest["conclusion"] != "success":
        raise DeploymentError("The docs build was superseded while publishing")
    directory.mkdir(parents=True, exist_ok=True)
    result_path = directory / "result.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    set_output("result-path", str(result_path))
    summarize(f"Docs {target}: [{result['url']}]({result['url']}).")


@dataclass
class PreviewState:
    message: str
    result: dict | None = None


def latest_builder(source: GitHub, pull: dict) -> dict | None:
    for run in source.items(
        f"actions/workflows/{BUILDER}/runs",
        "workflow_runs",
        event="pull_request",
        head_sha=pull["head"]["sha"],
    ):
        if (
            run["head_sha"] == pull["head"]["sha"]
            and run["head_branch"] == pull["head"]["ref"]
            and run["head_repository"]["id"] == pull["head"]["repo"]["id"]
        ):
            return run
    return None


def inspect_preview(source: GitHub, event: dict) -> PreviewState:
    expected = event["pull_request"]
    number = positive_integer(expected["number"], "pull request number")
    pull = source.api(f"pulls/{number}")
    if pull["state"] != "open" or pull["head"]["sha"] != expected["head"]["sha"]:
        raise DeploymentError(
            "This pull request check was superseded or the PR was closed"
        )
    builder = latest_builder(source, pull)
    if builder is None:
        return PreviewState("Waiting for the docs build to be created")
    builder_url = f"https://github.com/{SOURCE}/actions/runs/{builder['id']}"
    if builder["conclusion"] == "action_required":
        return PreviewState(f"Waiting for fork-workflow approval: {builder_url}")
    if builder["status"] != "completed":
        return PreviewState(f"Waiting for the docs build: {builder_url}")
    if builder["conclusion"] != "success":
        raise DeploymentError(f"The docs build did not succeed: {builder_url}")
    title = bridge_title(builder)
    bridge = next(
        (
            run
            for run in source.items(
                f"actions/workflows/{BRIDGE}/runs",
                "workflow_runs",
                event="workflow_run",
                created=f">={builder['created_at']}",
            )
            if run["display_title"] == title
        ),
        None,
    )
    if bridge is None:
        return PreviewState(f"Waiting for a publisher request for {builder_url}")
    bridge_url = f"https://github.com/{SOURCE}/actions/runs/{bridge['id']}"
    if bridge["status"] != "completed":
        return PreviewState(f"Waiting for publishing: {bridge_url}")
    if bridge["conclusion"] != "success":
        raise DeploymentError(f"Docs publishing did not succeed: {bridge_url}")
    result = download_result(source, bridge["id"])
    validate_result(result, builder, target="preview", pull_number=number)
    current = latest_builder(source, pull)
    if current is None or (
        current["id"],
        current["run_attempt"],
        current["conclusion"],
    ) != (
        builder["id"],
        builder["run_attempt"],
        "success",
    ):
        return PreviewState("A newer docs build appeared; waiting for its publisher")
    latest_pull = source.api(f"pulls/{number}")
    if (
        latest_pull["state"] != "open"
        or latest_pull["head"]["sha"] != pull["head"]["sha"]
    ):
        raise DeploymentError("The pull request changed while checking the preview")
    return PreviewState(f"Preview published: {result['url']}", result)


def wait_for_preview(source: GitHub, event: dict, *, timeout: float = 55 * 60):
    deadline = time.monotonic() + timeout
    last_message = ""
    while time.monotonic() < deadline:
        state = inspect_preview(source, event)
        if state.message != last_message:
            print(state.message, flush=True)
            last_message = state.message
        if state.result is not None:
            set_output("preview-url", state.result["url"])
            summarize(f"Docs preview: [{state.result['url']}]({state.result['url']}).")
            return
        time.sleep(15)
    raise DeploymentError(f"Timed out waiting for docs publishing. {last_message}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("request", "check"))
    arguments = parser.parse_args()
    try:
        if os.environ["GITHUB_REPOSITORY"] != SOURCE:
            raise DeploymentError("This helper only supports msgspec/msgspec")
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        source = GitHub(SOURCE)
        if arguments.command == "request":
            if os.environ["GITHUB_EVENT_NAME"] != "workflow_run":
                raise DeploymentError("Publisher requests require workflow_run")
            publisher = GitHub(PUBLISHER, os.environ["DOCS_DISPATCH_TOKEN"])
            publish_request(
                event,
                source,
                publisher,
                Path(os.environ["RUNNER_TEMP"]) / RESULT_ARTIFACT,
            )
        else:
            if os.environ["GITHUB_EVENT_NAME"] != "pull_request":
                raise DeploymentError("Preview checks require pull_request")
            wait_for_preview(source, event)
    except (DeploymentError, KeyError, ValueError, OSError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
