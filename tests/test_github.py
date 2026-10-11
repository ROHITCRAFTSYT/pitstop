import json
import subprocess

import pytest

from pitstop.github import PullRequestError, open_pr, title_for


def _report(tmp_path, attempts):
    md = tmp_path / "pitstop-x.md"
    md.write_text("# report\n", encoding="utf-8")
    summary = {"passed": 0, "tasks": 6, "total_tokens": 1000}
    md.with_suffix(".json").write_text(json.dumps({
        "branch": "pitstop/x", "attempts": attempts,
        "baseline": summary, "final": {**summary, "passed": 6, "total_tokens": 280},
    }), encoding="utf-8")
    return md


def test_title_summarises_the_improvement():
    assert title_for({"passed": 0, "tasks": 6, "total_tokens": 58879},
                     {"passed": 6, "tasks": 6, "total_tokens": 16302}) == "Pitstop: 0/6 → 6/6 tasks passing, -72% tokens"


def test_refuses_when_nothing_was_accepted(tmp_path):
    md = _report(tmp_path, [{"outcome": "rejected"}])
    with pytest.raises(PullRequestError, match="no accepted fixes"):
        open_pr(tmp_path, md)


def test_refuses_without_a_remote(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    md = _report(tmp_path, [{"outcome": "accepted"}])
    with pytest.raises(PullRequestError, match="no git remote"):
        open_pr(tmp_path, md)
