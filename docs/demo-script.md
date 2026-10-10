# Pitstop demo video script (target 2:30)

Judging for the demo (20%) is "how clearly the video explains the agent and your use
of neatlogs, Entire and cfo.ai", so each of the three gets its own on-screen moment.

## Before recording

- Record at 1080p. Use OBS, or **Win+Alt+R** (Xbox Game Bar) for one window.
- Terminal: Windows Terminal, font size 16+, dark theme, about 140 columns wide.
- Open these tabs in this order:
  1. neatlogs dashboard → Traces, filtered to workflow `scout`
  2. https://entire.io/gh/ROHITCRAFTSYT/pitstop/commit/7e08edba996ee741b17848e3abad7e534df54c5c
  3. https://cfo.ai/s/W2RB_otvpzPIaBn6
  4. https://github.com/ROHITCRAFTSYT/pitstop
- Pre-record the long part. A real `pitstop heal` takes about 4 minutes. Record it once, then
  speed it up 4–6x in the edit and cut to the narration beats below.

```bash
cd D:\Hackathon\neatHack-2026\pitstop
.venv\Scripts\activate
pitstop init-demo --force
pitstop heal --model claude-haiku --rounds 4 --budget 1.50
```

## Script

| Time | Screen | Say |
|---|---|---|
| 0:00–0:12 | Title card: "Pitstop: a pit crew for AI agents" | "When an agent breaks, you read traces, guess, patch, re-run and compare by hand. Pitstop is an agent that does that loop for you, and only keeps a fix if the numbers prove it." |
| 0:12–0:30 | Terminal: `pitstop eval`, the baseline table at 0/6 | "This is Scout, a company-research agent built on Crustdata data. Six tasks, zero pass. It burns about 59 thousand tokens and parses nothing." |
| 0:30–0:45 | **neatlogs**: open a failing Scout trace and click the red `scout.research` span showing JSONDecodeError | "Every run is traced in neatlogs. Here's one failing task: the tool calls succeed, then the final step dies with a JSON decode error. Pitstop reads these same traces back through the neatlogs API." |
| 0:45–1:05 | Terminal: `pitstop heal` starts. Highlight "neatlogs export: on · trace read-back: on · Entire Graph: on" and the round-1 hypotheses | "Pitstop pulls the failing traces, then asks **Entire Graph** where in the code each failure lives. Graph points straight at line 43 of agent.py. Then it ranks root causes, each citing trace evidence." |
| 1:05–1:30 | Diff on screen, then the eval table and "ACCEPTED" (sped up through rounds 2–3) | "It patches only files the agent is allowed to edit, runs the unit tests, re-runs all six tasks and compares. Fence fix: kept. Next it finds people-search dumping 50 thousand characters into context and trims it. Then a prompt that forced the model to invent a funding number." |
| 1:30–1:42 | Final panel: 0/6 → 6/6, tokens 58,879 → 16,302 | "Six out of six. Seventy-two percent fewer tokens. Pitstop itself spent twenty-one cents." |
| 1:42–1:58 | `git log` in sandbox/scout, then the report's "Rejected attempts" section from the nova-pro run | "Every fix is its own commit with the before/after numbers. When a patch doesn't help, it's reverted. With a weaker fixer model, its own neatlogs traces showed Pitstop repeating a rejected patch, so we taught it to remember rejected diffs. That's neatlogs improving Pitstop, not just Scout." |
| 1:58–2:10 | **Entire**: checkpoint page → Sessions, then Changes. Briefly show `CLAUDE.md` pointing at `entire graph search` | "We built Pitstop with Claude Code under Entire. Sessions are captured as checkpoints on our commits, and the same Entire Graph that helps our coding agent is what Pitstop uses to localize bugs." |
| 2:10–2:25 | **cfo.ai**: shared model, Controls, then Cash and runway, then Sensitivities | "cfo.ai's Ari modelled Pitstop as a business. At $49 a repo, our ten thousand dollars runs out in month three, so we'd need about twenty-eight thousand in bridge funding. Don't price at $29; at $79 it breaks even within the year. Ari's biggest open risk is the real cost of one pit stop, which Pitstop already measures: four to twenty-one cents in our runs." |
| 2:25–2:35 | GitHub repo README | "Pitstop. Open source, reports and traces in the repo. Built at #neatHack by team 4'feetus." |

## Numbers to have on screen (from the reports)

| | Value | Source |
|---|---|---|
| Baseline → final | 0/6 → 6/6 | `reports/pitstop-1010-2320-db0d.md` |
| Tokens | 58,879 → 16,302 (-72%) | same |
| Eval cost per run | $0.0697 → $0.0251 (-64%) | same |
| Pitstop spend | $0.2122, 7 model calls | same |
| neatlogs reads / Graph searches | 9 / 12 across runs 1 and 3 | report headers |
| Before/after trace pair (stripe task) | `4f00c2edd726bf2405756cc32fd5bff8` → `3a6ac2bcdd16692d88b7e3755144d09b` | report, "Eval runs" |
| Recovery run | 4 rejected and reverted, 1 accepted | `reports/pitstop-1010-2326-c7f5.md` |
| Entire checkpoint | `01M4KBB7SNC5AY5QCBG39ZXGMS` | entire.io link above |
| cfo.ai | $47k 12-month revenue · cash out month 3 · $28.5k bridge · $79 breaks even | https://cfo.ai/s/W2RB_otvpzPIaBn6 |

## Submission post (quote the official neatlogs post on X)

> Team 4'feetus · Pitstop: an agent that fixes other AI agents from their neatlogs traces.
> Repo: https://github.com/ROHITCRAFTSYT/pitstop
> Demo: <video link>
> #neatHack
