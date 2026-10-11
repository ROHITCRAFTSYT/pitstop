"""Turn eval results and neatlogs traces into compact evidence a model can reason over."""

from __future__ import annotations

import json
import os
import time

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


def build(results: dict, traces: NeatlogsTraces | None = None) -> str:
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
    """Reads traces back from neatlogs with the project API key.

    Uses the same read path as ``neatlogs doctor --probe``. Each read returns the
    trace's spans (inputs, outputs, errors, tokens) plus neatlogs' own failure
    detections. Every call is best-effort: Pitstop falls back to its own run
    telemetry when a trace isn't readable yet.
    """

    def __init__(self, api_key: str | None = None, endpoint: str | None = None, wait_s: float = 45.0) -> None:
        self.api_key = api_key or os.environ.get("NEATLOGS_API_KEY")
        self.endpoint = (endpoint or os.environ.get("NEATLOGS_ENDPOINT") or "https://ingest.neatlogs.com").rstrip("/")
        self.wait_s = wait_s
        self.reads = 0
        self.detections = 0
        self.failures: list[str] = []

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def get(self, trace_id: str) -> dict:
        import httpx

        deadline = time.monotonic() + self.wait_s
        while True:
            r = httpx.get(f"{self.endpoint}/api/traces/v3/{trace_id}", headers={"x-api-key": self.api_key}, timeout=20)
            ready = r.status_code == 200 and r.json().get("spans")
            if ready or time.monotonic() > deadline or r.status_code in (401, 403):
                break
            time.sleep(3)
        r.raise_for_status()
        self.reads += 1
        return r.json()

    def summarize(self, trace_id: str | None) -> str | None:
        if not (self.enabled and trace_id):
            return None
        try:
            trace = self.get(trace_id)
        except Exception as exc:
            self.failures.append(f"{trace_id}: {exc}")
            return None
        lines = [
            f"trace: {trace.get('spanCount')} spans, {trace.get('llmCalls')} llm calls, {trace.get('toolCalls')} tool calls, "
            f"{trace.get('errorCount')} errors, {trace.get('totalTokensUsed')} tokens, latency {trace.get('latency')}ms"
        ]
        detections = list(trace.get("detections") or []) + list(trace.get("traceDetections") or [])
        for span in trace.get("spans") or []:
            detections += span.get("detections") or []
        self.detections += len(detections)
        for det in detections[:8]:
            lines.append(f"neatlogs detection: {json.dumps(det)[:300]}")
        spans = sorted(trace.get("spans") or [], key=lambda s: s.get("createdAt") or "")
        for span in spans[:40]:
            data = span.get("data") or {}
            bits = [
                f"{span.get('node_type', '')} {span.get('node_name', '')}".strip(),
                f"status={span.get('status')}" if span.get("status") else "",
                f"{data.get('duration_ms')}ms" if data.get("duration_ms") else "",
                f"tokens={data.get('total_tokens')}" if data.get("total_tokens") else "",
                f"input={str(data.get('input_value'))[:120]!r}" if data.get("tool_name") and data.get("input_value") else "",
                f"output_chars={len(str(data.get('output_value') or ''))}" if data.get("output_value") else "",
                f"error={data.get('error_type')}: {str(data.get('error_message'))[:160]}" if data.get("error_message") else "",
            ]
            lines.append("- " + " ".join(b for b in bits if b))
        return "\n".join(lines)
