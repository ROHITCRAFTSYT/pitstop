# Seeded faults (for reviewers)

Pitstop never sees this file. It only gets the eval evidence, the neatlogs
traces and the source. These are the faults Scout v0 ships with, all of them
common in real agents:

| # | Fault | Where | Symptom in traces |
|---|---|---|---|
| 1 | Final answer parsed with bare `json.loads`; models often wrap JSON in a markdown fence | `scout/agent.py` | every task: `JSONDecodeError` on the last step |
| 2 | User input (`https://www.notion.so/`, `www.postman.com`) passed to lookups as-is | `scout/tools.py` | `company_lookup` → `ERROR: NotFound`, retries, invented answer |
| 3 | `people_search` returns full raw profiles (employment history, posts, skills) into context | `scout/tools.py` | ~25k-char tool result; prompt tokens jump on every later step; token budget blown |
| 4 | System prompt says "never leave a field empty or null" | `scout/prompts.py` | zerodha.com has no funding data, so the model invents a number |

## Triage

| # | Fault | Where | Symptom in traces |
|---|---|---|---|
| 1 | `TOOL_SPECS` declares `lookup_customer(email)` but the function takes `customer_email` | `triage/tools.py` | every lookup → `ERROR: TypeError ... unexpected keyword argument 'email'` |
| 2 | `search_kb` only matches the whole query string against a title or tag | `triage/tools.py` | natural-language queries return `[]`, so `kb_article` is empty or guessed |
| 3 | The prompt says "P1 only when the customer says urgent" instead of following `triage/policy.py` | `triage/prompts.py` | wrong priorities for enterprise and past-due tickets |
| 4 | `MAX_STEPS = 4` leaves little room for retries after tool errors | `triage/agent.py` | occasional "no answer after 4 steps" |

How much each fault shows up depends on the model under test. A careful model
may normalise URLs itself, for example. Pitstop works from whatever actually
fails in the traces.
