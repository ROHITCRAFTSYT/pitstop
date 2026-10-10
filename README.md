# Pitstop

**An autonomous pit crew for AI agents.** Point Pitstop at an agent repo. It runs
the agent's evals, reads the neatlogs traces of the failing runs, works out the
root cause, patches the code, re-runs the evals, and keeps the patch only if the
numbers improve. Each accepted fix lands as its own git commit with before/after
metrics and trace ids. Patches that don't help are reverted.

Built for [neatHack](https://neatlogs.com/hackathon) (Oct 10–12, 2026) by team **4'feetus**.

**First real run** ([report](reports/pitstop-1010-2320-db0d.md)): Scout on `claude-haiku`, Pitstop on `claude-sonnet-4.6`, via the hackathon LiteLLM proxy.

| | before | after |
|---|---|---|
| tasks passing | 0/6 | **6/6** |
| tokens (6 tasks) | 58,879 | **16,302 (-72%)** |
| est. cost per eval run | $0.0697 | **$0.0251 (-64%)** |
| avg latency | 4.6 s | 3.2 s |

Three rounds, three accepted fixes, each its own commit with the evidence that justified it:

1. **Fenced JSON.** Every neatlogs trace ended in `scout.research status=ERROR JSONDecodeError`; the timelines showed answers starting with a markdown code fence. Pitstop stripped fences before parsing (+19 checks).
2. **Context bloat.** `people_search` returned ~50k chars of full profiles into context. Pitstop trimmed it to name/title (0 → 5 tasks pass).
3. **Invented numbers.** The prompt said "never leave a field null", so the model filled zerodha.com's missing funding with 0. Pitstop allowed null for unknown values (5 → 6).

Pitstop spent $0.21 (7 model calls), read 9 neatlogs traces back and ran 7 Entire Graph searches.

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
| **cfo.ai** | Ari (cfo.ai's AI CFO) built Pitstop's 12-month model: pricing, unit economics, forecast, burn, runway and 12 sensitivity scenarios. Headline: $10k runs out in month 3, ~$28.5k bridge needed at $49; don't price Team at $29; $79 breaks even within the year. [Live model](https://cfo.ai/s/W2RB_otvpzPIaBn6) · [`docs/business-plan.md`](docs/business-plan.md) |
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
