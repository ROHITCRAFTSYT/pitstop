"""End-to-end pit stop on the Scout patient with scripted models and no network."""

import json
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from pitstop.cli import main as cli_main
from pitstop.heal import heal
from pitstop.llm import LLM, Ledger
from pitstop.target import Target

FENCE_FIX = {
    "edits": [{
        "file": "scout/agent.py",
        "search": "        return json.loads(message.content)",
        "replace": (
            "        text = (message.content or \"\").strip()\n"
            "        if text.startswith(\"```\"):\n"
            "            text = text.split(\"\\n\", 1)[1].rsplit(\"```\", 1)[0]\n"
            "        return json.loads(text)"
        ),
    }],
    "summary": "Strip markdown fences before parsing the final answer",
}

DOMAIN_FIX = {
    "edits": [
        {
            "file": "scout/tools.py",
            "search": "def _int(value):",
            "replace": (
                "def normalize_domain(value: str) -> str:\n"
                "    value = value.strip().lower()\n"
                "    value = value.split(\"://\", 1)[-1].split(\"/\", 1)[0]\n"
                "    return value[4:] if value.startswith(\"www.\") else value\n\n\n"
                "def _int(value):"
            ),
        },
        {
            "file": "scout/tools.py",
            "search": "    raw = get_backend().company(domain)",
            "replace": "    raw = get_backend().company(normalize_domain(domain))",
        },
        {
            "file": "scout/tools.py",
            "search": "    return get_backend().people(domain, titles)",
            "replace": "    return get_backend().people(normalize_domain(domain), titles)",
        },
    ],
    "summary": "Normalise URLs to bare domains before lookups",
}

TRIM_FIX = {
    "edits": [{
        "file": "scout/tools.py",
        "search": "    return get_backend().people(normalize_domain(domain), titles)",
        "replace": (
            "    people = get_backend().people(normalize_domain(domain), titles)\n"
            "    return [{\"name\": p.get(\"name\"), \"title\": p.get(\"title\")} for p in people[:10]]"
        ),
    }],
    "summary": "Return only name and title from people_search",
}

PROMPT_FIX = {
    "edits": [{
        "file": "scout/prompts.py",
        "search": "Every field is required. Never leave a field empty or null.",
        "replace": "Use only values your tools returned. If a value is unknown, use null.",
    }],
    "summary": "Let the agent report unknown values as null",
}

BAD_PATCH = {"edits": [{"file": "scout/agent.py", "search": "this text is not in the file", "replace": "x"}], "summary": "bad"}
FORBIDDEN_PATCH = {"edits": [{"file": "evals/run.py", "search": "DEFAULT_TOKEN_BUDGET = 8000", "replace": "DEFAULT_TOKEN_BUDGET = 10**9"}], "summary": "cheat"}


def hyp(title):
    return {"hypotheses": [{"id": "h1", "title": title, "root_cause": title, "evidence": ["task x"], "files": [], "fix_plan": "", "confidence": 0.9}]}


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **_):
        content = json.dumps(self.replies.pop(0))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=200),
        )


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    dest = tmp_path / "scout"
    assert cli_main(["init-demo", "--dest", str(dest)]) == 0
    return Target(dest, model="fake", python=sys.executable)


def test_baseline_fails_in_the_seeded_ways(sandbox):
    results = sandbox.evaluate("t", "baseline")
    assert results["summary"]["passed"] == 0
    failures = " ".join(f for t in results["tasks"] for f in t["failures"])
    assert "JSONDecodeError" in failures
    assert "budget" in failures


def test_full_pit_stop_fixes_scout(sandbox):
    script = [
        hyp("fenced JSON"), BAD_PATCH, FENCE_FIX,          # patch recovery: first edit doesn't apply
        hyp("URL inputs"), DOMAIN_FIX,
        hyp("people bloat"), FORBIDDEN_PATCH, TRIM_FIX,     # guardrail: evals are read-only
        hyp("invented numbers"), PROMPT_FIX,
    ]
    llm = LLM("claude-sonnet-4.6", Ledger(5.0), client=ScriptedLLM(script))
    events = []
    run = heal(sandbox, llm, max_rounds=5, tries_per_round=1, emit=lambda e, **d: events.append(e))

    assert run.baseline["summary"]["passed"] == 0
    assert run.final["summary"]["passed"] == 6, json.dumps(run.final["summary"])
    assert run.final["summary"]["total_tokens"] < run.baseline["summary"]["total_tokens"]
    assert [a["outcome"] for a in run.attempts] == ["accepted"] * 4
    assert events.count("patch_failed") == 2
    assert run.stopped == "all tasks pass"
    log = sandbox.git("log", "--oneline")
    assert log.count("pitstop:") == 4
    assert sandbox.git("status", "--porcelain") == ""


def test_rejects_patch_that_does_not_help_and_reverts(sandbox):
    useless = {"edits": [{"file": "scout/agent.py", "search": "MAX_STEPS = 10", "replace": "MAX_STEPS = 11"}], "summary": "more steps"}
    llm = LLM("claude-sonnet-4.6", Ledger(5.0), client=ScriptedLLM([hyp("step cap"), useless]))
    run = heal(sandbox, llm, max_rounds=1, tries_per_round=1)
    assert run.attempts[0]["outcome"] == "rejected"
    assert run.attempts[0]["reason"] == "no measurable improvement"
    assert "MAX_STEPS = 10" in sandbox.read("scout/agent.py")


def test_budget_stops_the_run(sandbox):
    llm = LLM("claude-sonnet-4.6", Ledger(0.001), client=ScriptedLLM([hyp("x"), FENCE_FIX]))
    run = heal(sandbox, llm, max_rounds=3, tries_per_round=1)
    assert run.stopped.startswith("budget")
    assert sandbox.git("status", "--porcelain") == ""


def test_identical_rejected_patch_is_not_retested(sandbox):
    useless = {"edits": [{"file": "scout/agent.py", "search": "MAX_STEPS = 10", "replace": "MAX_STEPS = 11"}], "summary": "more steps"}
    script = [hyp("step cap"), useless, hyp("step cap again"), useless, FENCE_FIX]
    llm = LLM("claude-sonnet-4.6", Ledger(5.0), client=ScriptedLLM(script))
    events = []
    run = heal(sandbox, llm, max_rounds=2, tries_per_round=1, emit=lambda e, **d: events.append(e))
    assert [a["outcome"] for a in run.attempts] == ["rejected", "accepted"]
    assert events.count("duplicate_patch") == 1
    assert events.count("eval_start") == 3
    assert run.attempts[0]["after_failures"]
