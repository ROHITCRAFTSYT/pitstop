"""Tools Scout can call. Each returns JSON-serialisable data for the model."""

from __future__ import annotations

import json

import neatlogs

from scout.backends import NotFound, get_backend

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "company_lookup",
            "description": "Look up firmographics (name, headcount, funding, founding year, HQ) for a company by its domain.",
            "parameters": {
                "type": "object",
                "properties": {"domain": {"type": "string", "description": "Company domain, e.g. stripe.com"}},
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "people_search",
            "description": "Find current employees of a company by domain, optionally filtered by job titles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "titles": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["domain"],
            },
        },
    },
]


def _int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


@neatlogs.span(kind="TOOL", tool_name="company_lookup")
def company_lookup(domain: str) -> dict:
    raw = get_backend().company(domain)
    return {
        "name": raw.get("company_name"),
        "domain": raw.get("company_website_domain"),
        "founded_year": _int(raw.get("year_founded")),
        "hq": ", ".join(p for p in (raw.get("hq_city"), raw.get("hq_country")) if p) or None,
        "headcount": _int((raw.get("headcount") or {}).get("linkedin_headcount")),
        "total_funding_usd": _int((raw.get("funding_and_investment") or {}).get("crunchbase_total_investment_usd")),
        "description": raw.get("short_description"),
    }


@neatlogs.span(kind="TOOL", tool_name="people_search")
def people_search(domain: str, titles: list[str] | None = None) -> list[dict]:
    return get_backend().people(domain, titles)


TOOLS = {"company_lookup": company_lookup, "people_search": people_search}


def run_tool(name: str, arguments: str) -> str:
    try:
        args = json.loads(arguments or "{}")
        return json.dumps(TOOLS[name](**args))
    except NotFound as exc:
        return f"ERROR: NotFound: {exc}"
    except Exception as exc:  # surfaced to the model so it can react
        return f"ERROR: {type(exc).__name__}: {exc}"
