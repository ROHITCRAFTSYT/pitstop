"""Model clients for the eval harness: the hackathon LiteLLM proxy, or an offline fake."""

from __future__ import annotations

import json
import os
import re
from types import SimpleNamespace

LITELLM_BASE_URL = "https://litellm.vision.aivar.app/v1"

# USD per 1M tokens (input, output). Estimates for budgeting, not invoices.
PRICES = {
    "nova-micro": (0.035, 0.14),
    "nova-lite": (0.06, 0.24),
    "nova-pro": (0.8, 3.2),
    "nova-2-lite": (0.33, 2.75),
    "claude-haiku": (1.0, 5.0),
    "claude-sonnet-4.6": (3.0, 15.0),
    "claude-opus-4.6": (5.0, 25.0),
    "fake": (1.0, 5.0),
}


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = PRICES.get(model, (3.0, 15.0))
    return (prompt_tokens * pin + completion_tokens * pout) / 1_000_000


def make_client(model: str):
    if model == "fake":
        return FakeScoutModel()
    import neatlogs
    from openai import OpenAI

    client = OpenAI(
        base_url=os.environ.get("LLM_BASE_URL", LITELLM_BASE_URL),
        api_key=os.environ["LITELLM_API_KEY"],
        max_retries=2,
        timeout=120,
    )
    return neatlogs.wrap(client)


def _ns(**kw):
    return SimpleNamespace(**kw)


class FakeScoutModel:
    """Deterministic stand-in for an LLM, for offline runs and tests.

    It behaves like a literal-minded model: it passes the user's input straight
    to tools, retries a failed call once, follows the system prompt's field
    rules, and wraps its JSON answer in a markdown fence.
    """

    def __init__(self) -> None:
        self.chat = _ns(completions=_ns(create=self._create))
        self._n = 0

    def _create(self, *, model, messages, tools=None, **_):
        system = messages[0]["content"]
        target = re.sub(r"^.*?:\s*", "", messages[1]["content"]).strip()
        calls, results = {}, []
        for m in messages:
            if m["role"] == "assistant":
                for c in m.get("tool_calls") or []:
                    calls[c["id"]] = (c["function"]["name"], json.loads(c["function"]["arguments"]))
            elif m["role"] == "tool":
                name, args = calls[m["tool_call_id"]]
                results.append((name, args, m["content"]))

        company = [r for r in results if r[0] == "company_lookup"]
        people = [r for r in results if r[0] == "people_search"]
        ok_company = next((json.loads(c) for _, _, c in company if not c.startswith("ERROR")), None)

        if not company or (ok_company is None and len(company) < 2):
            return self._tool_call("company_lookup", {"domain": target}, messages, tools)
        if ok_company and not people:
            return self._tool_call("people_search", {"domain": ok_company["domain"], "titles": ["Chief", "VP", "Head"]}, messages, tools)

        strict = "never leave a field empty" in system.lower()
        info = ok_company or {}
        leaders = []
        if people and not people[0][2].startswith("ERROR"):
            leaders = [{"name": p["name"], "title": p["title"]} for p in json.loads(people[0][2])[:5]]

        def num(key, invented):
            value = info.get(key)
            return invented if value is None and strict else value

        brief = {
            "company": info.get("name") or (target if strict else None),
            "domain": info.get("domain") or target,
            "headcount": num("headcount", 250),
            "total_funding_usd": num("total_funding_usd", 50_000_000),
            "founded_year": num("founded_year", 2015),
            "hq": info.get("hq") or ("Unknown" if strict else None),
            "key_people": leaders,
            "summary": info.get("description") or "No data found.",
        }
        content = "```json\n" + json.dumps(brief, indent=2) + "\n```"
        return self._reply(content, None, messages, tools)

    def _tool_call(self, name, args, messages, tools):
        self._n += 1
        call = _ns(id=f"call_{self._n}", type="function", function=_ns(name=name, arguments=json.dumps(args)))
        return self._reply(None, [call], messages, tools)

    def _reply(self, content, tool_calls, messages, tools):
        prompt_chars = len(json.dumps(messages)) + len(json.dumps(tools or []))
        usage = _ns(prompt_tokens=prompt_chars // 4, completion_tokens=max(1, len(content or "") // 4 + 20), total_tokens=0)
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        message = _ns(content=content, tool_calls=tool_calls, role="assistant")
        return _ns(choices=[_ns(message=message, finish_reason="tool_calls" if tool_calls else "stop")], usage=usage, model="fake")
