"""Write the pit-stop report: before/after numbers, every attempt, trace ids."""

from __future__ import annotations

import json
import pathlib

from pitstop.heal import HealRun
from pitstop.llm import Ledger


def _pct(before: float, after: float) -> str:
    if not before:
        return ""
    change = (after - before) / before
    return f" ({change:+.0%})"


def markdown(run: HealRun, ledger: Ledger, traces_used: int = 0, graph_searches: int = 0) -> str:
    b, f = run.baseline["summary"], run.final["summary"]
    accepted = [a for a in run.attempts if a["outcome"] == "accepted"]
    rejected = [a for a in run.attempts if a["outcome"] != "accepted"]
    lines = [
        f"# Pit stop `{run.run_id}` on `{run.target}`",
        "",
        f"- Branch: `{run.branch}`",
        f"- Model under test: `{b['model']}` · data: `{b['data']}`",
        f"- Stopped because: {run.stopped}",
        f"- Pitstop's own spend: ${ledger.spent_usd:.4f} over {ledger.calls} model calls ({ledger.tokens} tokens)",
        f"- neatlogs trace reads: {traces_used} · Entire Graph searches: {graph_searches}",
        "",
        *( [f"> **Needs a human.** {run.escalation}", ""] if run.escalation else [] ),
        "## Before → after",
        "",
        "| metric | before | after |",
        "|---|---|---|",
        f"| tasks passing | {b['passed']}/{b['tasks']} | {f['passed']}/{f['tasks']} |",
        f"| total tokens | {b['total_tokens']} | {f['total_tokens']}{_pct(b['total_tokens'], f['total_tokens'])} |",
        f"| est. cost (USD) | {b['cost_usd']:.4f} | {f['cost_usd']:.4f}{_pct(b['cost_usd'], f['cost_usd'])} |",
        f"| tool errors | {b['tool_errors']} | {f['tool_errors']} |",
        f"| avg steps | {b['avg_steps']} | {f['avg_steps']} |",
        f"| avg latency (s) | {b['avg_latency_s']} | {f['avg_latency_s']} |",
        "",
        f"## Accepted fixes ({len(accepted)})",
    ]
    for a in accepted:
        d = a["deltas"]
        lines += [
            "",
            f"### {a['summary']}",
            f"Round {a['round']} · commit `{a['commit'][:10]}` · {a['reason']}",
            "",
            f"**Root cause.** {a['hypothesis'].get('root_cause', '')}",
            "",
            "**Evidence.** " + "; ".join(a["hypothesis"].get("evidence", [])),
            "",
            f"passed {d['passed'][0]} → {d['passed'][1]}, checks {d['checks'][0]} → {d['checks'][1]}, "
            f"tokens {d['total_tokens'][0]} → {d['total_tokens'][1]}, tool errors {d['tool_errors'][0]} → {d['tool_errors'][1]}",
            "",
            "```diff",
            a["diff"].strip(),
            "```",
        ]
    lines += ["", f"## Rejected attempts ({len(rejected)})", ""]
    if not rejected:
        lines.append("None.")
    for a in rejected:
        lines.append(f"- Round {a['round']}: **{a['title']}**: {a['reason']}")
    lines += ["", "## Eval runs and neatlogs traces", ""]
    for e in run.evals:
        s = e["summary"]
        ids = ", ".join(f"`{t}`" for t in e["trace_ids"] if t) or "(neatlogs export off)"
        lines.append(f"- `{e['variant']}`: {s['passed']}/{s['tasks']} pass, {s['total_tokens']} tokens. Traces: {ids}")
    return "\n".join(lines) + "\n"


def write(run: HealRun, ledger: Ledger, out_dir: pathlib.Path, traces_used: int = 0, graph_searches: int = 0) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / f"pitstop-{run.run_id}.md"
    md.write_text(markdown(run, ledger, traces_used, graph_searches), encoding="utf-8", newline="\n")
    payload = {
        "run_id": run.run_id, "target": run.target, "branch": run.branch, "stopped": run.stopped,
        "escalation": run.escalation,
        "baseline": run.baseline["summary"], "final": run.final["summary"], "evals": run.evals,
        "attempts": run.attempts, "ledger": {"spent_usd": ledger.spent_usd, "calls": ledger.calls, "tokens": ledger.tokens},
        "started": run.started, "finished": run.finished,
    }
    (out_dir / f"pitstop-{run.run_id}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8", newline="\n")
    return md
