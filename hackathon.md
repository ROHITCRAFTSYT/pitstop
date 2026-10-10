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
- Entire CLI 0.11.4 (Claude Code hooks, checkpoints) + entire-graph 0.4.0 (code localisation inside Pitstop)
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

- Repo published at https://github.com/ROHITCRAFTSYT/pitstop; CI (offline pit stop) green. Attached the Claude Code build session to Entire as a checkpoint (hooks were installed mid-session, so it was attached by hand).

### 2026-10-10 (Sat), late evening IST
- neatlogs project connected. `python -m neatlogs doctor --probe`: all 8 checks pass (TRACE_VISIBLE, TRACE_FINALIZED, hierarchy, attributes, I/O, metadata, tokens).
- Bug found from the first traced run: every Scout trace id was `None`. neatlogs runs its tracer provider in isolated mode, so the OTel global current span isn't the neatlogs span. Fixed by resolving the span through neatlogs' active context.
- Switched trace read-back from `neatlogs-cli` (needs OAuth) to the trace API with the project key, the same path the doctor probe uses. Pitstop now gets spans, errors, tokens and neatlogs detections per failing task. First read-back of the `notion` task showed exactly the URL fault: two `company_lookup` spans with `NotFound ... 'https://www.notion.so/'`, then a `JSONDecodeError` on `scout.research`.

- `entire login` done; checkpoint `01M4KBB7SNC5AY5QCBG39ZXGMS` is publicly viewable on entire.io.
- Installed Entire Graph (`entire plugin install graph`, v0.4.0) and ran `entire graph init-agents` (AGENTS.md, CLAUDE.md, .entire/graph-agent.md).
- Added Entire Graph to Pitstop itself: a localize step turns each failure signal into an `entire graph search` and keeps only hits in editable files. On the offline baseline it points at `scout/agent.py:43` (the bare `json.loads`) and `scout/tools.py` `company_lookup` (the NotFound errors). The first attempt queried with raw eval failure text and every top hit was in the read-only eval harness, so queries now come from trace signals instead.

### 2026-10-10 (Sat), ~11:20 PM IST: first real run
- Got the team LiteLLM key (verified via the models page form), and ran `pitstop doctor --ping` successfully.
- Real baseline, Scout on `claude-haiku`: 0/6 pass, 58,879 tokens, $0.0697. It differs from the scripted run: Haiku normalises URLs itself, so that seeded fault never fires. The fence and bloat faults do.
- Real pit stop `1010-2320-db0d` (Pitstop on `claude-sonnet-4.6`, budget $1.50): **0/6 → 6/6, 58,879 → 16,302 tokens (-72%), $0.0697 → $0.0251 per eval run**, in 3 rounds with 3 accepted fixes and no rejections. Pitstop's own spend: $0.2122 over 7 calls. neatlogs trace reads: 9. Entire Graph searches: 7. Report: `reports/pitstop-1010-2320-db0d.md`.
- Round 1 shows why the accept rule counts checks rather than tasks. Fixing the fence made tokens go *up* (58,879 → 84,935), because the parsed briefs now exposed the people bloat, and still 0 tasks passed. Checks went 4 → 23, so it was kept; round 2 then cut the bloat.
- Evidence the diagnosis cited came straight from neatlogs read-back: `agent_action scout.research status=ERROR error=json.decoder.JSONDecodeError` on all tasks.

### Pending
- [x] LiteLLM key → first real run on `claude-haiku` (0/6 → 6/6)
- [x] neatlogs project + API key → traces in the dashboard, read-back working
- [x] `entire login` → checkpoint link + ID (https://entire.io/gh/ROHITCRAFTSYT/pitstop/commit/7e08edba996ee741b17848e3abad7e534df54c5c)
- [ ] cfo.ai business plan
- [x] Before/after trace pair (baseline `4f00c2ed…` vs final `3a6ac2bc…`, stripe task)
- [ ] A real failure-recovery trace (rejected or repaired patch on a real model)
- [ ] Demo video, #neatHack posts

## Demo
_Pending._

## Known limitations and next steps
- If a trace isn't finalized within ~45s, Pitstop falls back to its own run telemetry for that task.
- One fix per attempt, applied serially. Parallel hypothesis testing in worktrees is next.
- Evals are nondeterministic with real models; temperature 0 only partly helps. Repeat-runs for significance is next.

## Submission
Confirmed requirements (from neatlogs.com/hackathon): public repo with commits during the hackathon; demo video covering the agent + neatlogs + Entire + cfo.ai; cfo.ai business plan; #neatHack public posts; before/after run pair; failure-recovery run; Entire checkpoint link + ID. Submit by quoting the official neatlogs post on X with team, project, repo, demo.
