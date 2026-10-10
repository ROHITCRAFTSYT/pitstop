# Pitstop

**An autonomous pit crew for AI agents.** Point Pitstop at an agent repo. It runs
the agent's evals, reads the neatlogs traces of the failing runs, works out the
root cause, patches the code, re-runs the evals, and keeps the patch only if the
numbers improve. Each accepted fix lands as its own git commit with before/after
metrics and trace ids. Patches that don't help are reverted.

Built for [neatHack](https://neatlogs.com/hackathon) (Oct 10–12, 2026) by team **4'feetus**.

```
pitstop heal --target sandbox/scout

 baseline   0/6 pass · 35,672 tokens · 6 tool errors
 round 1    "final answer is fenced JSON, json.loads fails"       first edit didn't apply → repaired → ACCEPTED (+17 checks)
 round 2    "URLs passed to lookups without normalising"          ACCEPTED (+3 checks; tokens rise to 63,203 as more runs reach people_search)
 round 3    "people_search dumps full profiles into context"      tried to edit the evals → blocked → repaired → ACCEPTED (0 → 5 pass)
 round 4    "prompt forces the model to invent missing numbers"   ACCEPTED (5 → 6 pass)
 final      6/6 pass · 10,138 tokens (-72%) · 0 tool errors
```
*(Offline run with scripted models, from `tests/test_heal_offline.py`. Real runs use the hackathon LiteLLM models and are linked in [`reports/`](reports/).)*

## How it works

```
            ┌──────────── evals (pitstop.toml: eval_cmd) ─────────────┐
            ▼                                                          │
  target agent ──traces──▶ neatlogs ──trace API──▶ evidence ─┬▶ DIAGNOSE (claude-sonnet-4.6)
  target repo ──entire graph search──▶ candidate fix sites ───┘
                                                                       │ ranked root-cause hypotheses
                                                                       ▼
            keep + commit ◀── ACCEPT ◀── compare ◀── evals ◀── tests ◀── PATCH (search/replace edits)
            revert        ◀── REJECT ◀──┘                     │
                                     repair once ◀── edit didn't apply / tests failed
```

1. **Evaluate.** Run the target's eval command (declared in its `pitstop.toml`).
   The harness meters every model call itself, so the agent can't hide steps.
2. **Collect evidence.** For each failing task: failed checks, a step-by-step
   timeline (tool calls, arguments, result sizes, errors, tokens per step) and
   the neatlogs spans and detections for that task's trace, read back through the neatlogs trace API.
3. **Localize.** Each failure signal (an exception, a failing tool call, an
   oversized tool result, an invented value) becomes an `entire graph search`
   over the target repo. Only hits in editable files are kept, as candidate fix sites.
4. **Diagnose.** The model returns ranked hypotheses, each citing evidence
   (task, step, failure text), and sees every earlier attempt and why it was rejected.
5. **Patch.** Minimal search/replace edits, limited to files the target marks
   `editable`. Evals and data are read-only, so the agent can't game its own tests.
   If an edit doesn't apply or the unit tests fail, the error goes back to the
   model for one repair attempt.
6. **Verify.** Re-run the evals. Accept only if more tasks pass, or more checks
   pass, or results stay equal with ≥10% fewer tokens, and no passing task
   regresses. Otherwise revert.
7. **Report.** A markdown + JSON report with the before/after table, every
   accepted diff, every rejected attempt and why, and all trace ids.

Pitstop has a hard USD budget (`--budget`) for its own model calls and stops
cleanly (reverting any half-applied patch) when it hits it.

## The patient: Scout

[`patients/scout`](patients/scout) is a small but real tool-using research agent:
company website in, JSON brief out (headcount, funding, founding year, HQ,
leaders), built on Crustdata company and people data. Its eval checks that the
brief parses, names the right company, matches the data source number for
number (no invented values), lists real people, and stays within a token budget.

Scout ships with the faults real agents ship with. Pitstop isn't told what they are.

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate      # or source .venv/bin/activate
pip install -e .
cp .env.example .env                                 # add LITELLM_API_KEY and NEATLOGS_API_KEY
pitstop doctor --ping
pitstop init-demo                                    # copies Scout into sandbox/scout as a git repo
pitstop eval                                         # baseline
pitstop heal --rounds 4 --budget 1.50                # the pit stop
```

Offline (no keys, scripted models): `pytest -q`.

### Using it on your own agent

Add a `pitstop.toml` to your agent repo:

```toml
[target]
name = "my-agent"
description = "what it does"
eval_cmd = ["{python}", "-m", "evals.run", "--out", "{out}", "--model", "{model}"]
test_cmd = ["{python}", "-m", "pytest", "-q"]
editable = ["agent/*.py", "agent/prompts.py"]
context  = ["evals/run.py"]
```

Your eval command must write JSON with a `summary` (`tasks`, `passed`,
`total_tokens`, `cost_usd`, `tool_errors`, ...) and per-task `checks`,
`failures`, `steps` and `trace_id`. See [`patients/scout/evals/run.py`](patients/scout/evals/run.py).

## Sponsor tools

| Tool | How Pitstop uses it |
|---|---|
| **neatlogs** | Every Scout run and every Pitstop step is traced (`neatlogs.wrap`, `@neatlogs.span`, `neatlogs.log`). Pitstop reads each failing trace back through the neatlogs trace API (project key: spans, errors, tokens and neatlogs' own detections) as diagnosis evidence. Before/after trace ids go in each commit and report. |
| **Entire** | Inside the agent: Pitstop uses Entire Graph (`entire graph search`) to localize each failure to candidate fix sites before diagnosing. Building the agent: the repo is Entire-enabled for Claude Code (sessions captured as checkpoints linked to commits) and Graph-enabled (`AGENTS.md`/`CLAUDE.md` point coding agents at `entire graph search`). |
| **cfo.ai** | Pricing, costs, revenue and runway plan for Pitstop as a product: [`docs/business-plan.md`](docs/business-plan.md). |
| **Crustdata** | Scout's live data source (`SCOUT_DATA=live`). |
| **LiteLLM (hackathon proxy)** | All model calls: `claude-haiku` for Scout, `claude-sonnet-4.6` for Pitstop. |

## Layout

```
src/pitstop/      cli · heal loop · diagnose/patch crew · evidence (neatlogs trace read-back) · target (edits, git) · report
patients/scout/   the patient agent, its evals, fixtures and tests
tests/            offline end-to-end pit stops with scripted models
reports/          reports from real runs
hackathon.md      build log
```

MIT licensed.
