"""pitstop: an autonomous pit crew for AI agents.

    pitstop init-demo                 # copy the Scout patient into sandbox/scout as a git repo
    pitstop eval  --target sandbox/scout
    pitstop heal  --target sandbox/scout --rounds 4 --budget 1.50
    pitstop doctor
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

ROOT = pathlib.Path(__file__).resolve().parents[2]
console = Console(highlight=False)


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        load_dotenv()
    except ImportError:
        pass


def _init_neatlogs(run_tag: str | None = None) -> bool:
    if not os.environ.get("NEATLOGS_API_KEY"):
        return False
    import neatlogs

    tags = ["pitstop"] + ([f"run:{run_tag}"] if run_tag else [])
    neatlogs.init(workflow_name="pitstop", tags=tags)
    return True


def _summary_table(title: str, results: dict) -> Table:
    table = Table(title=title, title_justify="left")
    for col in ("task", "pass", "tokens", "steps", "tool err", "failures"):
        table.add_column(col)
    for t in results["tasks"]:
        table.add_row(
            t["id"], "[green]yes[/]" if t["passed"] else "[red]no[/]", str(t["total_tokens"]), str(t["n_steps"]),
            str(t["tool_errors"]), "; ".join(t["failures"])[:110],
        )
    s = results["summary"]
    table.caption = (
        f"{s['passed']}/{s['tasks']} pass · {s['total_tokens']} tokens · ${s['cost_usd']:.4f} · "
        f"{s['tool_errors']} tool errors · model {s['model']} · data {s['data']}"
    )
    return table


class Narrator:
    """Prints the pit stop as it happens."""

    def __call__(self, event: str, **d) -> None:
        handler = getattr(self, f"on_{event}", None)
        if handler:
            handler(**d)

    def on_start(self, run):
        console.print(Panel(f"Pit stop [bold]{run.run_id}[/] on [bold]{run.target}[/] · branch {run.branch}", style="cyan"))

    def on_eval_start(self, variant):
        console.print(f"[dim]running evals ({variant})...[/]")

    def on_eval_done(self, variant, results):
        console.print(_summary_table(f"evals: {variant}", results))

    def on_diagnose_start(self, round):
        console.rule(f"round {round}: reading traces and diagnosing")

    def on_diagnosed(self, round, hypotheses):
        for h in hypotheses:
            console.print(f"  [yellow]{h.get('id')}[/] {h.get('title')} [dim](confidence {h.get('confidence')})[/]")
            console.print(f"     [dim]{h.get('root_cause', '')[:220]}[/]")

    def on_localized(self, round, searches):
        console.print(f"  [dim]Entire Graph: localized failures to candidate fix sites ({searches} searches so far)[/]")

    def on_attempt_start(self, attempt):
        console.print(f"[bold]trying:[/] {attempt['title']}")

    def on_patch_failed(self, attempt, error, will_retry):
        console.print(f"  [red]patch did not apply[/]: {error.splitlines()[0][:160]}" + (" → retrying" if will_retry else ""))

    def on_duplicate_patch(self, attempt, will_retry):
        console.print("  [red]same patch as a rejected attempt[/], not re-testing" + (" → asking for a different fix" if will_retry else ""))

    def on_tests_failed(self, attempt, output, will_retry):
        console.print("  [red]tests failed after patch[/]" + (" → retrying" if will_retry else ""))

    def on_patched(self, attempt):
        console.print(f"  patched {', '.join(attempt['files'])}")
        console.print(f"[dim]{attempt['diff'][:1500]}[/]")

    def on_attempt_done(self, attempt):
        color = "green" if attempt["outcome"] == "accepted" else "red"
        console.print(f"  [{color}]{attempt['outcome'].upper()}[/]: {attempt['reason']}")

    def on_stuck(self, round):
        console.print("  [yellow]no hypothesis improved the agent this round[/]")

    def on_finish(self, run):
        b, f = run.baseline["summary"], run.final["summary"]
        console.print(Panel(
            f"{run.stopped}\npassing {b['passed']}/{b['tasks']} → {f['passed']}/{f['tasks']} · "
            f"tokens {b['total_tokens']} → {f['total_tokens']} · tool errors {b['tool_errors']} → {f['tool_errors']}",
            title="pit stop finished", style="green" if f["passed"] > b["passed"] else "yellow",
        ))


def cmd_init_demo(args) -> int:
    src = ROOT / "patients" / "scout"
    dest = pathlib.Path(args.dest).resolve()
    if dest.exists():
        if not args.force:
            console.print(f"[red]{dest} exists[/] (use --force to replace)")
            return 1
        shutil.rmtree(dest, onerror=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", ".pitstop", ".pytest_cache"))
    (dest / ".gitignore").write_text(".pitstop/\n__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "config", "core.autocrlf", "false"], ["git", "add", "-A"],
                ["git", "-c", "user.name=Scout", "-c", "user.email=scout@example.invalid", "commit", "-q", "-m", "Scout v0"]):
        subprocess.run(cmd, cwd=dest, check=True)
    console.print(f"Scout patient ready at [bold]{dest}[/]")
    return 0


def cmd_eval(args) -> int:
    from pitstop.target import Target

    _load_env()
    target = Target(args.target, model=args.model)
    results = target.evaluate(args.run_id or "manual", args.variant)
    console.print(_summary_table(f"evals: {args.variant}", results))
    return 0


def cmd_heal(args) -> int:
    from pitstop.evidence import NeatlogsTraces
    from pitstop.graph import EntireGraph
    from pitstop.heal import heal
    from pitstop.llm import LLM, Ledger
    from pitstop.report import write
    from pitstop.target import Target

    _load_env()
    traced = _init_neatlogs()
    if not os.environ.get("LITELLM_API_KEY"):
        console.print("[red]LITELLM_API_KEY is not set[/] (see .env.example)")
        return 2
    target = Target(args.target, model=args.model)
    ledger = Ledger(budget_usd=args.budget)
    llm = LLM(args.pitstop_model, ledger)
    traces = NeatlogsTraces()
    graph = EntireGraph(target.root, target.editable)
    console.print(
        f"neatlogs export: {'on' if traced else 'off'} · trace read-back: {'on' if traces.enabled else 'off (local telemetry)'} · "
        f"Entire Graph: {'on' if graph.enabled else 'off'} · budget ${args.budget:.2f}"
    )
    run = heal(target, llm, max_rounds=args.rounds, tries_per_round=args.tries, traces=traces if traces.enabled else None,
               graph=graph if graph.enabled else None, emit=Narrator())
    report = write(run, ledger, pathlib.Path(args.reports), traces.reads, graph.searches)
    console.print(f"report: {report}")
    if traced:
        import neatlogs

        neatlogs.flush()
    if traces.failures:
        console.print(f"[yellow]{len(traces.failures)} neatlogs trace reads failed[/]; first: {traces.failures[0]}")
    console.print(f"neatlogs traces read back: {traces.reads} · detections seen: {traces.detections} · Entire Graph searches: {graph.searches}")
    return 0


def cmd_doctor(args) -> int:
    _load_env()
    rows = []

    def check(name, ok, detail=""):
        rows.append((name, "[green]ok[/]" if ok else "[red]missing[/]", detail))

    check("LITELLM_API_KEY", bool(os.environ.get("LITELLM_API_KEY")), "hackathon model key (team leader's check-in email)")
    check("NEATLOGS_API_KEY", bool(os.environ.get("NEATLOGS_API_KEY")), "neatlogs project key: Settings → API keys")
    check("entire CLI", bool(shutil.which("entire")), "irm https://entire.io/install.ps1 | iex")
    check("CRUSTDATA_API_KEY", bool(os.environ.get("CRUSTDATA_API_KEY")), "optional: SCOUT_DATA=live")
    table = Table(title="pitstop doctor")
    for col in ("check", "status", "notes"):
        table.add_column(col)
    for r in rows:
        table.add_row(*r)
    console.print(table)
    if os.environ.get("LITELLM_API_KEY") and args.ping:
        from pitstop.llm import LLM, Ledger

        reply = LLM(args.pitstop_model, Ledger(0.05)).json("ping", "Reply with JSON.", 'Reply {"ok": true}')
        console.print(f"LiteLLM ping ({args.pitstop_model}): {json.dumps(reply)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pitstop", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init-demo", help="copy the Scout patient into a fresh git repo")
    p.add_argument("--dest", default=str(ROOT / "sandbox" / "scout"))
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init_demo)

    for name, fn in (("eval", cmd_eval), ("heal", cmd_heal)):
        p = sub.add_parser(name)
        p.add_argument("--target", default=str(ROOT / "sandbox" / "scout"))
        p.add_argument("--model", default=os.environ.get("SCOUT_MODEL", "claude-haiku"), help="model under test")
        p.set_defaults(fn=fn)
        if name == "eval":
            p.add_argument("--variant", default="manual")
            p.add_argument("--run-id")
        else:
            p.add_argument("--pitstop-model", default=os.environ.get("PITSTOP_MODEL", "claude-sonnet-4.6"))
            p.add_argument("--rounds", type=int, default=4)
            p.add_argument("--tries", type=int, default=2, help="hypotheses to try per round")
            p.add_argument("--budget", type=float, default=1.50, help="USD cap for Pitstop's own model calls")
            p.add_argument("--reports", default=str(ROOT / "reports"))

    p = sub.add_parser("doctor")
    p.add_argument("--ping", action="store_true")
    p.add_argument("--pitstop-model", default=os.environ.get("PITSTOP_MODEL", "claude-sonnet-4.6"))
    p.set_defaults(fn=cmd_doctor)

    args = ap.parse_args(argv)
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
