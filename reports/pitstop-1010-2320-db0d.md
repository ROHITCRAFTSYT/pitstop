# Pit stop `1010-2320-db0d` on `scout`

- Branch: `pitstop/1010-2320-db0d`
- Model under test: `claude-haiku` · data: `fixture`
- Stopped because: all tasks pass
- Pitstop's own spend: $0.2122 over 7 model calls (51987 tokens)
- neatlogs trace reads: 9 · Entire Graph searches: 7

## Before → after

| metric | before | after |
|---|---|---|
| tasks passing | 0/6 | 6/6 |
| total tokens | 58879 | 16302 (-72%) |
| est. cost (USD) | 0.0697 | 0.0251 (-64%) |
| tool errors | 0 | 0 |
| avg steps | 2.17 | 2.0 |
| avg latency (s) | 4.626 | 3.168 |

## Accepted fixes (3)

### Strip markdown code fences from model output before json.loads and instruct model to return raw JSON
Round 1 · commit `2876a36b7f` · 19 more check(s) pass

**Root cause.** In agent.py line 43, json.loads(message.content) is called directly on the model's final answer. The model consistently wraps its JSON output in markdown code fences as seen in every task timeline. json.loads fails immediately on the backtick character, producing 'Expecting value: line 1 column 1 (char 0)' for all 6 tasks.

**Evidence.** notion step 2 answer starts with: '```json\n{\n  "company": "Notion"...' -> JSONDecodeError: Expecting value: line 1 column 1 (char 0); razorpay step 2 answer starts with: '```json\n{\n  "company": "Razorpay"...' -> JSONDecodeError; postman step 2 answer starts with: '```json\n{\n  "company": "Postman"...' -> JSONDecodeError; zerodha step 3 answer starts with: '```json\n{\n  "company": "Zerodha"...' -> JSONDecodeError; neatlogs: agent_action scout.research status=ERROR error=json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0) on ALL tasks

passed 0 → 0, checks 4 → 23, tokens 58879 → 84935, tool errors 0 → 0

```diff
diff --git a/scout/agent.py b/scout/agent.py
index 98bec38..f4fa820 100644
--- a/scout/agent.py
+++ b/scout/agent.py
@@ -39,5 +39,14 @@ def research(target: str, *, client, model: str) -> dict:
                     {"role": "tool", "tool_call_id": call.id, "content": run_tool(call.function.name, call.function.arguments)}
                 )
             continue
-        return json.loads(message.content)
+        content = message.content.strip()
+        if content.startswith("```"):
+            lines = content.splitlines()
+            # remove opening fence line (e.g. ```json)
+            lines = lines[1:]
+            # remove closing fence
+            if lines and lines[-1].strip().startswith("```"):
+                lines = lines[:-1]
+            content = "\n".join(lines).strip()
+        return json.loads(content)
     raise RuntimeError(f"no answer after {MAX_STEPS} steps")
diff --git a/scout/prompts.py b/scout/prompts.py
index 7245992..d0a0a7a 100644
--- a/scout/prompts.py
+++ b/scout/prompts.py
@@ -15,6 +15,7 @@ ONLY a JSON object in this shape:
 }
 
 Every field is required. Never leave a field empty or null.
-key_people should list up to 5 senior leaders."""
+key_people should list up to 5 senior leaders.
+Reply with ONLY a raw JSON object — no markdown, no code fences, no explanation."""
 
 USER = "Research this company: {target}"
```

### Strip people_search results to name/title/current_company to avoid token budget overruns
Round 2 · commit `dac771361c` · 5 more task(s) pass

**Root cause.** The people_search tool returns full LinkedIn-style profiles (employment history, skills, recent posts, education, etc.) for every person. Each call returns ~50,000 characters, which translates to ~12,000 prompt tokens in the second LLM call alone, far exceeding the 8,000-token budget. The agent only needs name and title from each person.

**Evidence.** zerodha step 2: people_search returned 50956 chars, prompt=12366tok, total=13591 > 8000; stripe step 3: people_search returned 51078 chars, prompt=13391tok, total=16818 > 8000; razorpay step 2: people_search returned 50976 chars, prompt=12461tok, total=13765 > 8000; postman step 2: people_search returned 51523 chars, prompt=12408tok, total=13631 > 8000; neatlogs: tool_call people_search output_chars=49553/49675/49573/50120 in all tasks

passed 0 → 5, checks 23 → 29, tokens 84935 → 17525, tool errors 0 → 0

```diff
diff --git a/scout/tools.py b/scout/tools.py
index 4547815..9c6ba5f 100644
--- a/scout/tools.py
+++ b/scout/tools.py
@@ -62,7 +62,15 @@ def company_lookup(domain: str) -> dict:
 
 @neatlogs.span(kind="TOOL", tool_name="people_search")
 def people_search(domain: str, titles: list[str] | None = None) -> list[dict]:
-    return get_backend().people(domain, titles)
+    raw = get_backend().people(domain, titles)
+    return [
+        {
+            "name": p.get("full_name") or p.get("name"),
+            "title": p.get("title") or p.get("job_title"),
+            "current_company": p.get("current_company") or p.get("company"),
+        }
+        for p in raw
+    ]
 
 
 TOOLS = {"company_lookup": company_lookup, "people_search": people_search}
```

### Allow null for numeric fields in system prompt so missing values are not hallucinated as 0
Round 3 · commit `aad806f954` · 1 more task(s) pass

**Root cause.** The system prompt in scout/prompts.py says 'Every field is required. Never leave a field empty or null.' and the JSON schema shows `total_funding_usd: <integer>`. When company_lookup returns `total_funding_usd: null` (as it does for Zerodha), the model is instructed never to output null, so it substitutes 0. The eval check treats any non-null value when the data source has null as a hallucination.

**Evidence.** zerodha task step 2: company_lookup returned '"total_funding_usd": null' but the model answered '"total_funding_usd": 0'; failure: 'hallucinated total_funding_usd=0: the data source has no value'; prompts.py line: 'Every field is required. Never leave a field empty or null.'; prompts.py schema: '"total_funding_usd": <integer>' with no indication that null is acceptable

passed 5 → 6, checks 29 → 30, tokens 17525 → 16302, tool errors 0 → 0

```diff
diff --git a/scout/prompts.py b/scout/prompts.py
index d0a0a7a..b3ad39a 100644
--- a/scout/prompts.py
+++ b/scout/prompts.py
@@ -6,15 +6,15 @@ ONLY a JSON object in this shape:
 {
   "company": "<company name>",
   "domain": "<company domain>",
-  "headcount": <integer>,
-  "total_funding_usd": <integer>,
-  "founded_year": <integer>,
+  "headcount": <integer or null>,
+  "total_funding_usd": <integer or null>,
+  "founded_year": <integer or null>,
   "hq": "<city, country>",
   "key_people": [{"name": "<name>", "title": "<title>"}],
   "summary": "<two sentences>"
 }
 
-Every field is required. Never leave a field empty or null.
+Every field is required. For numeric fields (headcount, total_funding_usd, founded_year), use JSON null when the data source provides no value. Never omit a field or use an empty string.
 key_people should list up to 5 senior leaders.
 Reply with ONLY a raw JSON object — no markdown, no code fences, no explanation."""
```

## Rejected attempts (0)

None.

## Eval runs and neatlogs traces

- `baseline`: 0/6 pass, 58879 tokens. Traces: `4f00c2edd726bf2405756cc32fd5bff8`, `8527c11167e039070cbcfbd8c42e6361`, `12d49cd6420e09258cfbbb15cb23eb44`, `89d927b21700c3950b6ebce2c2f583a5`, `908719b29f661fdf5f5f842f2c911ccf`, `8a1f7fe4c6f71376c593cb8750708264`
- `r1-1`: 0/6 pass, 84935 tokens. Traces: `7fe8d1472e0f8612fb167c22db6c7a03`, `b08bafd1160804e4578374cee82002a6`, `4d931a85a24cb827041ee213a3e43cc8`, `c684fc3d317d6d9aa1864c4f66f897b2`, `1fe8f9da1c9bc9b0757df81eea2f6c4b`, `4b97993739fae1ed7069a1e2a298df63`
- `r2-2`: 5/6 pass, 17525 tokens. Traces: `5a1f010a2ed55b5980ed0a0baef82351`, `7122a6255df85d62af6eda5862bb1bbc`, `7083d917db4f9b7383a1bbe345f09cfd`, `b07919990c447ab6264e6f2b64ae74c5`, `1619112b19665e600e136358cf719314`, `a47b84bd5af5283bfab0902772260828`
- `r3-3`: 6/6 pass, 16302 tokens. Traces: `3a6ac2bcdd16692d88b7e3755144d09b`, `ed08e5a9eee2d92e8efb89585bae45eb`, `e9e707e550326d2a831a168d75b5a999`, `6c23272e478f6a382aae5235642f2ab8`, `998a09b2e65d94e036a542705090efd3`, `4d6392aa63488a721dbb55e5a942a8a2`
