"""Open a pull request with the pit-stop report (needs an `origin` remote and the `gh` CLI)."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess


class PullRequestError(RuntimeError):
    pass


def _run(cmd: list[str], cwd: pathlib.Path) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if proc.returncode != 0:
        raise PullRequestError(f"{' '.join(cmd[:3])} failed: {(proc.stderr or proc.stdout).strip()[:400]}")
    return proc.stdout.strip()


def title_for(summary_before: dict, summary_after: dict) -> str:
    b, a = summary_before, summary_after
    change = (a["total_tokens"] - b["total_tokens"]) / max(b["total_tokens"], 1)
    return f"Pitstop: {b['passed']}/{b['tasks']} → {a['passed']}/{a['tasks']} tasks passing, {change:+.0%} tokens"


def open_pr(repo: pathlib.Path, report_md: pathlib.Path, base: str = "main") -> str:
    """Push the pit-stop branch recorded in the report and open a PR against `base`. Returns the PR URL."""
    if not shutil.which("gh"):
        raise PullRequestError("the GitHub CLI (gh) is not installed")
    data = json.loads(report_md.with_suffix(".json").read_text(encoding="utf-8"))
    if not any(a["outcome"] == "accepted" for a in data["attempts"]):
        raise PullRequestError("no accepted fixes, so there is nothing to propose")
    if not _run(["git", "remote"], repo):
        raise PullRequestError("the target repo has no git remote to push to")
    branch = data["branch"]
    _run(["git", "push", "-u", "origin", branch], repo)
    body = report_md.read_text(encoding="utf-8") + "\n---\nOpened by [Pitstop](https://github.com/ROHITCRAFTSYT/pitstop).\n"
    body_file = report_md.with_suffix(".pr.md")
    body_file.write_text(body, encoding="utf-8", newline="\n")
    try:
        return _run(["gh", "pr", "create", "--base", base, "--head", branch,
                     "--title", title_for(data["baseline"], data["final"]), "--body-file", str(body_file)], repo)
    finally:
        body_file.unlink(missing_ok=True)
