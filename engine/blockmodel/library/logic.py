"""Logic: Compare, If."""

import numpy as np

from ..types import Type, TypeRuleError, additive, result_shape
from .registry import Ctx, register

COMPARE_OPS = {
    ">": np.greater,
    ">=": np.greater_equal,
    "<": np.less,
    "<=": np.less_equal,
    "==": np.equal,
    "!=": np.not_equal,
}


def _op(ctx: Ctx) -> str:
    op = ctx.settings.get("op", ">")
    if op not in COMPARE_OPS:
        raise TypeRuleError(
            f"Operator {op!r} is not one of {' '.join(COMPARE_OPS)}. Pick one in the inspector."
        )
    return op


def _compare_infer(ctx: Ctx) -> dict[str, Type]:
    op = _op(ctx)
    a, b = ctx.types["a"], ctx.types["b"]
    if a.kind == "bool" and b.kind == "bool":
        if op not in ("==", "!="):
            raise TypeRuleError("TRUE/FALSE values can only be compared with == or !=. Change the operator.")
        return {"result": Type(result_shape(a, b), "bool")}
    shape = additive(a, b, "compare").shape
    return {"result": Type(shape, "bool")}


@register("logic.compare", _compare_infer)
def compare(ctx: Ctx, inputs):
    result = COMPARE_OPS[_op(ctx)](inputs["a"], inputs["b"])
    return {"result": result if np.ndim(result) else bool(result)}


def _if_infer(ctx: Ctx) -> dict[str, Type]:
    cond, then, other = ctx.types["condition"], ctx.types["then"], ctx.types["else"]
    if cond.kind != "bool":
        raise TypeRuleError("Input condition needs TRUE/FALSE values. Wire a Compare or Period flag block.")
    if then.kind == "bool" and other.kind == "bool":
        branch = Type(result_shape(then, other), "bool")
    else:
        branch = additive(then, other, "choose between")
    return {"result": branch.with_(shape=result_shape(cond, branch))}


@register("logic.if", _if_infer)
def if_(ctx: Ctx, inputs):
    result = np.where(inputs["condition"], inputs["then"], inputs["else"])
    if result.ndim:
        return {"result": result}
    return {"result": bool(result) if ctx.out["result"].kind == "bool" else float(result)}
