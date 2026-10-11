"""Code localisation with Entire Graph (`entire graph search`)."""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess

import neatlogs

MAX_QUERIES = 4
MAX_CHARS = 2000
_HIT = re.compile(r"^\d+\.\s+(\S+?):\d+")


def queries_for(results: dict) -> list[str]:
    """Turn the failure signals of an eval run into plain-language code searches."""
    queries: list[str] = []
    errored_tools: set[str] = set()

    def add(q: str) -> None:
        if q not in queries:
            queries.append(q)

    for task in results["tasks"]:
        if task.get("error"):
            add(f"agent loop that raises {task['error'].split(':')[0]} when handling the model's final answer")
        for step in task.get("steps", []):
            for r in step.get("tool_results_in", []):
                if r["error"] and r["tool"] not in errored_tools:
                    errored_tools.add(r["tool"])
                    add(f"{r['tool']} tool implementation that fails with: {r['excerpt'][:120]}")
                elif r["chars"] > 8000:
                    add(f"{r['tool']} tool that returns large results into the model context")
        for failure in task["failures"]:
            if failure.startswith("hallucinated") or "data source says" in failure:
                add("system prompt rules for filling headcount, funding and founded year fields")
            elif "tokens, budget" in failure:
                add("tool output added to the conversation messages on every step")
    return queries


class EntireGraph:
    def __init__(self, repo, editable: list[str] | None = None) -> None:
        self.repo = str(repo)
        self.editable = editable or ["*"]
        self.exe = shutil.which("entire")
        self.searches = 0
        self.failures: list[str] = []

    @property
    def enabled(self) -> bool:
        return bool(self.exe)

    def search(self, query: str, top_k: int = 6) -> str | None:
        cmd = [self.exe, "graph", "search", "--query", query, "--repo", self.repo,
               "--format", "agent", "--top-k", str(top_k), "--profile", "full"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.failures.append(str(exc))
            return None
        if proc.returncode != 0:
            self.failures.append(proc.stderr.strip()[:300])
            return None
        self.searches += 1
        return self._editable_hits(proc.stdout)

    def _editable_hits(self, output: str) -> str | None:
        """Keep only ranked hits in files Pitstop may edit."""
        kept, keep = [], False
        for line in output.splitlines():
            m = _HIT.match(line)
            if m:
                keep = any(fnmatch.fnmatch(m.group(1).replace("\\", "/"), p) for p in self.editable)
            elif line and not line.startswith((" ", "\t")):
                keep = False
            if keep:
                kept.append(line)
        return "\n".join(kept)[:MAX_CHARS] or None

    @neatlogs.span(kind="RETRIEVER", name="pitstop.localize")
    def localize(self, results: dict) -> str | None:
        if not self.enabled:
            return None
        blocks = []
        for query in queries_for(results)[:MAX_QUERIES]:
            hits = self.search(query)
            if hits:
                blocks.append(f"### entire graph search: {query}\n{hits}")
        return "\n\n".join(blocks) or None
