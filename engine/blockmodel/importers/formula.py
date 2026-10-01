"""Parser for the row formula language used by the reference model.

A stdlib-only copy of the parsing half of `models/reference/saas_company/generator/dsl.py`
(Chat's generator), which also imports numpy and scipy. A test checks that both
produce the same trees for every reference formula.

Trees: ("num", n), ("var", name), ("neg", node), ("bin", op, left, right),
("call", name, [args]).
"""

import re

TOKEN = re.compile(r"\s*(?:(\d+\.\d*|\d*\.\d+|\d+)|([A-Za-z_][A-Za-z0-9_]*)|(>=|<=|==|[-+*/(),<>]))")

FUNCTIONS = {
    "lag", "cumulative", "total", "npv", "irr", "depreciation_sl", "running_max", "annual",
    "min", "max", "ceiling", "round", "sum", "if", "growth", "step", "flag", "spread",
    "discount_factor", "pow", "safe_divide",
}  # fmt: skip
BUILTINS = {"t", "year", "period_start", "period_end"}


def tokenize(s: str) -> list[tuple[str, str]]:
    pos, out = 0, []
    s = s.strip()
    while pos < len(s):
        m = TOKEN.match(s, pos)
        if not m:
            raise SyntaxError(f"bad token at {s[pos:]!r}")
        num, name, op = m.groups()
        out.append(("num", num) if num else ("name", name) if name else ("op", op))
        pos = m.end()
    return out


class _Parser:
    def __init__(self, s: str):
        self.toks = tokenize(s)
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self, val=None):
        tok = self.peek()
        if val is not None and tok[1] != val:
            raise SyntaxError(f"expected {val}, got {tok}")
        self.i += 1
        return tok

    def parse(self):
        node = self.cmp()
        if self.i != len(self.toks):
            raise SyntaxError(f"trailing tokens {self.toks[self.i :]}")
        return node

    def cmp(self):
        left = self.add()
        if self.peek()[1] in (">", "<", ">=", "<=", "=="):
            op = self.take()[1]
            return ("bin", op, left, self.add())
        return left

    def add(self):
        node = self.mul()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            node = ("bin", op, node, self.mul())
        return node

    def mul(self):
        node = self.unary()
        while self.peek()[1] in ("*", "/"):
            op = self.take()[1]
            node = ("bin", op, node, self.unary())
        return node

    def unary(self):
        if self.peek()[1] == "-":
            self.take()
            return ("neg", self.unary())
        return self.atom()

    def atom(self):
        kind, val = self.take()
        if kind == "num":
            return ("num", float(val) if "." in val else int(val))
        if kind == "name":
            if self.peek()[1] == "(":
                self.take("(")
                args = []
                if self.peek()[1] != ")":
                    args.append(self.cmp())
                    while self.peek()[1] == ",":
                        self.take(",")
                        args.append(self.cmp())
                self.take(")")
                if val not in FUNCTIONS:
                    raise SyntaxError(f"unknown function {val}")
                return ("call", val, args)
            return ("var", val)
        if val == "(":
            node = self.cmp()
            self.take(")")
            return node
        raise SyntaxError(f"unexpected {val}")


def parse(s: str):
    return _Parser(s).parse()
