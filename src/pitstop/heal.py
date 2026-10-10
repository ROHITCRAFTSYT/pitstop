"""The pit-stop loop: evaluate, diagnose, patch, verify, keep or revert, repeat."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

import neatlogs

from pitstop import evidence as evidence_mod
from pitstop.crew import diagnose, propose_patch
from pitstop.graph import EntireGraph
from pitstop.llm import LLM, BudgetExceeded
from pitstop.target import EditError, Target


@dataclass
class Verdict:
    accept: bool
    reason: str
    deltas: dict


def _passing_checks(results: dict) -> int:
    return sum(sum(1 for ok in t["checks"].values() if ok) for t in results["tasks"])


def compare(before: dict, after: dict) -> Verdict:
    """Accept a candidate only if it measurably improves the agent and breaks nothing."""
    b, a = before["summary"], after["summary"]
    was_passing = {t["id"] for t in before["tasks"] if t["passed"]}
    regressions = [t["id"] for t in after["tasks"] if t["id"] in was_passing and not t["passed"]]
    deltas = {
        "passed": (b["passed"], a["passed"]),
        "checks": (_passing_checks(before), _passing_checks(after)),
        "total_tokens": (b["total_tokens"], a["total_tokens"]),
        "cost_usd": (b["cost_usd"], a["cost_usd"]),
        "tool_errors": (b["tool_errors"], a["tool_errors"]),
        "avg_steps": (b["avg_steps"], a["avg_steps"]),
    }
    if regressions:
        return Verdict(False, f"regressed previously passing tasks: {regressions}", deltas)
    if a["passed"] > b["passed"]:
        return Verdict(True, f"{a['passed'] - b['passed']} more task(s) pass", deltas)
    token_cut = 1 - a["total_tokens"] / max(b["total_tokens"], 1)
    checks_b, checks_a = deltas["checks"]
    if checks_a > checks_b:
        # Token use is itself a check, so a net gain in checks already accounts for it.
        return Verdict(True, f"{checks_a - checks_b} more check(s) pass", deltas)
    if checks_a == checks_b and token_cut >= 0.10:
        return Verdict(True, f"same results with {token_cut:.0%} fewer tokens", deltas)
    return Verdict(False, "no measurable improvement", deltas)


def _done(results: dict) -> bool:
    return results["summary"]["passed"] == results["summary"]["tasks"]


@dataclass
class HealRun:
    run_id: str
    target: str
    branch: str | None = None
    baseline: dict | None = None
    final: dict | None = None
    attempts: list[dict] = field(default_factory=list)
    evals: list[dict] = field(default_factory=list)
    stopped: str = ""
    started: float = field(default_factory=time.time)
    finished: float | None = None


Emit = Callable[..., None]


def _noop(event: str, **data) -> None:
    pass


@neatlogs.span(kind="TOOL", name="pitstop.evaluate", tool_name="run_evals")
def _evaluate(target: Target, run: HealRun, variant: str, emit: Emit) -> dict:
    emit("eval_start", variant=variant)
    results = target.evaluate(run.run_id, variant)
    run.evals.append({"variant": variant, "summary": results["summary"], "path": results.get("path"),
                      "trace_ids": [t.get("trace_id") for t in results["tasks"]]})
    emit("eval_done", variant=variant, results=results)
    return results


@neatlogs.span(kind="WORKFLOW", name="pitstop.heal")
def heal(
    target: Target,
    llm: LLM,
    *,
    max_rounds: int = 4,
    tries_per_round: int = 2,
    traces: evidence_mod.NeatlogsTraces | None = None,
    graph: EntireGraph | None = None,
    emit: Emit = _noop,
    run_id: str | None = None,
) -> HealRun:
    run = HealRun(run_id=run_id or time.strftime("%m%d-%H%M") + "-" + uuid.uuid4().hex[:4], target=target.name)
    target.ensure_clean()
    run.branch = target.start_branch(run.run_id)
    emit("start", run=run)

    current = _evaluate(target, run, "baseline", emit)
    run.baseline = current
    try:
        for round_no in range(1, max_rounds + 1):
            if _done(current):
                run.stopped = "all tasks pass"
                break
            emit("diagnose_start", round=round_no)
            evidence = evidence_mod.build(current, traces)
            sites = graph.localize(current) if graph else None
            if sites:
                evidence += "\n\n# candidate fix sites (Entire Graph)\n" + sites
                emit("localized", round=round_no, searches=graph.searches)
            hypotheses = diagnose(llm, target, evidence, run.attempts)
            emit("diagnosed", round=round_no, hypotheses=hypotheses)
            improved = False
            for hypothesis in hypotheses[:tries_per_round]:
                attempt = _try(target, llm, run, current, hypothesis, round_no, emit)
                run.attempts.append(attempt)
                if attempt["outcome"] == "accepted":
                    current = attempt["_results"]
                    improved = True
                    break
            if not improved:
                emit("stuck", round=round_no)
        else:
            run.stopped = run.stopped or f"reached {max_rounds} rounds"
        if not run.stopped:
            run.stopped = "all tasks pass" if _done(current) else f"reached {max_rounds} rounds"
    except BudgetExceeded as exc:
        run.stopped = f"budget: {exc}"
        target.revert()
    run.final = current
    run.finished = time.time()
    for a in run.attempts:
        a.pop("_results", None)
    emit("finish", run=run)
    return run


def _try(target: Target, llm: LLM, run: HealRun, current: dict, hypothesis: dict, round_no: int, emit: Emit) -> dict:
    title = hypothesis.get("title", "untitled fix")
    attempt = {"round": round_no, "title": title, "hypothesis": hypothesis, "outcome": "rejected", "reason": "", "diff": ""}
    emit("attempt_start", attempt=attempt)
    feedback = None
    for repair in range(2):
        edits, summary = propose_patch(llm, target, hypothesis, feedback)
        attempt["summary"] = summary
        try:
            files = target.apply(edits)
        except EditError as exc:
            feedback = str(exc)
            emit("patch_failed", attempt=attempt, error=feedback, will_retry=repair == 0)
            neatlogs.log("patch could not be applied: {error}", level="warning", error=feedback)
            continue
        ok, output = target.run_tests()
        if ok:
            break
        target.revert()
        feedback = f"tests failed after your edit:\n{output[-1500:]}"
        emit("tests_failed", attempt=attempt, output=output, will_retry=repair == 0)
        neatlogs.log("tests failed after patch", level="warning")
    else:
        attempt["reason"] = f"could not produce a working patch: {feedback[:300]}"
        emit("attempt_done", attempt=attempt)
        return attempt

    attempt["files"] = files
    attempt["diff"] = target.diff()
    emit("patched", attempt=attempt)
    candidate = _evaluate(target, run, f"r{round_no}-{len(run.attempts) + 1}", emit)
    verdict = compare(current, candidate)
    attempt["deltas"] = verdict.deltas
    attempt["reason"] = verdict.reason
    attempt["variant"] = candidate["summary"]["variant"]
    if verdict.accept:
        attempt["outcome"] = "accepted"
        attempt["_results"] = candidate
        b, a = current["summary"], candidate["summary"]
        attempt["commit"] = target.commit(
            f"pitstop: {attempt['summary']}\n\n{hypothesis.get('root_cause', '')}\n\n"
            f"verdict: {verdict.reason}\n"
            f"passed {b['passed']}/{b['tasks']} -> {a['passed']}/{a['tasks']}, "
            f"tokens {b['total_tokens']} -> {a['total_tokens']}, tool errors {b['tool_errors']} -> {a['tool_errors']}\n"
            f"pitstop-run: {run.run_id}"
        )
    else:
        target.revert()
    neatlogs.log("attempt {title}: {outcome} ({reason})", title=title, outcome=attempt["outcome"], reason=verdict.reason)
    emit("attempt_done", attempt=attempt)
    return attempt
