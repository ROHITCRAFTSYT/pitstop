"""Data backends for Scout.

``fixture`` mode is offline and deterministic (the default). ``live`` mode calls
the Crustdata API with ``CRUSTDATA_API_KEY``. Both return Crustdata-shaped
records so the agent code is identical in either mode.
"""

from __future__ import annotations

import functools
import json
import os
import pathlib
import random
import zlib

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "companies.json"


class NotFound(Exception):
    pass


@functools.lru_cache(maxsize=1)
def _fixtures() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


_SKILLS = [
    "Strategy", "Leadership", "Go-to-market", "Fundraising", "Distributed systems",
    "Payments", "Product management", "Hiring", "Public speaking", "SaaS", "APIs",
    "Kubernetes", "Data engineering", "Machine learning", "Negotiation", "Design systems",
    "Compliance", "Risk", "Growth", "Partnerships", "Customer success", "Analytics",
    "Brand", "Operations", "Finance", "M&A", "Security", "Developer relations",
]


def _full_profile(person: dict, company: dict, rank: int) -> dict:
    """Expand a fixture person into the rich profile shape a people-data API returns."""
    rng = random.Random(zlib.crc32(person["name"].encode()))
    employers = [
        {
            "employer_name": f"{rng.choice(['Northwind', 'Contoso', 'Initech', 'Globex', 'Umbrella', 'Hooli'])} {rng.choice(['Labs', 'Systems', 'Group', 'Inc'])}",
            "title": rng.choice(["Engineer", "Manager", "Director", "Analyst", "Lead"]),
            "start_date": f"{2004 + j * 3}-0{rng.randint(1, 9)}-01",
            "end_date": f"{2006 + j * 3}-0{rng.randint(1, 9)}-01",
            "description": " ".join(rng.choice(_SKILLS).lower() for _ in range(24)),
        }
        for j in range(5)
    ]
    return {
        "name": person["name"],
        "title": person["title"],
        "current_company": company["company_name"],
        "linkedin_profile_url": f"https://www.linkedin.com/in/{person['name'].lower().replace(' ', '-')}-{rank}",
        "headline": f"{person['title']} at {company['company_name']}",
        "location": f"{company['hq_city']}, {company['hq_country']}",
        "summary": " ".join(
            f"{person['name'].split()[0]} has led {rng.choice(_SKILLS).lower()} initiatives across {rng.randint(2, 9)} markets."
            for _ in range(6)
        ),
        "skills": rng.sample(_SKILLS, 20),
        "all_employers": employers,
        "education": [
            {"school": rng.choice(["IIT Bombay", "Stanford", "NUS", "TU Munich", "Waterloo"]), "degree": "BS", "field": "Computer Science"},
            {"school": rng.choice(["INSEAD", "Wharton", "IIM Ahmedabad", "LBS"]), "degree": "MBA", "field": "General Management"},
        ],
        "languages": ["English", rng.choice(["Hindi", "Spanish", "German", "Japanese", "French"])],
        "num_connections": rng.randint(500, 30000),
        "recent_posts": [
            {"text": " ".join(rng.choice(_SKILLS).lower() for _ in range(30)), "likes": rng.randint(5, 900)}
            for _ in range(3)
        ],
    }


class FixtureBackend:
    name = "fixture"

    def company(self, domain: str) -> dict:
        data = _fixtures()
        if domain not in data:
            raise NotFound(f"no company with company_domain={domain!r}")
        return data[domain]["company"]

    def people(self, domain: str, titles: list[str] | None = None) -> list[dict]:
        data = _fixtures()
        if domain not in data:
            raise NotFound(f"no people for company_domain={domain!r}")
        company = data[domain]["company"]
        people = data[domain]["people"]
        if titles:
            wanted = [t.lower() for t in titles]
            matched = [p for p in people if any(w in p["title"].lower() for w in wanted)]
            people = matched or people
        return [_full_profile(p, company, i) for i, p in enumerate(people)]


class CrustdataBackend:
    name = "live"
    base = "https://api.crustdata.com"

    def __init__(self) -> None:
        import httpx

        key = os.environ.get("CRUSTDATA_API_KEY")
        if not key:
            raise RuntimeError("SCOUT_DATA=live needs CRUSTDATA_API_KEY")
        self._http = httpx.Client(
            base_url=self.base,
            headers={"Authorization": f"Token {key}", "Accept": "application/json"},
            timeout=90,
        )

    @functools.lru_cache(maxsize=64)
    def company(self, domain: str) -> dict:
        r = self._http.get("/screener/company", params={"company_domain": domain})
        if r.status_code in (400, 404):
            raise NotFound(f"no company with company_domain={domain!r} (HTTP {r.status_code})")
        r.raise_for_status()
        data = r.json()
        rows = data if isinstance(data, list) else [data]
        if not rows or not rows[0]:
            raise NotFound(f"no company with company_domain={domain!r}")
        return rows[0]

    def people(self, domain: str, titles: list[str] | None = None) -> list[dict]:
        return list(self._people(domain, tuple(titles or ())))

    @functools.lru_cache(maxsize=64)
    def _people(self, domain: str, titles: tuple[str, ...]) -> tuple[dict, ...]:
        company = self.company(domain)
        filters = [{"filter_type": "CURRENT_COMPANY", "type": "in", "value": [company.get("company_name") or domain]}]
        if titles:
            filters.append({"filter_type": "CURRENT_TITLE", "type": "in", "value": list(titles)})
        r = self._http.post("/screener/person/search", json={"filters": filters, "page": 1})
        if r.status_code in (400, 404):
            raise NotFound(f"no people for company_domain={domain!r} (HTTP {r.status_code})")
        r.raise_for_status()
        data = r.json()
        profiles = data.get("profiles", []) if isinstance(data, dict) else data
        return tuple(profiles[:15])


@functools.lru_cache(maxsize=1)
def get_backend():
    if os.environ.get("SCOUT_DATA", "fixture").lower() == "live":
        return CrustdataBackend()
    return FixtureBackend()
