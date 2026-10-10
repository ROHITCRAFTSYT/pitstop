"""Turn eval results and neatlogs traces into compact evidence a model can reason over."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

MAX_TASKS = 4


def _step_line(step: dict) -> str:
    parts = [f"step {step['step']}: prompt={step['prompt_tokens']}tok completion={step['completion_tokens']}tok"]
    for r in step.get("tool_results_in", []):
        flag = " ERROR" if r["error"] else ""
        parts.append(f"  <- {r['tool']}({r['args']}) returned {r['chars']} chars{flag}: {r['excerpt'][:160]!r}")
    for c in step.get("tool_calls_out", []):
        parts.append(f"  -> calls {c['tool']}({c['args']})")
    if step.get("content_excerpt"):
        parts.append(f"  -> answers: {step['content_excerpt'][:240]!r}")
    return "\n".join(parts)


def task_digest(task: dict, trace_summary: str | None = None) -> str:
    lines = [
        f"## task `{task['id']}` input={task['input']!r} passed={task['passed']}",
        f"checks: {json.dumps(task['checks'])}",
        f"tokens={task['total_tokens']} steps={task['n_steps']} tool_errors={task['tool_errors']} latency={task['latency_s']}s",
    ]
    if task.get("failures"):
        lines.append("failures:\n" + "\n".join(f"- {f}" for f in task["failures"]))
    if task.get("error"):
        lines.append(f"exception: {task['error']}")
    lines.append("timeline:\n" + "\n".join(_step_line(s) for s in task.get("steps", [])))
    if trace_summary:
        lines.append(f"neatlogs trace {task.get('trace_id')}:\n{trace_summary}")
    return "\n".join(lines)


def build(results: dict, traces: "NeatlogsTraces | None" = None) -> str:
    """Evidence for the failing tasks (worst first), plus the run summary."""
    tasks = sorted(results["tasks"], key=lambda t: (t["passed"], -len(t["failures"]), -t["total_tokens"]))
    failing = [t for t in tasks if not t["passed"]][:MAX_TASKS]
    chunks = [f"# eval summary\n{json.dumps(results['summary'])}"]
    for task in failing:
        summary = traces.summarize(task.get("trace_id")) if traces else None
        chunks.append(task_digest(task, summary))
    passing = [t["id"] for t in tasks if t["passed"]]
    if passing:
        chunks.append(f"passing tasks (do not regress these): {passing}")
    return "\n\n".join(chunks)


class NeatlogsTraces:
    """Reads traces back from neatlogs with the `neatlogs` CLI (OAuth login required).

    Enabled when the CLI is on PATH and NEATLOGS_CLI_PROJECT is set. Every call is
    best-effort: Pitstop falls back to its own run telemetry if a read fails.
    """

    def __init__(self, project: str | None = None, host: str | None = None) -> None:
        self.project = project or os.environ.get("NEATLOGS_CLI_PROJECT")
        self.host = host or os.environ.get("NEATLOGS_CLI_HOST")
        self.exe = shutil.which("neatlogs")
        self.reads = 0
        self.failures: list[str] = []

    @property
    def enabled(self) -> bool:
        return bool(self.exe and self.project)

    def _cli(self, *args: str):
        cmd = [self.exe]
        if self.host:
            cmd += ["--host", self.host]
        cmd += ["--project", self.project, *args, "--json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[:300] or f"exit {proc.returncode}")
        return json.loads(proc.stdout)

    def spans(self, trace_id: str) -> list[dict]:
        data = self._cli("traces", "spans", "list", trace_id, "--limit", "100")
        self.reads += 1
        if isinstance(data, dict):
            for key in ("spans", "items", "data", "results"):
                if isinstance(data.get(key), list):
                    return data[key]
        return data if isinstance(data, list) else []

    def summarize(self, trace_id: str | None) -> str | None:
        if not (self.enabled and trace_id):
            return None
        try:
            spans = self.spans(trace_id)
        except Exception as exc:
            self.failures.append(f"{trace_id}: {exc}")
            return None
        lines = []
        for span in spans[:60]:
            name = _pick(span, "name", "span_name", "spanName") or "?"
            kind = _pick(span, "kind", "span_kind", "spanKind", "type") or ""
            status = _pick(span, "status", "status_code", "statusCode") or ""
            dur = _pick(span, "duration_ms", "durationMs", "latency_ms", "duration")
            tokens = _pick(span, "total_tokens", "totalTokens", "tokens")
            err = _pick(span, "error", "error_message", "exception", "status_message")
            bits = [f"{kind} {name}".strip(), f"status={status}" if status else "", f"dur={dur}" if dur else "",
                    f"tokens={tokens}" if tokens else "", f"error={str(err)[:160]}" if err else ""]
            lines.append("- " + " ".join(b for b in bits if b))
        return "\n".join(lines) or None


def _pick(d: dict, *keys):
    for key in keys:
        if key in d and d[key] not in (None, "", {}):
            value = d[key]
            return value if not isinstance(value, dict) else json.dumps(value)[:120]
        attrs = d.get("attributes") or {}
        if key in attrs and attrs[key] not in (None, ""):
            return attrs[key]
    return None
