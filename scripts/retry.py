"""Retry an existing Oracle Resource Manager stack from a GitHub-hosted runner."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import time

WINDOW = 330 * 60
ACTIVE = {"ACCEPTED", "IN_PROGRESS", "CANCELING"}


class Throttled(Exception):
    pass


def prepare_key(directory):
    for name in ("OCI_CLI_USER", "OCI_CLI_TENANCY", "OCI_CLI_REGION",
                 "OCI_CLI_FINGERPRINT", "OCI_STACK_ID", "OCI_CLI_KEY_CONTENT"):
        if not os.environ.get(name, "").strip():
            raise SystemExit(f"Missing GitHub Actions secret {name}")

    raw = os.environ.pop("OCI_CLI_KEY_CONTENT").replace(r"\n", "\n")
    match = re.search(r"-----BEGIN (RSA PRIVATE KEY|PRIVATE KEY)-----"
                      r"([A-Za-z0-9+/=\s]+)-----END \1-----", raw)
    if not match:
        raise SystemExit("OCI_CLI_KEY_CONTENT must contain the full RSA private PEM.")
    label, body = match.groups()
    lines = textwrap.wrap("".join(body.split()), 64)
    path = Path(directory) / "signing.pem"
    with path.open("x") as f:
        path.chmod(0o600)
        f.write("\n".join([f"-----BEGIN {label}-----", *lines, f"-----END {label}-----", ""]))
    check = subprocess.run(["openssl", "rsa", "-in", str(path), "-noout", "-check",
                            "-passin", "pass:"], capture_output=True)
    if check.returncode:
        raise SystemExit("OCI_CLI_KEY_CONTENT is malformed or encrypted.")
    os.environ["OCI_CLI_KEY_FILE"] = str(path)


def oracle(*args):
    result = subprocess.run(
        ["oci", "resource-manager", "job", *args, "--output", "json",
         "--no-retry", "--connection-timeout", "15", "--read-timeout", "60"],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode:
        if re.search(r'"status"\s*:\s*429\b|\bTooManyRequests\b', result.stderr, re.I):
            raise Throttled
        raise SystemExit(f"Oracle CLI failed during {args[0]}:\n{result.stderr.strip()}")
    if args[0] == "list" and not result.stdout.strip():
        return []  # OCI CLI can omit output for an empty collection.
    return json.loads(result.stdout)["data"]


def summary(message):
    line = f"{time.strftime('%H:%M:%S UTC', time.gmtime())} {message}"
    print(line, flush=True)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        print(f"- {line}", file=f)


def output(name, value):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        print(f"{name}={value}", file=f)


def retry():
    stack = os.environ["OCI_STACK_ID"]
    name = "orecle-retry-" + os.environ["GITHUB_REPOSITORY_ID"]
    end = time.monotonic() + WINDOW
    job_id = None
    attempt = 0
    while time.monotonic() < end:
        delay = 30
        try:
            if job_id:
                job = oracle("get", "--job-id", job_id)
            else:
                history = oracle("list", "--stack-id", stack, "--all")
                successful = next((j for j in history if j["operation"] == "APPLY"
                                   and j["lifecycle-state"] == "SUCCEEDED"), None)
                if successful:
                    job = successful
                elif any(j["lifecycle-state"] in ACTIVE for j in history):
                    # A previous runner or a manual operation still owns the stack.
                    time.sleep(min(delay, max(0, end - time.monotonic())))
                    continue
                else:
                    attempt += 1
                    summary(f"Attempt {attempt}: submitting an apply.")
                    job = oracle("create-apply-job", "--stack-id", stack,
                                 "--execution-plan-strategy", "AUTO_APPROVED",
                                 "--display-name", name)

            state = job["lifecycle-state"]
            if state == "SUCCEEDED":
                if job.get("display-name") == name:
                    output("marker", hashlib.sha256(job["id"].encode()).hexdigest())
                    summary("SUCCEEDED. Checking the success notification.")
                    return "success"
                summary("SKIPPED. This stack already has a successful apply.")
                return "skip"
            if state in ACTIVE:
                job_id = job["id"]
            elif state in {"FAILED", "CANCELED"}:
                summary(f"Attempt {attempt}: {state}. Retrying in 10 minutes.")
                job_id = None
                delay = 600
            else:
                raise SystemExit(f"Unexpected Oracle job state: {state}")
        except Throttled:
            summary("RATE_LIMITED. Waiting 15 minutes before contacting Oracle.")
            delay = 900
        time.sleep(min(delay, max(0, end - time.monotonic())))

    summary("Retry window ended. Requesting a new workflow run.")
    return "continue"


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        prepare_key(directory)
        output("result", retry())
