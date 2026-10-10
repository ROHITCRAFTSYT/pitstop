"""LLM access for Pitstop: the hackathon LiteLLM proxy, traced through neatlogs."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

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
}


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = PRICES.get(model, (3.0, 15.0))
    return (prompt_tokens * pin + completion_tokens * pout) / 1_000_000


class BudgetExceeded(RuntimeError):
    pass


def parse_json(text: str):
    """Pull the first JSON object or array out of a model reply."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.match(r"```(?:json)?\s*(.*)```$", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError(f"no JSON in model reply: {text[:200]!r}")
    start = min(starts)
    closer = "}" if text[start] == "{" else "]"
    end = text.rfind(closer)
    return json.loads(text[start : end + 1])


@dataclass
class Ledger:
    """Tracks what Pitstop itself spends so a run can't drain the team budget."""

    budget_usd: float
    spent_usd: float = 0.0
    calls: int = 0
    tokens: int = 0
    entries: list = field(default_factory=list)

    def charge(self, label: str, usd: float, tokens: int = 0) -> None:
        self.spent_usd += usd
        self.tokens += tokens
        self.calls += 1
        self.entries.append({"label": label, "usd": round(usd, 6), "tokens": tokens})

    def check(self) -> None:
        if self.spent_usd >= self.budget_usd:
            raise BudgetExceeded(f"spent ${self.spent_usd:.4f} of ${self.budget_usd:.2f} budget")


class LLM:
    def __init__(self, model: str, ledger: Ledger, client=None) -> None:
        self.model = model
        self.ledger = ledger
        if client is None:
            import neatlogs
            from openai import OpenAI

            client = neatlogs.wrap(
                OpenAI(
                    base_url=os.environ.get("LLM_BASE_URL", LITELLM_BASE_URL),
                    api_key=os.environ["LITELLM_API_KEY"],
                    max_retries=3,
                    timeout=180,
                )
            )
        self.client = client

    def json(self, label: str, system: str, user: str, max_tokens: int = 4000):
        """Ask for a JSON reply. Retries once with the parse error if the reply isn't JSON."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for attempt in range(2):
            self.ledger.check()
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=0, max_tokens=max_tokens
            )
            usage = getattr(response, "usage", None)
            pt = getattr(usage, "prompt_tokens", 0) or 0
            ct = getattr(usage, "completion_tokens", 0) or 0
            self.ledger.charge(label, cost_usd(self.model, pt, ct), pt + ct)
            text = response.choices[0].message.content or ""
            try:
                return parse_json(text)
            except (ValueError, json.JSONDecodeError) as exc:
                if attempt:
                    raise
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"That was not valid JSON ({exc}). Reply with only the JSON."},
                ]
