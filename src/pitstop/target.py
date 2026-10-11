"""The agent repo Pitstop works on: config, eval/test runs, edits and git."""

from __future__ import annotations

import fnmatch
import json
import os
import pathlib
import py_compile
import subprocess
import sys
import tomllib
from dataclasses import dataclass


@dataclass
class Edit:
    file: str
    search: str
    replace: str


class EditError(ValueError):
    pass


class Target:
    def __init__(self, root: str | os.PathLike, model: str, python: str | None = None) -> None:
        self.root = pathlib.Path(root).resolve()
        config = tomllib.loads((self.root / "pitstop.toml").read_text(encoding="utf-8"))["target"]
        self.name = config["name"]
        self.description = config.get("description", "")
        self.eval_cmd = config["eval_cmd"]
        self.test_cmd = config.get("test_cmd")
        self.editable = config["editable"]
        self.context = config.get("context", [])
        self.model = model
        self.python = python or sys.executable
        self.work = self.root / ".pitstop"
        self.work.mkdir(exist_ok=True)

    # -- commands ---------------------------------------------------------
    def _expand(self, cmd: list[str], **extra) -> list[str]:
        values = {"python": self.python, "model": self.model, **extra}
        return [part.format(**values) for part in cmd]

    def _run(self, cmd: list[str], env: dict | None = None, timeout: int = 1800) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd, cwd=self.root, env={**os.environ, **(env or {})}, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )

    def evaluate(self, run_id: str, variant: str) -> dict:
        out = self.work / "runs" / run_id / f"{variant}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        proc = self._run(
            self._expand(self.eval_cmd, out=str(out)),
            env={"PITSTOP_RUN_ID": run_id, "PITSTOP_VARIANT": variant, "PYTHONIOENCODING": "utf-8"},
        )
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"eval command failed ({proc.returncode}):\n{proc.stderr[-3000:]}")
        results = json.loads(out.read_text(encoding="utf-8"))
        results["path"] = str(out)
        return results

    def run_tests(self) -> tuple[bool, str]:
        if not self.test_cmd:
            return True, "no test command configured"
        proc = self._run(self._expand(self.test_cmd), timeout=600)
        return proc.returncode == 0, (proc.stdout + proc.stderr)[-4000:]

    # -- files ------------------------------------------------------------
    def is_editable(self, rel: str) -> bool:
        rel = rel.replace("\\", "/")
        return any(fnmatch.fnmatch(rel, pattern) for pattern in self.editable)

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def source_bundle(self, include_context: bool = True) -> str:
        files = list(self.editable) + (list(self.context) if include_context else [])
        parts = []
        for rel in files:
            path = self.root / rel
            if path.exists():
                tag = "EDITABLE" if self.is_editable(rel) else "READ-ONLY"
                parts.append(f"### {rel} ({tag})\n```\n{path.read_text(encoding='utf-8')}\n```")
        return "\n\n".join(parts)

    def apply(self, edits: list[Edit]) -> list[str]:
        """Apply search/replace edits atomically. Raises EditError and leaves files untouched on any problem."""
        staged: dict[str, str] = {}
        for edit in edits:
            rel = edit.file.replace("\\", "/")
            if not self.is_editable(rel):
                raise EditError(f"{rel} is not editable (allowed: {', '.join(self.editable)})")
            text = staged.get(rel, self.read(rel))
            count = text.count(edit.search)
            if count != 1:
                raise EditError(
                    f"search block for {rel} matched {count} times; it must match exactly once. "
                    f"Block was:\n{edit.search[:500]}"
                )
            staged[rel] = text.replace(edit.search, edit.replace, 1)
        backups = {rel: self.read(rel) for rel in staged}
        for rel, text in staged.items():
            (self.root / rel).write_text(text, encoding="utf-8", newline="")
        try:
            for rel in staged:
                if rel.endswith(".py"):
                    py_compile.compile(str(self.root / rel), doraise=True)
        except py_compile.PyCompileError as exc:
            for rel, text in backups.items():
                (self.root / rel).write_text(text, encoding="utf-8", newline="")
            raise EditError(f"edit produced invalid Python: {exc.msg}") from exc
        return sorted(staged)

    # -- git --------------------------------------------------------------
    def git(self, *args: str) -> str:
        proc = self._run(["git", *args], timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
        return proc.stdout.strip()

    def ensure_clean(self) -> None:
        dirty = [line for line in self.git("status", "--porcelain").splitlines() if ".pitstop" not in line]
        if dirty:
            raise RuntimeError("target has uncommitted changes:\n" + "\n".join(dirty))

    def start_branch(self, run_id: str) -> str:
        branch = f"pitstop/{run_id}"
        self.git("checkout", "-b", branch)
        return branch

    def diff(self) -> str:
        return self.git("diff")

    def revert(self) -> None:
        self.git("checkout", "--", *self.editable_existing())

    def editable_existing(self) -> list[str]:
        return [rel for rel in self.editable if (self.root / rel).exists()]

    def commit(self, message: str) -> str:
        self.git("add", *self.editable_existing())
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")
