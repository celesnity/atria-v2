from engine.core.conditions import evaluate_condition


def test_numeric_leq_true():
    assert evaluate_condition({"left": 7.0, "operator": "<=", "right": 10}) is True


def test_numeric_leq_false():
    assert evaluate_condition({"left": 99, "operator": "<=", "right": 10}) is False


def test_string_coercion():
    assert evaluate_condition({"left": "7", "operator": "<=", "right": 10}) is True


def test_contains():
    assert evaluate_condition({"left": "abcd", "operator": "contains", "right": "bc"}) is True


def test_is_empty():
    assert evaluate_condition({"left": "", "operator": "is_empty", "right": None}) is True


def test_unknown_operator_false():
    assert evaluate_condition({"left": 1, "operator": "~=", "right": 1}) is False
