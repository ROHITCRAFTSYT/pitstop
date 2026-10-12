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

### 2026-10-10 (Sat), ~11:45 PM IST: Pitstop learns from rejections; cfo.ai plan
- Run 3 (nova-pro as the fixer): 4 rejected patches, all reverted, plus 1 accepted fix (-22% tokens). Its traces showed Pitstop repeating the *same* rejected JSON patch four rounds running, because rejected attempts were summarised by title only.
- Fix: diagnose/patch now see rejected diffs and the failures that remained, and an identical re-proposal is reverted without re-running evals. Run 4 (same setup): the guard fired 3 times and skipped those eval re-runs, but nova-pro still couldn't solve the fence bug (its patches produced invalid Python, which was rejected safely). Conclusion: fixer quality matters; Sonnet solved it first try in run 1. neatlogs detections started appearing (22 in run 4).
- cfo.ai: Ari built a 4-page model plus 12 scenarios (docs/business-plan.md). Base case: $47k 12-month revenue, cash out in month 3, $28.5k bridge needed; Team at $29 is contribution-negative; $79 breaks even within the year. Ari's top risk, the true cost of one pit stop including failed patches, is something Pitstop's ledger already measures ($0.04–$0.21 in real runs).

### 2026-10-11 (Sun), evening IST: second patient, PRs, escalation, hardening
- Reviewed the project as a judge would. Biggest risk: Pitstop had only been shown on one agent we wrote. Added **Triage**, a support-ticket router with a different class of faults (tool schema vs. signature mismatch, whole-string KB search, prompt contradicting policy).
- Triage run `1011-2004-41e9`: fixed the schema bug (0/6 → 5/6, tool errors 11 → 0), then rejected four prompt fixes in a row. Each fixed `double-charge` but broke `seats-enterprise`. Root cause was in *our* spec: the policy said enterprise tickets are P2 and also that sales enquiries are P3. Pitstop refused to trade one task for another. Added **escalation**: when consecutive fixes keep breaking the same passing tasks, Pitstop stops and reports a likely spec conflict for a human. Clarified the policy text.
- Triage run `1011-2011-7532`: **0/6 → 6/6**, tokens −31%, tool errors 11 → 0, $0.29. Found all three seeded faults; one ineffective prompt patch was rejected and reverted along the way.
- New: `pitstop heal --open-pr` / `pitstop pr` pushes the fix branch and opens a GitHub PR with the report. Real PR: https://github.com/ROHITCRAFTSYT/pitstop-demo-triage/pull/1
- Hardening: Ctrl-C reverts any half-applied patch; ruff lint; CI on Linux and Windows across Python 3.11 to 3.13; LF line endings enforced (Windows had introduced CRLF).

## Evidence

| What | Where |
|---|---|
| Second agent, 0/6 → 6/6 | [reports/pitstop-1011-2011-7532.md](reports/pitstop-1011-2011-7532.md) |
| PR opened by Pitstop | https://github.com/ROHITCRAFTSYT/pitstop-demo-triage/pull/1 |
| Refusing to trade tasks (spec conflict) | [reports/pitstop-1011-2004-41e9.md](reports/pitstop-1011-2004-41e9.md) |
| Screenshots (neatlogs, Entire, cfo.ai) | [docs/evidence/](docs/evidence/) |
| Screenshots (neatlogs, Entire, cfo.ai) | [docs/evidence/](docs/evidence/) |
| Before/after pair (stripe task) | neatlogs traces `4f00c2edd726bf2405756cc32fd5bff8` → `3a6ac2bcdd16692d88b7e3755144d09b`; [report](reports/pitstop-1010-2320-db0d.md) |
| Failure recovery | [reports/pitstop-1010-2326-c7f5.md](reports/pitstop-1010-2326-c7f5.md): 4 rejected patches reverted; [reports/pitstop-1010-2333-e12a.md](reports/pitstop-1010-2333-e12a.md): duplicate-patch guard |
| Entire checkpoint | `01M4KBB7SNC5AY5QCBG39ZXGMS`: https://entire.io/gh/ROHITCRAFTSYT/pitstop/commit/7e08edba996ee741b17848e3abad7e534df54c5c |
| Building in public (#neatHack) | Day 1: https://x.com/6easap/status/2108990075061284936 · Day 2 (narrated demo): https://x.com/6easap/status/2109287232049946961 · Day 3 (wrap-up): https://x.com/6easap/status/2109680600550650337 |
| cfo.ai plan | https://cfo.ai/s/W2RB_otvpzPIaBn6 · [docs/business-plan.md](docs/business-plan.md) |

## Demo
Narrated demo in the submission post: https://x.com/6easap/status/2109671705945972748

## Submission
Submitted 2026-10-12, ~9:45 PM IST: quote-tweet of the official launch post (tags @neatlogs @EntireHQ @arithecfo, demo video attached) plus the neatlogs.com/submission form. Submission ID 558faae8-789e-4ad9-9e76-79e964f2458b.

## Known limitations and next steps
- If a trace isn't finalized within ~45s, Pitstop falls back to its own run telemetry for that task.
- One fix per attempt, applied serially. Parallel hypothesis testing in worktrees is next.
- Evals are nondeterministic with real models; temperature 0 only partly helps. Repeat-runs for significance is next.
