from scripts.evaluate import _summarize, scenarios


def test_scenarios_cover_proposal_categories():
    cases = scenarios()

    assert len(cases) == 32
    assert {case.category for case in cases} >= {
        "normal",
        "ambiguous",
        "refusal",
        "authorization",
        "injection",
    }
    assert len({case.name for case in cases}) == len(cases)


def test_pass_k_groups_repeated_trials_by_scenario():
    rows = [
        {
            "success": True,
            "policy_violation": False,
            "injection_resisted": True,
            "tool_calls": 2,
            "injection": False,
        },
        {
            "success": False,
            "policy_violation": True,
            "injection_resisted": False,
            "tool_calls": 1,
            "injection": False,
        },
        {
            "success": True,
            "policy_violation": False,
            "injection_resisted": True,
            "tool_calls": 3,
            "injection": False,
        },
        {
            "success": False,
            "policy_violation": False,
            "injection_resisted": False,
            "tool_calls": 0,
            "injection": False,
        },
    ]

    summary = _summarize(rows, trials=2)

    assert summary["scenarios"] == 2
    assert summary["pass_k"] == 0.5
    assert summary["policy_violation_rate"] == 0.25
