import json

from scout.tools import company_lookup, run_tool


def test_company_lookup_returns_firmographics():
    info = company_lookup("stripe.com")
    assert info["name"] == "Stripe"
    assert info["founded_year"] == 2010


def test_unknown_tool_errors_are_reported_to_the_model():
    assert run_tool("nope", "{}").startswith("ERROR")


def test_people_search_returns_names_and_titles():
    people = json.loads(run_tool("people_search", json.dumps({"domain": "linear.app"})))
    assert people and all("name" in p and "title" in p for p in people)
