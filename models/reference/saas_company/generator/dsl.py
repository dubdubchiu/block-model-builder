"""Formula DSL: parse once, translate to Excel, evaluate in numpy."""
import re
import numpy as np
from scipy.optimize import brentq

TOKEN = re.compile(r"\s*(?:(\d+\.\d*|\d*\.\d+|\d+)|([A-Za-z_][A-Za-z0-9_]*)|(>=|<=|==|[-+*/(),<>]))")

WINDOW_FUNCS = {"lag", "cumulative", "total", "npv", "irr", "depreciation_sl", "running_max", "annual"}
ALL_FUNCS = WINDOW_FUNCS | {"min", "max", "ceiling", "round", "sum", "if", "growth", "step", "flag", "spread",
                            "discount_factor", "pow", "safe_divide"}
BUILTINS = {"t", "year", "period_start", "period_end"}


def tokenize(s):
    pos, out = 0, []
    s = s.strip()
    while pos < len(s):
        m = TOKEN.match(s, pos)
        if not m:
            raise SyntaxError(f"bad token at {s[pos:]}")
        num, name, op = m.groups()
        out.append(("num", num) if num else ("name", name) if name else ("op", op))
        pos = m.end()
    return out


class Parser:
    def __init__(self, s):
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
            raise SyntaxError(f"trailing tokens {self.toks[self.i:]}")
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
                if val not in ALL_FUNCS:
                    raise SyntaxError(f"unknown function {val}")
                return ("call", val, args)
            return ("var", val)
        if val == "(":
            node = self.cmp()
            self.take(")")
            return node
        raise SyntaxError(f"unexpected {val}")


def parse(s):
    return Parser(s).parse()


def names_in(node, acc=None):
    acc = set() if acc is None else acc
    if node[0] == "var":
        acc.add(node[1])
    elif node[0] == "bin":
        names_in(node[2], acc); names_in(node[3], acc)
    elif node[0] == "neg":
        names_in(node[1], acc)
    elif node[0] == "call":
        for a in node[2]:
            names_in(a, acc)
    return acc


def funcs_in(node, acc=None):
    acc = set() if acc is None else acc
    if node[0] == "call":
        acc.add(node[1])
        for a in node[2]:
            funcs_in(a, acc)
    elif node[0] == "bin":
        funcs_in(node[2], acc); funcs_in(node[3], acc)
    elif node[0] == "neg":
        funcs_in(node[1], acc)
    return acc


# ---------------------------------------------------------------- Excel
class ExcelCtx:
    """Resolves ids to Excel references.

    refs: id -> ("scalar", defined_name) | ("series", sheet, row)
    col_letters: list of the 32 period column letters.
    t_ref(col) -> timeline reference for built-ins.
    """

    def __init__(self, refs, col_letters, timeline_rows, home_sheet):
        self.refs, self.cols, self.tl, self.home = refs, col_letters, timeline_rows, home_sheet

    def sheet_prefix(self, sheet):
        return "" if sheet == self.home else f"{sheet}!"

    def cell(self, ident, col):
        r = self.refs[ident]
        if r[0] == "scalar":
            return r[1]
        return f"{self.sheet_prefix(r[1])}{col}{r[2]}"

    def row_range(self, ident):
        r = self.refs[ident]
        if r[0] != "series":
            raise ValueError(f"{ident} must be a series")
        return f"{self.sheet_prefix(r[1])}${self.cols[0]}{r[2]}:${self.cols[-1]}{r[2]}"

    def row_range_to(self, ident, col):
        r = self.refs[ident]
        return f"{self.sheet_prefix(r[1])}${self.cols[0]}{r[2]}:{col}{r[2]}"

    def t(self, col):
        return f"Timeline!{col}${self.tl['t']}"

    def t_range(self):
        return f"Timeline!${self.cols[0]}${self.tl['t']}:${self.cols[-1]}${self.tl['t']}"


def to_excel(node, ctx, col):
    """col is a period column letter, or None for scalar rows."""
    k = node[0]
    if k == "num":
        return repr(node[1])
    if k == "var":
        name = node[1]
        if name in BUILTINS:
            if col is None:
                raise ValueError("built-in used in scalar row")
            return f"Timeline!{col}${ctx.tl[name]}"
        if ctx.refs[name][0] == "series" and col is None:
            raise ValueError(f"series {name} used in scalar context")
        return ctx.cell(name, col)
    if k == "neg":
        return f"(-{to_excel(node[1], ctx, col)})"
    if k == "bin":
        op = "=" if node[1] == "==" else node[1]
        return f"({to_excel(node[2], ctx, col)}{op}{to_excel(node[3], ctx, col)})"
    f, a = node[1], node[2]
    E = lambda n: to_excel(n, ctx, col)

    def ident(n):
        if n[0] != "var":
            raise ValueError(f"{f}() needs an id argument; add a row for the expression")
        return n[1]

    if f == "min":
        return f"MIN({E(a[0])},{E(a[1])})"
    if f == "max":
        return f"MAX({E(a[0])},{E(a[1])})"
    if f == "sum":
        return "SUM(" + ",".join(E(x) for x in a) + ")"
    if f == "ceiling":
        return f"CEILING({E(a[0])},1)"
    if f == "round":
        return f"ROUND({E(a[0])},{E(a[1])})"
    if f == "if":
        return f"IF({E(a[0])},{E(a[1])},{E(a[2])})"
    if f == "pow":
        return f"POWER({E(a[0])},{E(a[1])})"
    if f == "safe_divide":
        return f"IF(({E(a[1])})=0,{E(a[2])},({E(a[0])})/({E(a[1])}))"
    if f == "growth":
        return f"({E(a[0])})*(1+{E(a[1])})^({ctx.t(col)}-1)"
    if f == "step":
        return f"IF({ctx.t(col)}>={E(a[1])},{E(a[0])},0)"
    if f == "flag":
        return f"AND({ctx.t(col)}>={E(a[0])},{ctx.t(col)}<={E(a[1])})"
    if f == "spread":
        return f"IF(AND({ctx.t(col)}>={E(a[1])},{ctx.t(col)}<{E(a[1])}+{E(a[2])}),{E(a[0])}/{E(a[2])},0)"
    if f == "discount_factor":
        return f"1/(1+{E(a[0])})^{ctx.t(col)}"
    if f == "lag":
        x, n = ident(a[0]), E(a[1])
        return f"IF({ctx.t(col)}>{n},INDEX({ctx.row_range(x)},1,{ctx.t(col)}-{n}),0)"
    if f == "cumulative":
        x = ident(a[0])
        return f"({E(a[1])}+SUM({ctx.row_range_to(x, col)}))"
    if f == "running_max":
        x = ident(a[0])
        return f"MAX({ctx.row_range_to(x, col)})"
    if f == "depreciation_sl":
        x, life = ident(a[0]), E(a[1])
        tr = ctx.t_range()
        return (f"SUMPRODUCT(({tr}<={ctx.t(col)})*({tr}>{ctx.t(col)}-{life}),{ctx.row_range(x)})/{life}")
    if f == "total":
        return f"SUM({ctx.row_range(ident(a[0]))})"
    if f == "npv":
        return f"NPV({E(a[0])},{ctx.row_range(ident(a[1]))})"
    if f == "irr":
        guess = f",{E(a[1])}" if len(a) > 1 else ""
        return f"IRR({ctx.row_range(ident(a[0]))}{guess})"
    raise ValueError(f"no Excel mapping for {f}")


# ---------------------------------------------------------------- numpy
class NpCtx:
    def __init__(self, env, t, year):
        self.env, self.t, self.year = env, t, year


def excel_round(x, n):
    m = 10.0 ** n
    return np.sign(x) * np.floor(np.abs(x) * m + 0.5) / m


def np_irr(x):
    x = np.asarray(x, dtype=float)
    k = np.arange(len(x))
    f = lambda r: np.sum(x / (1 + r) ** k)
    return brentq(f, -0.99, 10.0, xtol=1e-15, rtol=1e-15, maxiter=500)


def evaluate(node, c):
    k = node[0]
    if k == "num":
        return float(node[1])
    if k == "var":
        n = node[1]
        if n == "t":
            return c.t.astype(float)
        if n == "year":
            return c.year.astype(float)
        return c.env[n]
    if k == "neg":
        return -evaluate(node[1], c)
    if k == "bin":
        l, r = evaluate(node[2], c), evaluate(node[3], c)
        return {"+": lambda: l + r, "-": lambda: l - r, "*": lambda: l * r, "/": lambda: l / r,
                ">": lambda: l > r, "<": lambda: l < r, ">=": lambda: l >= r, "<=": lambda: l <= r,
                "==": lambda: l == r}[node[1]]()
    f, a = node[1], node[2]
    V = lambda i: evaluate(a[i], c)
    t = c.t.astype(float)
    if f == "min":
        return np.minimum(V(0), V(1))
    if f == "max":
        return np.maximum(V(0), V(1))
    if f == "sum":
        out = 0.0
        for i in range(len(a)):
            out = out + V(i)
        return out
    if f == "ceiling":
        return np.ceil(V(0))
    if f == "round":
        return excel_round(V(0), V(1))
    if f == "if":
        return np.where(V(0), V(1), V(2))
    if f == "pow":
        return np.power(V(0), V(1))
    if f == "safe_divide":
        num, den, fb = V(0), V(1), V(2)
        den_arr = np.asarray(den, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(den_arr == 0, fb, num / np.where(den_arr == 0, 1.0, den_arr))
    if f == "growth":
        return V(0) * (1 + V(1)) ** (t - 1)
    if f == "step":
        return np.where(t >= V(1), V(0), 0.0)
    if f == "flag":
        return (t >= V(0)) & (t <= V(1))
    if f == "spread":
        s, n = V(1), V(2)
        return np.where((t >= s) & (t < s + n), V(0) / n, 0.0)
    if f == "discount_factor":
        return 1.0 / (1 + V(0)) ** t
    if f == "lag":
        x, n = np.asarray(V(0), dtype=float), int(V(1))
        out = np.zeros_like(x)
        if n < len(x):
            out[n:] = x[:len(x) - n]
        return out
    if f == "cumulative":
        return V(1) + np.cumsum(V(0))
    if f == "running_max":
        return np.maximum.accumulate(np.asarray(V(0), dtype=float))
    if f == "depreciation_sl":
        # independent vintage implementation: each period's capex over `life` periods
        capex, life = np.asarray(V(0), dtype=float), int(V(1))
        out = np.zeros_like(capex)
        for k_, amt in enumerate(capex):
            out[k_:k_ + life] += amt / life
        return out
    if f == "total":
        return float(np.sum(V(0)))
    if f == "npv":
        r, x = V(0), np.asarray(V(1), dtype=float)
        return float(sum(x[i] / (1 + r) ** (i + 1) for i in range(len(x))))
    if f == "irr":
        return float(np_irr(V(0)))
    raise ValueError(f"no numpy mapping for {f}")
