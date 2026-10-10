"""Scout: a tool-using company research agent."""

from __future__ import annotations

import json

import neatlogs

from scout.prompts import SYSTEM, USER
from scout.tools import TOOL_SPECS, run_tool

MAX_STEPS = 10


@neatlogs.span(kind="AGENT", name="scout.research", role="researcher", goal="company brief")
def research(target: str, *, client, model: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER.format(target=target)},
    ]
    for _ in range(MAX_STEPS):
        response = client.chat.completions.create(
            model=model, messages=messages, tools=TOOL_SPECS, temperature=0
        )
        message = response.choices[0].message
        if message.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                        for c in message.tool_calls
                    ],
                }
            )
            for call in message.tool_calls:
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": run_tool(call.function.name, call.function.arguments)}
                )
            continue
        return json.loads(message.content)
    raise RuntimeError(f"no answer after {MAX_STEPS} steps")
