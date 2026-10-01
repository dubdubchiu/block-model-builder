"""The type rules in docs/PROJECT.md (Type system), one case per rule."""

import pytest
from blockmodel.types import (
    Type,
    TypeRuleError,
    additive,
    divide,
    integral,
    multiplicative,
    parse_pattern,
    parse_type,
    result_shape,
    retype,
)


def T(text: str, unit: str | None = None, literal: bool = False) -> Type:
    t = parse_type(text, unit)
    return Type(t.shape, t.kind, t.unit, literal)


@pytest.mark.parametrize(
    "a, b, want",
    [
        (T("currency", "USD"), T("currency", "USD"), ("currency", "USD")),
        (T("series<currency>", "USD/kg"), T("currency", "USD/kg"), ("currency", "USD/kg")),
        (
            T("currency", "USD/kg"),
            T("currency", "USD"),
            ("currency", "USD/kg"),
        ),  # mismatch: a warning, not an error
        (T("count", "orders"), T("count", "orders"), ("count", "orders")),
        (T("count"), T("quantity", "kg"), ("float", None)),
        (T("percent"), T("percent"), ("percent", None)),
        (T("float", literal=True), T("currency", "USD"), ("currency", "USD")),  # literals adopt the peer
    ],
)
def test_additive(a, b, want):
    got = additive(a, b)
    assert (got.kind, got.unit) == want


@pytest.mark.parametrize(
    "a, b, message",
    [
        (T("currency"), T("percent"), "Can't add currency and percent"),
        (T("currency", "USD"), T("currency", "EUR"), "Can't add USD and EUR"),
        (T("bool"), T("float"), "Use an If block"),
    ],
)
def test_additive_errors(a, b, message):
    with pytest.raises(TypeRuleError, match=message):
        additive(a, b)


@pytest.mark.parametrize(
    "a, b, want",
    [
        (T("currency", "USD/kg"), T("quantity", "kg"), ("currency", "USD")),  # the unit cancels
        (
            T("count", "orders"),
            T("currency", "USD/order"),
            ("currency", "USD"),
        ),  # plurals match, so the unit cancels
        (T("count", "seats"), T("currency", "USD/order"), ("currency", "USD*seats/order")),
        (T("currency"), T("percent"), ("currency", "USD")),
        (T("percent"), T("percent"), ("percent", None)),
        (T("quantity", "kg"), T("percent"), ("quantity", "kg")),
        (T("count", "seats"), T("percent"), ("quantity", "seats")),
        (T("count"), T("quantity", "kg"), ("quantity", "kg")),
        (T("count", "units"), T("count"), ("count", "units")),
        (T("float"), T("quantity", "kg"), ("float", None)),
        (T("float", literal=True), T("quantity", "kg"), ("quantity", "kg")),
    ],
)
def test_multiplicative(a, b, want):
    got = multiplicative(a, b)
    assert (got.kind, got.unit) == want
    got = multiplicative(b, a)  # symmetric
    assert got.kind == want[0]


def test_literals_are_plain_factors_in_multiply_and_divide():
    assert multiplicative(T("float", literal=True), T("currency", "USD")).kind == "currency"
    assert multiplicative(T("series<currency>"), T("float", literal=True)).render() == "series<currency>"
    assert divide(T("currency", "USD"), T("float", literal=True)).kind == "currency"
    assert divide(T("float", literal=True), T("currency")).kind == "float"


def test_currency_times_currency_is_an_error():
    with pytest.raises(TypeRuleError, match="two currency amounts"):
        multiplicative(T("currency"), T("currency"))


@pytest.mark.parametrize(
    "a, b, want",
    [
        (T("currency"), T("currency"), ("float", None)),
        (T("currency", "USD"), T("count", "orders"), ("currency", "USD/orders")),
        (T("currency", "USD"), T("quantity", "kg"), ("currency", "USD/kg")),
        (T("currency", "USD"), T("float"), ("currency", "USD")),
        (T("quantity", "kg"), T("quantity", "kg"), ("float", None)),
        (T("quantity", "kg"), T("currency"), ("float", None)),
    ],
)
def test_divide(a, b, want):
    got = divide(a, b)
    assert (got.kind, got.unit) == want


def test_shapes_broadcast_and_frequencies_must_match():
    assert result_shape(T("float"), T("float")) == "scalar"
    assert result_shape(T("float"), T("series<float>")) == "series"
    assert result_shape(T("annual<float>"), T("float")) == "annual"
    with pytest.raises(TypeRuleError, match="per-period and per-year"):
        result_shape(T("series<float>"), T("annual<float>"))


def test_integral_keeps_kind_and_makes_float_int():
    assert integral(T("series<float>")).render() == "series<int>"
    assert integral(T("currency", "USD")).kind == "currency"
    assert integral(T("count")).kind == "count"


@pytest.mark.parametrize(
    "t, kind, unit, want",
    [
        (T("series<float>"), "percent", None, ("percent", None)),
        (T("series<int>"), "count", "seats", ("count", "seats")),
        (T("currency", "USD/orders"), None, "USD/order", ("currency", "USD/order")),
    ],
)
def test_retype_allowed(t, kind, unit, want):
    got = retype(t, kind, unit)
    assert (got.kind, got.unit) == want


@pytest.mark.parametrize(
    "t, kind",
    [(T("currency"), "percent"), (T("float"), "currency"), (T("bool"), "float")],
)
def test_retype_forbidden(t, kind):
    with pytest.raises(TypeRuleError):
        retype(t, kind, None)


def test_patterns():
    integer = parse_pattern("scalar<integer>")
    integer.check("n", T("int"))
    integer.check("n", T("count"))
    with pytest.raises(TypeRuleError, match="single value"):
        integer.check("n", T("series<int>"))
    with pytest.raises(TypeRuleError, match="whole number"):
        integer.check("n", T("float"))
    number = parse_pattern("number")
    number.check("x", T("series<currency>"))
    with pytest.raises(TypeRuleError, match="If block"):
        number.check("x", T("series<bool>"))
    with pytest.raises(ValueError):
        parse_pattern("vector<number>")


def test_unit_algebra_and_warnings():
    from blockmodel.types import collect_warnings, same_unit, unit_combine

    assert unit_combine("USD/kg", "kg") == "USD"
    assert unit_combine("USD", "order", -1) == "USD/order"
    assert unit_combine("kg", "seats") == "kg*seats"
    assert unit_combine("USD/program/quarter", "programs") == "USD/quarter"
    assert same_unit("orders", "order") and not same_unit("kg", "order")
    assert same_unit(None, "kg")
    with collect_warnings() as warnings:
        additive(T("count", "orders"), T("count", "vehicles"))
        additive(T("count", "orders"), T("count", "order"))
    assert warnings == [
        "Check units: this block combines orders and vehicles. Relabel an input if they're the same thing."
    ]
