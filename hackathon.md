# hackathon.md — neatHack 2026 build log

## Project
- **Name:** Pitstop
- **Purpose:** An autonomous pit crew for AI agents: it reads an agent's neatlogs traces, finds root causes, patches the code, and keeps a fix only when before/after evals prove it helped.
- **Problem:** Debugging agents is slow. You read traces, guess, patch, re-run, compare by hand. Pitstop runs that loop itself, with guardrails and a budget.

## Team
- 4'feetus (team leader: Rohit Madhavan, GitHub @ROHITCRAFTSYT)

## Stack
- Python 3.12, OpenAI SDK against the hackathon LiteLLM proxy (`claude-haiku`, `claude-sonnet-4.6`)
- neatlogs SDK (`wrap`, `span`, `log`, `identify`) + `neatlogs-cli` 0.2.0 for trace read-back
- Entire CLI 0.11.4 (Claude Code hooks, checkpoints)
- Crustdata (Scout's live data source)
- cfo.ai (business plan)

## Build log

### 2026-10-10 (Sat), evening IST
- Read the published rules: one track ("build an agent that works"), judging = agent 30 / sponsor tools 25 / demo 20 / building in public 15 / usefulness 10. Submission window Oct 12 7:00–11:55 PM IST.
- Installed Entire CLI 0.11.4 (Windows installer, checksum verified), `neatlogs-cli` 0.2.0, `neatlogs` 1.4.26.
- Built **Scout**, the patient agent (Crustdata-shaped fixture backend + live Crustdata backend), and its eval harness. The harness meters model calls itself, so evidence doesn't depend on agent code.
- Built **Pitstop**: evidence builder (local timeline + neatlogs CLI read-back), diagnose/patch roles, atomic search/replace edits limited to `editable` files, unit-test gate, before/after compare, git commit/revert, USD budget ledger, markdown/JSON report.
- Offline end-to-end tests (scripted models): Scout 0/6 → 6/6 over 4 accepted fixes; tokens 35,672 → 10,138. Covers patch repair, blocked eval edits, rejected no-op patches with revert, and budget stop. `pytest -q`: 4 passed.
- Design decision: the accept rule first used a token guard that rejected the URL fix, because fixing it let more runs reach the bloated `people_search` and tokens went up. Switched to net checks passing (token budget is itself a check). This is the kind of trade-off the tool has to handle.

### Pending
- [ ] LiteLLM key (team leader verifies check-in email) → first real run on `claude-haiku`
- [ ] neatlogs project + API key → traces in the dashboard; `neatlogs auth login` for read-back
- [ ] `entire login` + GitHub App on the repo → checkpoint link + ID
- [ ] cfo.ai business plan
- [ ] Before/after trace pair and a failure-recovery trace for the submission
- [ ] Demo video, #neatHack posts

## Demo
_Pending._

## Known limitations and next steps
- Read-back depends on `neatlogs-cli` OAuth. Without it, Pitstop uses its own run telemetry.
- One fix per attempt, applied serially. Parallel hypothesis testing in worktrees is next.
- Evals are nondeterministic with real models; temperature 0 only partly helps. Repeat-runs for significance is next.

## Submission
Confirmed requirements (from neatlogs.com/hackathon): public repo with commits during the hackathon; demo video covering the agent + neatlogs + Entire + cfo.ai; cfo.ai business plan; #neatHack public posts; before/after run pair; failure-recovery run; Entire checkpoint link + ID. Submit by quoting the official neatlogs post on X with team, project, repo, demo.
