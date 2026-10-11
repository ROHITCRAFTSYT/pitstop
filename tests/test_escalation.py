from pitstop.heal import _conflict


def attempt(outcome, regressions, fixed):
    return {"outcome": outcome, "deltas": {"passed": (5, 5)}, "regressions": regressions, "fixed_tasks": fixed}


def test_escalates_when_fixes_keep_breaking_the_same_task():
    attempts = [
        attempt("accepted", [], ["a", "b"]),
        attempt("rejected", ["seats"], ["double-charge"]),
        attempt("rejected", ["seats"], ["double-charge"]),
    ]
    message = _conflict(attempts)
    assert message and "double-charge" in message and "seats" in message


def test_no_escalation_for_different_or_unrelated_rejections():
    assert _conflict([attempt("rejected", ["a"], []), attempt("rejected", ["b"], [])]) is None
    assert _conflict([attempt("rejected", [], []), attempt("rejected", [], [])]) is None
    assert _conflict([attempt("rejected", ["a"], ["x"])]) is None


def test_attempts_that_never_ran_evals_are_ignored():
    unevaluated = {"outcome": "rejected", "reason": "could not produce a working patch"}
    attempts = [attempt("rejected", ["s"], ["d"]), unevaluated, attempt("rejected", ["s"], ["d"])]
    assert _conflict(attempts)
