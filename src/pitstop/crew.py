"""The two model-backed roles in a pit stop: the diagnostician and the mechanic."""

from __future__ import annotations

import json

import neatlogs

from pitstop.llm import LLM
from pitstop.target import Edit, Target

DIAGNOSE_SYSTEM = """You are Pitstop, an engineer who debugs AI agents from their execution traces.

You get an agent's eval evidence (failed checks, the step-by-step tool timeline,
token counts, and neatlogs trace spans when available) plus its source code.
Find the root causes of the failures.

Rules:
- Every hypothesis must cite concrete evidence: task id, step number, failure text.
- Fix the agent, never the evals or the data. Files marked READ-ONLY cannot change.
- One root cause per hypothesis. Rank by how many failing checks it would fix.
- Never propose hard-coding task inputs, company names or expected answers.
- Skip anything already tried and accepted. If a fix was rejected, its diff and the
  failures that remained are shown: explain why it didn't work and propose a
  different fix, or drop the hypothesis.

Reply with only JSON:
{"hypotheses": [{"id": "h1", "title": "...", "root_cause": "...",
  "evidence": ["..."], "files": ["path"], "fix_plan": "...",
  "expected_effect": "which checks/tasks should flip and the token impact",
  "confidence": 0.0}]}"""

PATCH_SYSTEM = """You are Pitstop's mechanic. Implement exactly one fix as minimal search/replace edits.

Rules:
- Only edit files marked EDITABLE.
- `search` is copied verbatim from the current file, includes enough lines to be
  unique, and must match exactly once.
- Keep public function names and signatures unchanged.
- General fixes only: no hard-coded task ids, inputs, company names or answers.
- Match the surrounding code style.

Reply with only JSON:
{"edits": [{"file": "path", "search": "...", "replace": "..."}],
 "summary": "one-line commit message"}"""


def _attempts_text(attempts: list[dict]) -> str:
    if not attempts:
        return "none yet"
    lines = []
    for a in attempts:
        lines.append(f"- round {a['round']} [{a['outcome']}] {a['title']}: {a['reason']}")
        if a["outcome"] != "accepted" and a.get("diff"):
            lines.append(f"  rejected diff:\n{a['diff'][:800]}")
            lines.append(f"  still failing after it: {a.get('after_failures')}")
    return "\n".join(lines)


@neatlogs.span(kind="AGENT", name="pitstop.diagnose", role="diagnostician", goal="root-cause agent failures from traces")
def diagnose(llm: LLM, target: Target, evidence: str, attempts: list[dict]) -> list[dict]:
    user = (
        f"Agent: {target.name} - {target.description}\n\n"
        f"Previous pit-stop attempts:\n{_attempts_text(attempts)}\n\n"
        f"Evidence:\n{evidence}\n\nSource:\n{target.source_bundle()}"
    )
    reply = llm.json("diagnose", DIAGNOSE_SYSTEM, user)
    hypotheses = reply.get("hypotheses", []) if isinstance(reply, dict) else reply
    hypotheses = sorted(hypotheses, key=lambda h: -float(h.get("confidence", 0)))
    neatlogs.log("diagnosed {n} hypotheses", n=len(hypotheses), titles=json.dumps([h.get("title") for h in hypotheses]))
    return hypotheses


@neatlogs.span(kind="AGENT", name="pitstop.patch", role="mechanic", goal="implement one fix as minimal edits")
def propose_patch(
    llm: LLM, target: Target, hypothesis: dict, feedback: str | None = None, attempts: list[dict] | None = None
) -> tuple[list[Edit], str]:
    user = (
        f"Fix this root cause:\n{json.dumps(hypothesis, indent=2)}\n\n"
        f"Earlier attempts (do not repeat a rejected diff):\n{_attempts_text(attempts or [])}\n\n"
        f"Current source:\n{target.source_bundle(include_context=False)}"
    )
    if feedback:
        user += f"\n\nYour previous edit could not be applied or failed tests:\n{feedback}\nTry again."
    reply = llm.json("patch", PATCH_SYSTEM, user)
    edits = [Edit(e["file"], e["search"], e["replace"]) for e in reply.get("edits", [])]
    return edits, reply.get("summary") or hypothesis.get("title", "pitstop fix")
