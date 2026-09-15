"""Versioned Python subset interpreted as data, never executed by Python.

signal(history) receives a list of past closes. Grammar: assignments, return,
if, numeric/list expressions, slices, arithmetic, comparisons and seven pure
aggregations. No imports, attributes, comprehensions, loops, recursion or I/O.
The AST allowlist is the security boundary, not a prompt or regex blacklist.
"""

import ast
import math
import operator
from collections.abc import Callable
from typing import Any

GRAMMAR = "signal-python-v1"
FUNCTIONS = {
    "len": len,
    "sum": sum,
    "min": min,
    "max": max,
    "abs": abs,
    "float": float,
    "round": round,
}
ALLOWED = (
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Assign,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Return,
    ast.If,
    ast.Expr,
    ast.Constant,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.BoolOp,
    ast.IfExp,
    ast.Call,
    ast.Subscript,
    ast.Slice,
    ast.List,
    ast.Tuple,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.And,
    ast.Or,
)


class Program:
    def __init__(self, source: str):
        if len(source.encode()) > 16_384:
            raise ValueError("PROGRAM_TOO_LARGE")
        try:
            tree = ast.parse(source)
        except (SyntaxError, RecursionError) as exc:
            raise ValueError("PROGRAM_SYNTAX") from exc
        nodes = list(ast.walk(tree))
        if len(nodes) > 512 or any(not isinstance(n, ALLOWED) for n in nodes):
            raise ValueError("PROGRAM_GRAMMAR")
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            raise ValueError("ONE_SIGNAL_FUNCTION_REQUIRED")
        fn = tree.body[0]
        if (
            fn.name != "signal"
            or fn.decorator_list
            or fn.returns
            or fn.type_params
            or len(fn.args.args) != 1
            or fn.args.args[0].arg != "history"
            or fn.args.args[0].annotation
            or fn.args.posonlyargs
            or fn.args.kwonlyargs
            or fn.args.vararg
            or fn.args.kwarg
            or fn.args.defaults
        ):
            raise ValueError("SIGNATURE_SIGNAL_HISTORY_REQUIRED")
        for n in nodes:
            if isinstance(n, ast.FunctionDef) and n is not fn:
                raise ValueError("NESTED_FUNCTION_FORBIDDEN")
            if isinstance(n, ast.Name) and (n.id.startswith("_") or len(n.id) > 40):
                raise ValueError("INVALID_NAME")
            if isinstance(n, ast.Constant) and (
                type(n.value) not in (int, float, bool) or abs(n.value) > 1e12  # type: ignore[arg-type]
            ):
                raise ValueError("NUMERIC_CONSTANT_REQUIRED")
            if isinstance(n, ast.Call) and (
                not isinstance(n.func, ast.Name) or n.func.id not in FUNCTIONS or n.keywords
            ):
                raise ValueError("PURE_FUNCTION_REQUIRED")
            if isinstance(n, ast.Assign) and (
                len(n.targets) != 1
                or not isinstance(n.targets[0], ast.Name)
                or n.targets[0].id in {*FUNCTIONS, "history", "signal"}
            ):
                raise ValueError("LOCAL_ASSIGNMENT_REQUIRED")
        self.body = fn.body

    def signal(self, history: list[float]) -> float:
        if not history or len(history) > 10_000:
            raise ValueError("HISTORY_BOUND")
        env: dict[str, Any] = {"history": tuple(history)}
        fuel = [2048]

        def value(n: ast.AST) -> Any:
            fuel[0] -= 1
            if fuel[0] < 0:
                raise ValueError("PROGRAM_BUDGET")
            result: Any
            if isinstance(n, ast.Constant):
                result = n.value
            elif isinstance(n, ast.Name):
                result = env[n.id]
            elif isinstance(n, (ast.List, ast.Tuple)):
                result = tuple(value(x) for x in n.elts)
                if any(type(item) not in (int, float, bool) for item in result):
                    raise ValueError("FLAT_NUMERIC_SEQUENCE_REQUIRED")
            elif isinstance(n, ast.Subscript):
                result = value(n.value)[value(n.slice)]
            elif isinstance(n, ast.Slice):
                result = slice(*(int(value(x)) if x else None for x in (n.lower, n.upper, n.step)))
            elif isinstance(n, ast.Call):
                if not isinstance(n.func, ast.Name):
                    raise ValueError("FUNCTION_REQUIRED")
                result = FUNCTIONS[n.func.id](*(value(x) for x in n.args))  # type: ignore[operator]
            elif isinstance(n, ast.UnaryOp):
                operand = value(n.operand)
                result = (
                    -operand
                    if isinstance(n.op, ast.USub)
                    else +operand
                    if isinstance(n.op, ast.UAdd)
                    else not operand
                )
            elif isinstance(n, ast.BinOp):
                left, right = value(n.left), value(n.right)
                if type(left) not in (int, float, bool) or type(right) not in (int, float, bool):
                    raise ValueError("NUMERIC_ARITHMETIC_ONLY")
                if isinstance(n.op, ast.Add):
                    result = left + right
                elif isinstance(n.op, ast.Sub):
                    result = left - right
                elif isinstance(n.op, ast.Mult):
                    result = left * right
                else:
                    result = left / right
            elif isinstance(n, ast.Compare):
                left = value(n.left)
                result = True
                for op, rhs in zip(n.ops, n.comparators, strict=True):
                    right = value(rhs)
                    if type(left) not in (int, float, bool) or type(right) not in (
                        int,
                        float,
                        bool,
                    ):
                        raise ValueError("NUMERIC_COMPARISON_REQUIRED")
                    comparisons: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
                        ast.Eq: operator.eq,
                        ast.NotEq: operator.ne,
                        ast.Lt: operator.lt,
                        ast.LtE: operator.le,
                        ast.Gt: operator.gt,
                        ast.GtE: operator.ge,
                    }
                    if not comparisons[type(op)](left, right):
                        result = False
                        break
                    left = right
            elif isinstance(n, ast.BoolOp):
                result = (
                    all(value(x) for x in n.values)
                    if isinstance(n.op, ast.And)
                    else any(value(x) for x in n.values)
                )
            elif isinstance(n, ast.IfExp):
                result = value(n.body if value(n.test) else n.orelse)
            else:
                raise ValueError("UNSUPPORTED_EXPRESSION")
            if type(result) in (float, int) and (not math.isfinite(result) or abs(result) > 1e15):
                raise ValueError("NUMERIC_BOUND")
            return result

        def statements(body: list[ast.stmt]) -> Any:
            for statement in body:
                if isinstance(statement, ast.Return):
                    if statement.value is None:
                        raise ValueError("SIGNAL_REQUIRED")
                    return value(statement.value)
                if isinstance(statement, ast.Assign):
                    target = statement.targets[0]
                    if not isinstance(target, ast.Name):
                        raise ValueError("LOCAL_REQUIRED")
                    env[target.id] = value(statement.value)
                elif isinstance(statement, ast.If):
                    outcome = statements(
                        statement.body if value(statement.test) else statement.orelse
                    )
                    if outcome is not None:
                        return outcome
                else:
                    raise ValueError("UNSUPPORTED_STATEMENT")
            return None

        try:
            result = statements(self.body)
            if (
                type(result) not in (int, float)
                or not math.isfinite(result)
                or not 0 <= result <= 1
            ):
                raise ValueError("SIGNAL_MUST_BE_FRACTION")
            return float(result)
        except (ArithmeticError, LookupError, TypeError, RecursionError) as exc:
            raise ValueError("PROGRAM_RUNTIME") from exc
