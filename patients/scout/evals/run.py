"""Scout eval harness.

Runs every task in evals/tasks.json through ``scout.agent.research`` and scores
the brief against the data source. Writes a JSON report that Pitstop reads.

    python -m evals.run --out results.json [--model claude-haiku] [--only stripe]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import uuid
from types import SimpleNamespace

import neatlogs
from scout.backends import get_backend

from evals.models import cost_usd, make_client

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_TOKEN_BUDGET = 8000
NUMBER_FIELDS = ("headcount", "total_funding_usd", "founded_year")


class MeteredClient:
    """Wraps a chat client and records each step without relying on agent code."""

    def __init__(self, inner, model: str) -> None:
        self.inner = inner
        self.model = model
        self.steps: list[dict] = []
        self._seen = 0
        self._names: dict[str, tuple[str, str]] = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        messages = kwargs.get("messages", [])
        tool_results = []
        for m in messages[self._seen:]:
            m = m if isinstance(m, dict) else m.model_dump()
            for c in m.get("tool_calls") or []:
                self._names[c["id"]] = (c["function"]["name"], c["function"]["arguments"])
            if m.get("role") == "tool":
                name, args = self._names.get(m.get("tool_call_id"), ("?", ""))
                content = str(m.get("content", ""))
                tool_results.append(
                    {"tool": name, "args": args, "chars": len(content), "error": content.startswith("ERROR"), "excerpt": content[:240]}
                )
        self._seen = len(messages)
        started = time.perf_counter()
        response = self.inner.chat.completions.create(**kwargs)
        usage = getattr(response, "usage", None)
        message = response.choices[0].message
        self.steps.append(
            {
                "step": len(self.steps) + 1,
                "tool_results_in": tool_results,
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "latency_s": round(time.perf_counter() - started, 3),
                "tool_calls_out": [
                    {"tool": c.function.name, "args": c.function.arguments} for c in (message.tool_calls or [])
                ],
                "content_excerpt": (message.content or "")[:400],
            }
        )
        return response

    @property
    def prompt_tokens(self) -> int:
        return sum(s["prompt_tokens"] for s in self.steps)

    @property
    def completion_tokens(self) -> int:
        return sum(s["completion_tokens"] for s in self.steps)


def _as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().replace(",", "").isdigit():
        return int(value.strip().replace(",", ""))
    return value


def truth_for(domain: str) -> dict:
    backend = get_backend()
    raw = backend.company(domain)
    people = backend.people(domain)

    def as_int(v):
        try:
            return int(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    return {
        "name": raw.get("company_name"),
        "headcount": as_int((raw.get("headcount") or {}).get("linkedin_headcount")),
        "total_funding_usd": as_int((raw.get("funding_and_investment") or {}).get("crunchbase_total_investment_usd")),
        "founded_year": as_int(raw.get("year_founded")),
        "people": {p.get("name") for p in people if p.get("name")},
    }


def score(task: dict, brief, error: str | None, metered: MeteredClient, budget: int) -> dict:
    checks, failures = {}, []
    checks["completed"] = isinstance(brief, dict)
    if not checks["completed"]:
        failures.append(f"no usable brief: {error}")
        brief = {}
    truth = truth_for(task["domain"])

    name = str(brief.get("company") or "")
    checks["identity"] = task["expect_name"].lower() in name.lower()
    if checks["completed"] and not checks["identity"]:
        failures.append(f"company name {name!r} does not match {task['expect_name']!r}")

    grounded = True
    for field in NUMBER_FIELDS:
        got, want = _as_int(brief.get(field)), truth[field]
        if not checks["completed"]:
            grounded = False
        elif want is None and got not in (None,):
            grounded = False
            failures.append(f"hallucinated {field}={got!r}: the data source has no value")
        elif want is not None and got != want:
            grounded = False
            failures.append(f"{field}={got!r} but the data source says {want!r}")
    checks["grounded_numbers"] = grounded

    people = brief.get("key_people") or []
    names = [p.get("name") for p in people if isinstance(p, dict)]
    unknown = [n for n in names if n not in truth["people"]]
    checks["grounded_people"] = bool(names) and not unknown
    if checks["completed"] and not names:
        failures.append("key_people is empty")
    if unknown:
        failures.append(f"key_people not in data source: {unknown}")

    total = metered.prompt_tokens + metered.completion_tokens
    checks["within_token_budget"] = total <= budget
    if not checks["within_token_budget"]:
        failures.append(f"used {total} tokens, budget is {budget}")

    return {"checks": checks, "failures": failures, "passed": all(checks.values())}


def _trace_id() -> str | None:
    try:
        from neatlogs._wrap_utils import active_neatlogs_context
        from opentelemetry import trace

        ctx = active_neatlogs_context()
        span = trace.get_current_span(ctx) if ctx is not None else trace.get_current_span()
        trace_id = span.get_span_context().trace_id
        return format(trace_id, "032x") if trace_id else None
    except Exception:
        return None


@neatlogs.span(kind="WORKFLOW", name="scout.eval_task")
def run_task(task: dict, client, model: str, budget: int) -> dict:
    from scout.agent import research

    metered = MeteredClient(client, model)
    started = time.perf_counter()
    brief, error = None, None
    try:
        brief = research(task["input"], client=metered, model=model)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    result = score(task, brief, error, metered, budget)
    neatlogs.log("scout task {task_id} passed={passed}", task_id=task["id"], passed=result["passed"])
    return {
        "id": task["id"],
        "input": task["input"],
        **result,
        "error": error,
        "brief": brief,
        "steps": metered.steps,
        "n_steps": len(metered.steps),
        "prompt_tokens": metered.prompt_tokens,
        "completion_tokens": metered.completion_tokens,
        "total_tokens": metered.prompt_tokens + metered.completion_tokens,
        "cost_usd": round(cost_usd(model, metered.prompt_tokens, metered.completion_tokens), 6),
        "latency_s": round(time.perf_counter() - started, 3),
        "tool_errors": sum(r["error"] for s in metered.steps for r in s["tool_results_in"]),
        "trace_id": _trace_id(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=os.environ.get("SCOUT_MODEL", "claude-haiku"))
    ap.add_argument("--only", action="append")
    ap.add_argument("--budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    args = ap.parse_args(argv)

    run_id = os.environ.get("PITSTOP_RUN_ID", uuid.uuid4().hex[:8])
    variant = os.environ.get("PITSTOP_VARIANT", "manual")
    if os.environ.get("NEATLOGS_API_KEY"):
        neatlogs.init(workflow_name="scout", tags=[f"run:{run_id}", f"variant:{variant}", f"model:{args.model}"])

    tasks = json.loads((ROOT / "evals" / "tasks.json").read_text(encoding="utf-8"))
    if args.only:
        tasks = [t for t in tasks if t["id"] in args.only]
    client = make_client(args.model)
    results = []
    with neatlogs.identify(session_id=f"{run_id}-{variant}"):
        for task in tasks:
            results.append(run_task(task, client, args.model, args.budget))

    n = len(results) or 1
    summary = {
        "run_id": run_id,
        "variant": variant,
        "model": args.model,
        "data": get_backend().name,
        "tasks": len(results),
        "passed": sum(r["passed"] for r in results),
        "pass_rate": round(sum(r["passed"] for r in results) / n, 3),
        "total_tokens": sum(r["total_tokens"] for r in results),
        "cost_usd": round(sum(r["cost_usd"] for r in results), 6),
        "avg_latency_s": round(sum(r["latency_s"] for r in results) / n, 3),
        "avg_steps": round(sum(r["n_steps"] for r in results) / n, 2),
        "tool_errors": sum(r["tool_errors"] for r in results),
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "tasks": results}, indent=2, default=str), encoding="utf-8")
    if os.environ.get("NEATLOGS_API_KEY"):
        neatlogs.flush()
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
