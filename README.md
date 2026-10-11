# Pitstop

**An autonomous pit crew for AI agents.** Point Pitstop at an agent repo. It runs
the agent's evals, reads the neatlogs traces of the failing runs, works out the
root cause, patches the code, re-runs the evals, and keeps the patch only if the
numbers improve. Each accepted fix lands as its own git commit with before/after
metrics and trace ids. Patches that don't help are reverted.

Built for [neatHack](https://neatlogs.com/hackathon) (Oct 10–12, 2026) by team **4'feetus**.

## For judges: the 60-second version

**What it is.** An agent that fixes other AI agents. It reads their neatlogs traces, finds
the faulty code with Entire Graph, patches it, re-runs the evals, and keeps a fix only when
the numbers prove it helped. The result arrives as a pull request.

**Proof on two different agents** (real runs on the hackathon LiteLLM models: agent under
test `claude-haiku`, Pitstop `claude-sonnet-4.6`):

| Agent | Kind of bugs | Before | After | Tokens | Pitstop's cost | Report |
|---|---|---|---|---|---|---|
| **Scout** (company research) | fenced JSON, context bloat, prompt forcing invented numbers | 0/6 | **6/6** | −72% | $0.21 | [report](reports/pitstop-1010-2320-db0d.md) |
| **Triage** (support routing) | tool schema ≠ signature, broken KB search, prompt out of step with policy | 0/6 | **6/6** | −31%, tool errors 11 → 0 | $0.29 | [report](reports/pitstop-1011-2011-7532.md) |

- **A real PR, opened by Pitstop:** [ROHITCRAFTSYT/pitstop-demo-triage#1](https://github.com/ROHITCRAFTSYT/pitstop-demo-triage/pull/1).
  Three commits; the description carries the root cause, trace evidence and before/after numbers.
- **Failure recovery:** patches that don't apply get one repair; patches that fail tests or don't
  move the numbers are reverted ([nova-pro run](reports/pitstop-1010-2326-c7f5.md): 4 rejected, 1 kept).
  A patch identical to a rejected one isn't re-tested ([run](reports/pitstop-1010-2333-e12a.md)).
- **It won't game the evals:** evals and data are read-only to it, and a fix that breaks a passing
  task is rejected. On an early Triage run ([report](reports/pitstop-1011-2004-41e9.md)) every prompt
  fix for one ticket broke another, because our policy text contradicted itself. Pitstop refused all
  of them. It now **escalates to a human** when fixes keep trading the same tasks, and we fixed the
  policy wording.
- **Sponsor tools, used inside the agent:** neatlogs traces are its evidence (read back through the
  trace API, detections included), Entire Graph localizes the bug, and cfo.ai's Ari planned the
  business ([live model](https://cfo.ai/s/W2RB_otvpzPIaBn6)). Screenshots: [docs/evidence/](docs/evidence/).
  Entire checkpoint: [`01M4KBB7SNC5AY5QCBG39ZXGMS`](https://entire.io/gh/ROHITCRAFTSYT/pitstop/commit/7e08edba996ee741b17848e3abad7e534df54c5c).
- **Demo video (2:18, narrated):** [on X](https://x.com/6easap/status/2109287232049946961).
- **Try it without any keys:** `pip install -e . && pytest -q` runs full offline pit stops with
  scripted models. CI runs lint and tests on Linux and Windows, Python 3.11 to 3.13.

### Scout, round by round

1. **Fenced JSON.** Every neatlogs trace ended in `scout.research status=ERROR JSONDecodeError`; the
   timelines showed answers starting with a markdown fence. Pitstop stripped fences before parsing (+19 checks).
2. **Context bloat.** `people_search` returned ~50k chars of full profiles. Pitstop trimmed it to name/title (0 → 5 tasks).
3. **Invented numbers.** The prompt said "never leave a field null", so the model filled zerodha.com's
   missing funding with 0. Pitstop allowed null for unknown values (5 → 6).

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

## The patients: Scout and Triage

[`patients/scout`](patients/scout) is a small but real tool-using research agent:
company website in, JSON brief out (headcount, funding, founding year, HQ,
leaders), built on Crustdata company and people data. Its eval checks that the
brief parses, names the right company, matches the data source number for
number (no invented values), lists real people, and stays within a token budget.

Scout ships with the faults real agents ship with. Pitstop isn't told what they are.

[`patients/triage`](patients/triage) is a support-ticket router: it looks up the customer, searches a
knowledge base and returns queue, priority, article and reply, checked against `triage/policy.py`.
Its faults are a different class: a tool whose declared schema doesn't match its Python signature,
a search that only matches whole strings, and a prompt that contradicts the policy.

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate      # or source .venv/bin/activate
pip install -e .
cp .env.example .env                                 # add LITELLM_API_KEY and NEATLOGS_API_KEY
pitstop doctor --ping
pitstop init-demo                                    # copies Scout into sandbox/scout (or --patient triage)
pitstop eval                                         # baseline
pitstop heal --rounds 4 --budget 1.50                # the pit stop (add --open-pr to get a GitHub PR)
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
| **Crustdata** | Scout's data model mirrors Crustdata's company and people records. The live backend (`SCOUT_DATA=live`) is written but untested; all runs use the offline fixtures. |
| **LiteLLM (hackathon proxy)** | All model calls: `claude-haiku` for Scout, `claude-sonnet-4.6` for Pitstop. |

## Layout

```
src/pitstop/      cli · heal loop · diagnose/patch crew · evidence (neatlogs read-back) · graph (Entire) · target (edits, git) · report · github (PRs)
patients/         two patient agents (scout, triage) with evals, fixtures and tests
tests/            offline end-to-end pit stops with scripted models
reports/          reports from real runs
hackathon.md      build log
```

MIT licensed.
