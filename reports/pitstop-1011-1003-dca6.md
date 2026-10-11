# Pit stop `1011-1003-dca6` on `scout`

- Branch: `pitstop/1011-1003-dca6`
- Model under test: `claude-haiku` · data: `fixture`
- Stopped because: all tasks pass
- Pitstop's own spend: $0.1509 over 6 model calls (36565 tokens)
- neatlogs trace reads: 6 · Entire Graph searches: 7

## Before → after

| metric | before | after |
|---|---|---|
| tasks passing | 0/6 | 6/6 |
| total tokens | 58873 | 16490 (-72%) |
| est. cost (USD) | 0.0696 | 0.0257 (-63%) |
| tool errors | 0 | 0 |
| avg steps | 2.17 | 2.17 |
| avg latency (s) | 4.549 | 3.394 |

## Accepted fixes (3)

### Strip markdown code fences from model output before JSON parsing, and instruct model not to use them
Round 1 · commit `79bfba590a` · 3 more task(s) pass

**Root cause.** In agent.py, `json.loads(message.content)` is called directly on the model's final message. The model consistently wraps its JSON output in ```json ... ``` markdown fences (visible in every timeline's final answer excerpt). json.loads cannot parse a string starting with backticks, producing JSONDecodeError: Expecting value: line 1 column 1 (char 0) on every single task.

**Evidence.** zerodha step 3 answers: '```json\n{\n  "company": "Zerodha"...'; notion step 2 answers: '```json\n{\n  "company": "Notion"...'; razorpay step 2 answers: '```json\n{\n  "company": "Razorpay"...'; postman step 2 answers: '```json\n{\n  "company": "Postman"...'; All tasks: 'no usable brief: JSONDecodeError: Expecting value: line 1 column 1 (char 0)'; agent.py line 43: return json.loads(message.content)

passed 0 → 3, checks 4 → 26, tokens 58873 → 62396, tool errors 0 → 0

```diff
diff --git a/scout/agent.py b/scout/agent.py
index 98bec38..fd40bdb 100644
--- a/scout/agent.py
+++ b/scout/agent.py
@@ -39,5 +39,12 @@ def research(target: str, *, client, model: str) -> dict:
                     {"role": "tool", "tool_call_id": call.id, "content": run_tool(call.function.name, call.function.arguments)}
                 )
             continue
-        return json.loads(message.content)
+        content = message.content or ""
+        content = content.strip()
+        if content.startswith("```"):
+            # Strip markdown code fences (e.g. ```json ... ```)
+            lines = content.splitlines()
+            # Remove first line (``` or ```json) and last line (```)
+            content = "\n".join(lines[1:-1]).strip()
+        return json.loads(content)
     raise RuntimeError(f"no answer after {MAX_STEPS} steps")
diff --git a/scout/prompts.py b/scout/prompts.py
index 7245992..da07953 100644
--- a/scout/prompts.py
+++ b/scout/prompts.py
@@ -15,6 +15,7 @@ ONLY a JSON object in this shape:
 }
 
 Every field is required. Never leave a field empty or null.
-key_people should list up to 5 senior leaders."""
+key_people should list up to 5 senior leaders.
+Do NOT wrap the JSON in markdown code fences. Output raw JSON only."""
 
 USER = "Research this company: {target}"
```

### Truncate people_search results to name+title only (max 5) to stay within token budget
Round 2 · commit `d251742b97` · 2 more task(s) pass

**Root cause.** The people_search tool returns full LinkedIn-style profiles (employment history, skills, education, posts, etc.) for every person, producing ~51,000 chars per call. This inflates the prompt in step 2 to ~12,000+ tokens, pushing all three failing tasks over the 8,000-token budget. The fix is to slim the tool response to only the fields the agent actually needs (name, title) before returning it to the model.

**Evidence.** zerodha step 2: people_search returned 50956 chars, prompt=12362tok, total=13624 > 8000 budget; razorpay step 2: people_search returned 50976 chars, prompt=12467tok, total=13777 > 8000 budget; linear step 2: people_search returned 51138 chars, prompt=12361tok, total=13614 > 8000 budget; tools.py:68 people_search returns raw list[dict] from backend with full _full_profile expansion including all_employers, skills, education, recent_posts, summary, etc.

passed 3 → 5, checks 26 → 29, tokens 62396 → 14757, tool errors 0 → 0

```diff
diff --git a/scout/tools.py b/scout/tools.py
index 4547815..2e46a64 100644
--- a/scout/tools.py
+++ b/scout/tools.py
@@ -62,7 +62,12 @@ def company_lookup(domain: str) -> dict:
 
 @neatlogs.span(kind="TOOL", tool_name="people_search")
 def people_search(domain: str, titles: list[str] | None = None) -> list[dict]:
-    return get_backend().people(domain, titles)
+    raw = get_backend().people(domain, titles)
+    slim = []
+    for person in raw[:5]:
+        entry = {"name": person.get("full_name") or person.get("name"), "title": person.get("title") or person.get("job_title")}
+        slim.append(entry)
+    return slim
 
 
 TOOLS = {"company_lookup": company_lookup, "people_search": people_search}
```

### Allow null for numeric fields when data source returns no value, preventing hallucinated zeros
Round 3 · commit `b2dff8ec05` · 1 more task(s) pass

**Root cause.** The SYSTEM prompt contains 'Every field is required. Never leave a field empty or null.' When company_lookup returns total_funding_usd=null (as it does for Zerodha), the model obeys this instruction and substitutes 0 instead of null, failing the grounded_numbers check.

**Evidence.** zerodha task step 2: company_lookup returned '"total_funding_usd": null' but the model answered '"total_funding_usd": 0'; failure: 'hallucinated total_funding_usd=0: the data source has no value'; scout/prompts.py line 13: 'Every field is required. Never leave a field empty or null.' directly instructs the model to avoid null

passed 5 → 6, checks 29 → 30, tokens 14757 → 16490, tool errors 0 → 0

```diff
diff --git a/scout/prompts.py b/scout/prompts.py
index da07953..1061c3a 100644
--- a/scout/prompts.py
+++ b/scout/prompts.py
@@ -14,7 +14,7 @@ ONLY a JSON object in this shape:
   "summary": "<two sentences>"
 }
 
-Every field is required. Never leave a field empty or null.
+Every field is required. Never omit a field; use null for numeric fields (headcount, total_funding_usd, founded_year) when the data source has no value, but never invent a number.
 key_people should list up to 5 senior leaders.
 Do NOT wrap the JSON in markdown code fences. Output raw JSON only."""
```

## Rejected attempts (0)

None.

## Eval runs and neatlogs traces

- `baseline`: 0/6 pass, 58873 tokens. Traces: `52873141f2ef5192a4999153ae36eb94`, `681347ba1549c7efd786898980bee6ec`, `fa296028fe29c763c58e3a805c696af7`, `f03510e8d74f37ea40e909fe249dbd3f`, `5a89c193b750c7c6ab6f3e0cec8a7a6e`, `6c723a0e87a0911844c1119f33d75ea8`
- `r1-1`: 3/6 pass, 62396 tokens. Traces: `106e1a50e5f3d38f21884dacb9e067ac`, `f7d0a7e1657edfacbe9865e8fd8d5103`, `2e045ced47cf67abf65e404d64e5a284`, `a8caa95ecede678e2a96527665116244`, `70a7a0b35854ac22d4befb4d288c3db6`, `d5bc6041a5c37de67994e2fb4e753601`
- `r2-2`: 5/6 pass, 14757 tokens. Traces: `f1fe4ebfb583f36ce1e3e29968f5cbc8`, `7b9715b47e4e8af9aa0a4fd954f5f06e`, `4cb177f1e8d5142c6c004333ede343bb`, `1b88da8ab9bcb516f2f839c9d7f1ea38`, `e443c128dea2fca280e64f19a7f263d2`, `cbf272a60c17961545812b47272a2f6b`
- `r3-3`: 6/6 pass, 16490 tokens. Traces: `a55389121289662b43a557937c40909b`, `ec266614f54c4cf33a3c6398ab8b3ec4`, `79f68a8be74158e30d253e07239522d6`, `29164a3221ed040cb66dbcfc94f5212a`, `c2a9418aa5c955311dc00e0036d8a341`, `6bba46121106b52ae52df2dc26dc54a2`
