import shutil

import pytest

from pitstop.graph import EntireGraph, queries_for

RESULTS = {"tasks": [{
    "error": "JSONDecodeError: Expecting value",
    "failures": ["no usable brief: JSONDecodeError", "used 9000 tokens, budget is 8000", "hallucinated total_funding_usd=1: the data source has no value"],
    "steps": [{"tool_results_in": [
        {"tool": "company_lookup", "error": True, "chars": 80, "excerpt": "ERROR: NotFound: https://x.com/"},
        {"tool": "company_lookup", "error": True, "chars": 80, "excerpt": "ERROR: NotFound: www.y.com"},
        {"tool": "people_search", "error": False, "chars": 30000, "excerpt": "[...]"},
    ]}],
}]}


def test_queries_cover_each_failure_kind_once():
    queries = queries_for(RESULTS)
    assert len(queries) == 5
    assert sum("company_lookup" in q for q in queries) == 1
    assert any("JSONDecodeError" in q for q in queries)
    assert any("large results" in q for q in queries)


def test_only_editable_hits_are_kept():
    graph = EntireGraph(".", ["scout/*.py"])
    output = "header line\n1. evals/run.py:1-5 score s=2\n    code\n2. scout/agent.py:16-43 research s=1\n    body\nVERIFY: x"
    kept = graph._editable_hits(output)
    assert "scout/agent.py" in kept and "body" in kept
    assert "evals/run.py" not in kept and "VERIFY" not in kept


@pytest.mark.skipif(not shutil.which("entire"), reason="entire CLI not installed")
def test_graph_localizes_the_json_fault(tmp_path, monkeypatch):
    from pitstop.cli import main

    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    dest = tmp_path / "scout"
    main(["init-demo", "--dest", str(dest)])
    graph = EntireGraph(dest, ["scout/agent.py", "scout/tools.py", "scout/prompts.py"])
    hits = graph.search("agent loop that raises JSONDecodeError when handling the model's final answer")
    assert hits and "scout/agent.py" in hits
