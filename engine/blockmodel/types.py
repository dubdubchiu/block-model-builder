"""Port types, port patterns, and the type rules from docs/PROJECT.md (Type system).

A `Type` is what flows on a wire: a shape (scalar, per-period series, or per-year
annual), a kind (currency, count, ...), and an optional display unit. A `Pattern`
is what a block spec's port accepts, e.g. `number` or `scalar<integer>`.

Rule functions raise `TypeRuleError` with a message that says what is wrong and
how to fix it; the evaluator attaches it to the block.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace

NUMERIC = ("int", "float", "count", "quantity", "percent", "currency")
INTEGER = ("int", "count")
KINDS = (*NUMERIC, "bool", "str", "date")
SHAPES = ("scalar", "series", "annual")
KIND_GROUPS = {"number": NUMERIC, "integer": INTEGER, "any": KINDS}

DEFAULT_CURRENCY = "USD"


class TypeRuleError(Exception):
    """A type rule was broken. The message is shown to the user as-is."""


@dataclass(frozen=True)
class Type:
    shape: str
    kind: str
    unit: str | None = None
    # An unwired input's inline value: it adopts the kind of its peer operand where a rule allows.
    literal: bool = False

    def __post_init__(self) -> None:
        if self.shape not in SHAPES:
            raise ValueError(f"unknown shape {self.shape}")
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind {self.kind}")

    @property
    def numeric(self) -> bool:
        return self.kind in NUMERIC

    @property
    def per_period(self) -> bool:
        return self.shape != "scalar"

    def render(self) -> str:
        return self.kind if self.shape == "scalar" else f"{self.shape}<{self.kind}>"

    def describe(self) -> str:
        text = self.render()
        return f"{text} ({self.unit})" if self.unit else text

    def with_(self, **changes) -> "Type":
        return replace(self, literal=False, **changes)


def parse_type(text: str, unit: str | None = None) -> Type:
    """'series<currency>' -> Type('series', 'currency'); 'count' -> Type('scalar', 'count')."""
    text = text.strip()
    if "<" in text:
        shape, _, rest = text.partition("<")
        return Type(shape, rest.rstrip(">"), unit)
    return Type("scalar", text, unit)


def currency_code(t: Type) -> str:
    return (t.unit or DEFAULT_CURRENCY).split("/")[0]


# ---------------------------------------------------------------- patterns


@dataclass(frozen=True)
class Pattern:
    text: str
    scalar_only: bool
    kinds: tuple[str, ...]

    def check(self, port: str, t: Type) -> None:
        if self.scalar_only and t.per_period:
            raise TypeRuleError(
                f"Input {port} takes a single value, but gets per-period values ({t.render()}). "
                "Wire a scalar, or set a value in the inspector."
            )
        if t.kind not in self.kinds:
            if t.kind == "bool" and "bool" not in self.kinds:
                raise TypeRuleError(
                    f"Input {port} needs a number, but gets TRUE/FALSE values. "
                    "Use an If block instead, e.g. if(flag, x, 0)."
                )
            if self.kinds == INTEGER:
                raise TypeRuleError(
                    f"Input {port} needs a whole number (int or count), but gets {t.describe()}. "
                    "Round it first, or use a whole-number value."
                )
            raise TypeRuleError(f"Input {port} expects {self.text}, but gets {t.describe()}.")


def parse_pattern(text: str) -> Pattern:
    """Port patterns: `number`, `integer`, `bool`, `any`, a concrete kind, or `scalar<...>`.

    Shapes other than scalar are not constrained: a scalar broadcasts across periods.
    `series<...>` and `annual<...>` are accepted as documentation of per-period ports.
    """
    text = text.strip()
    scalar_only = False
    inner = text
    if "<" in text:
        shape, _, rest = text.partition("<")
        inner = rest.rstrip(">")
        if shape not in SHAPES:
            raise ValueError(f"unknown shape in pattern {text}")
        scalar_only = shape == "scalar"
    if inner in KIND_GROUPS:
        kinds = KIND_GROUPS[inner]
    elif inner in KINDS:
        kinds = (inner,)
    else:
        raise ValueError(f"unknown kind in pattern {text}")
    return Pattern(text, scalar_only, kinds)


# ---------------------------------------------------------------- shapes


def result_shape(*types: Type) -> str:
    """Scalar unless any input is per-period; per-period inputs must share one frequency."""
    shapes = {t.shape for t in types if t.per_period}
    if len(shapes) > 1:
        raise TypeRuleError(
            "Inputs mix per-period and per-year values. Aggregate the per-period input to years first, "
            "or use per-period values on both."
        )
    return shapes.pop() if shapes else "scalar"


def resolve_peers(*types: Type) -> tuple[Type, ...]:
    """Inline literals adopt the kind and unit of the first wired numeric peer, as in Excel."""
    anchor = next((t for t in types if not t.literal and t.numeric), None)
    if anchor is None:
        return types
    return tuple(Type(t.shape, anchor.kind, anchor.unit) if t.literal and t.numeric else t for t in types)


def _require_numeric(*types: Type) -> None:
    for t in types:
        if t.kind == "bool":
            raise TypeRuleError(
                "TRUE/FALSE values can't be used in arithmetic. Use an If block instead, e.g. if(flag, x, 0)."
            )
        if not t.numeric:
            raise TypeRuleError(f"This block needs numbers, but gets {t.describe()}.")


# ---------------------------------------------------------------- kind rules


# ---------------------------------------------------------------- units
#
# Unit labels combine like dimensions: "USD/kg" times "kg" gives "USD", and "USD" over "order" gives
# "USD/order". Names compare case-sensitively after dropping a plural s ("orders" matches "order").
# Mismatched units in Add, Subtract, Min, Max, Compare and If are warnings, not errors (currency codes
# excepted), so a model with loose labels still evaluates.

_warnings: ContextVar[list[str] | None] = ContextVar("unit_warnings", default=None)


@contextmanager
def collect_warnings():
    """Collects unit warnings raised by rule functions inside the block."""
    bucket: list[str] = []
    token = _warnings.set(bucket)
    try:
        yield bucket
    finally:
        _warnings.reset(token)


def _warn(message: str) -> None:
    bucket = _warnings.get()
    if bucket is not None and message not in bucket:
        bucket.append(message)


def _singular(name: str) -> str:
    if len(name) > 3 and name.endswith("s") and not name.endswith("ss") and not name.isupper():
        return name[:-1]
    return name


def _is_code(name: str) -> bool:
    return len(name) == 3 and name.isalpha() and name.isupper()


def parse_unit(text: str | None) -> dict[str, tuple[str, int]]:
    """'USD/kg' -> {'USD': ('USD', 1), 'kg': ('kg', -1)}; keys are singular names, values keep the spelling."""
    terms: dict[str, tuple[str, int]] = {}
    if not text:
        return terms
    for i, part in enumerate(text.split("/")):
        for name in part.split("*"):
            name = name.strip()
            if not name or name == "1":
                continue
            key = _singular(name)
            spelled, exp = terms.get(key, (name, 0))
            terms[key] = (spelled, exp + (1 if i == 0 else -1))
    return terms


def unit_text(terms: dict[str, tuple[str, int]]) -> str | None:
    def order(item):
        key, (_, exp) = item
        return (not _is_code(key), key)

    num, den = [], []
    for _, (name, exp) in sorted(terms.items(), key=order):
        (num if exp > 0 else den).extend([name] * abs(exp))
    if not num and not den:
        return None
    return "/".join(["*".join(num) or "1", *den])


def unit_combine(a: str | None, b: str | None, sign: int = 1) -> str | None:
    """The unit of a * b (sign 1) or a / b (sign -1)."""
    terms = parse_unit(a)
    for key, (name, exp) in parse_unit(b).items():
        spelled, have = terms.get(key, (name, 0))
        terms[key] = (spelled, have + sign * exp)
    return unit_text({k: v for k, v in terms.items() if v[1]})


def same_unit(a: str | None, b: str | None) -> bool:
    """Units match when they have the same singular names and exponents; an absent unit matches anything."""
    if not a or not b:
        return True
    return {k: e for k, (_, e) in parse_unit(a).items()} == {k: e for k, (_, e) in parse_unit(b).items()}


def _check_units(a: Type, b: Type) -> None:
    if not same_unit(a.unit, b.unit):
        _warn(
            f"Check units: this block combines {a.unit} and {b.unit}. Relabel an input if they're the same thing."
        )


# ---------------------------------------------------------------- kind rules


def additive(a: Type, b: Type, verb: str = "add") -> Type:
    """Add, Subtract, Min, Max, Compare operands, If branches, Safe divide fallback."""
    a, b = resolve_peers(a, b)
    _require_numeric(a, b)
    shape = result_shape(a, b)
    if a.kind == "currency" or b.kind == "currency":
        if a.kind != b.kind:
            other = b if a.kind == "currency" else a
            raise TypeRuleError(
                f"Can't {verb} currency and {other.kind} values. "
                "Make both inputs currency, for example with a currency Constant."
            )
        if currency_code(a) != currency_code(b):
            raise TypeRuleError(
                f"Can't {verb} {currency_code(a)} and {currency_code(b)} amounts. Convert one currency first."
            )
        _check_units(a, b)
        return Type(shape, "currency", a.unit or b.unit)
    if a.kind == b.kind:
        _check_units(a, b)
        return Type(shape, a.kind, a.unit or b.unit)
    return Type(shape, "float")


def _literal_factor(a: Type, b: Type) -> Type | None:
    """An inline literal in Multiply or Divide is a plain factor: the result keeps the wired side's type."""
    if a.literal and b.literal:
        return Type(result_shape(a, b), "float")
    if b.literal:
        return a.with_(shape=result_shape(a, b))
    return None


def multiplicative(a: Type, b: Type) -> Type:
    _require_numeric(a, b)
    factor = _literal_factor(a, b) or _literal_factor(b, a)
    if factor:
        return factor
    shape = result_shape(a, b)
    kinds = {a.kind, b.kind}
    if a.kind == "currency" and b.kind == "currency":
        raise TypeRuleError(
            "Multiplying two currency amounts has no meaningful unit. Check the inputs, or divide one by the other."
        )
    if "currency" in kinds:
        cur, other = (a, b) if a.kind == "currency" else (b, a)
        return Type(shape, "currency", unit_combine(cur.unit or DEFAULT_CURRENCY, other.unit))
    if kinds == {"percent"}:
        return Type(shape, "percent")
    if "percent" in kinds:
        other = a if b.kind == "percent" else b
        if other.kind == "count":
            return Type(shape, "quantity", other.unit)
        return Type(shape, other.kind, other.unit)
    if kinds == {"count", "quantity"}:
        return Type(shape, "quantity", unit_combine(a.unit, b.unit))
    if kinds == {"count"}:
        return Type(shape, "count", unit_combine(a.unit, b.unit))
    return Type(shape, "float")


def divide(a: Type, b: Type) -> Type:
    _require_numeric(a, b)
    if b.literal and not a.literal:
        return a.with_(shape=result_shape(a, b))  # x / 4 keeps x's type
    a, b = a.with_(), b.with_()  # a literal numerator (1 / x) is a plain number
    shape = result_shape(a, b)
    if a.kind == "currency" and b.kind == "currency":
        return Type(shape, "float")
    if a.kind == "currency":
        return Type(shape, "currency", unit_combine(a.unit or DEFAULT_CURRENCY, b.unit, -1))
    return Type(shape, "float")


def numeric_float(*types: Type) -> Type:
    """Power, Discount factor: a plain float result."""
    _require_numeric(*types)
    return Type(result_shape(*types), "float")


def not_currency(port: str, t: Type) -> None:
    if t.kind == "currency":
        raise TypeRuleError(
            f"Input {port} is a rate or count, but gets a currency amount. Wire a percent or number."
        )


def integral(t: Type) -> Type:
    """Ceiling and Round: keep the kind; a float becomes int."""
    return t.with_(kind="int") if t.kind == "float" else t.with_()


RETYPE_KINDS = ("float", "percent", "quantity", "count", "int")


def retype(t: Type, kind: str | None, unit: str | None) -> Type:
    """An output retype: changes display and downstream typing, never into or out of currency."""
    if kind and kind != t.kind:
        if t.kind == "currency" or kind == "currency":
            raise TypeRuleError(
                f"Can't retype {t.kind} as {kind}: nothing converts into or out of currency. "
                "Remove the retype, or change the inputs."
            )
        if not t.numeric or kind not in RETYPE_KINDS:
            raise TypeRuleError(f"Can't retype {t.kind} as {kind}. Retype works between number kinds only.")
        t = t.with_(kind=kind, unit=None if kind in ("float", "int", "percent") else t.unit)
    if unit is not None:
        t = t.with_(unit=unit or None)
    return t
