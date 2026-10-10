# Scout's seeded faults (for reviewers)

Pitstop never sees this file. It only gets the eval evidence, the neatlogs
traces and the source. These are the faults Scout v0 ships with, all of them
common in real agents:

| # | Fault | Where | Symptom in traces |
|---|---|---|---|
| 1 | Final answer parsed with bare `json.loads`; models often wrap JSON in a markdown fence | `scout/agent.py` | every task: `JSONDecodeError` on the last step |
| 2 | User input (`https://www.notion.so/`, `www.postman.com`) passed to lookups as-is | `scout/tools.py` | `company_lookup` → `ERROR: NotFound`, retries, invented answer |
| 3 | `people_search` returns full raw profiles (employment history, posts, skills) into context | `scout/tools.py` | ~25k-char tool result; prompt tokens jump on every later step; token budget blown |
| 4 | System prompt says "never leave a field empty or null" | `scout/prompts.py` | zerodha.com has no funding data, so the model invents a number |

How much each fault shows up depends on the model under test. A careful model
may normalise URLs itself, for example. Pitstop works from whatever actually
fails in the traces.
