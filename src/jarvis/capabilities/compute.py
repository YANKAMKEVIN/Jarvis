"""Local, deterministic calculations and unit conversions (no network).

Arithmetic is evaluated from a restricted AST (never Python eval), so only
numbers, the basic operators and a small set of math functions are allowed.
Unit conversions use a static table; currency is intentionally excluded (it
needs live rates -- use the web search for that).
"""

from __future__ import annotations

import ast
import math
import operator

from jarvis.capabilities.results import ToolResult


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "floor": math.floor,
    "ceil": math.ceil, "log": math.log, "log10": math.log10, "exp": math.exp,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "min": min, "max": max,
    "pow": pow,
}
_CONSTS = {"pi": math.pi, "e": math.e}
_MAX_POW_EXPONENT = 1000  # guards against 10**10**10 style blowups

# Conversion factors to a base unit per dimension. Temperature is handled apart.
_LENGTH = {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "mi": 1609.344,
           "mile": 1609.344, "miles": 1609.344, "yd": 0.9144, "ft": 0.3048,
           "in": 0.0254, "inch": 0.0254}
_MASS = {"g": 1.0, "kg": 1000.0, "mg": 0.001, "lb": 453.59237, "lbs": 453.59237,
         "oz": 28.349523125, "t": 1_000_000.0}
_VOLUME = {"l": 1.0, "ml": 0.001, "cl": 0.01, "gal": 3.785411784, "pt": 0.473176473}
_DIMENSIONS = {"length": _LENGTH, "mass": _MASS, "volume": _VOLUME}


class ComputeError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


class ComputeCapability:
    def calculate(self, expression: str) -> ToolResult:
        if not isinstance(expression, str) or not expression.strip():
            return ToolResult.failure(
                action="calculate", message="L'expression est vide.",
                error_code="invalid_expression",
            )
        try:
            value = _safe_eval(expression)
        except ComputeError as error:
            return ToolResult.failure(action="calculate", message=error.message, error_code=error.code)
        except Exception:
            return ToolResult.failure(
                action="calculate",
                message="Je n'ai pas pu calculer cette expression.",
                error_code="invalid_expression",
            )
        pretty = _format_number(value)
        return ToolResult.success(
            action="calculate",
            message=f"Le resultat est {pretty}.",
            expression=expression.strip(),
            result=value,
            result_text=pretty,
        )

    def convert_units(self, value: float, from_unit: str, to_unit: str) -> ToolResult:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return ToolResult.failure(
                action="convert_units", message="La valeur a convertir est invalide.",
                error_code="invalid_value",
            )
        src = _normalize_unit(from_unit)
        dst = _normalize_unit(to_unit)

        try:
            converted = _convert(number, src, dst)
        except ComputeError as error:
            return ToolResult.failure(action="convert_units", message=error.message, error_code=error.code)

        pretty = _format_number(converted)
        return ToolResult.success(
            action="convert_units",
            message=f"{_format_number(number)} {from_unit} = {pretty} {to_unit}.",
            value=number,
            from_unit=src,
            to_unit=dst,
            result=converted,
            result_text=pretty,
        )


def _safe_eval(expression: str) -> float:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        raise ComputeError("Expression invalide.", "invalid_expression")
    return _eval_node(tree.body)


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ComputeError("Seuls les nombres sont permis.", "invalid_expression")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POW_EXPONENT:
            raise ComputeError("Exposant trop grand.", "value_too_large")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        args = [_eval_node(arg) for arg in node.args]
        return _FUNCS[node.func.id](*args)
    raise ComputeError("Element non autorise dans l'expression.", "invalid_expression")


def _normalize_unit(unit: str) -> str:
    return unit.strip().lower() if isinstance(unit, str) else ""


def _convert(value: float, src: str, dst: str) -> float:
    if src in _TEMPERATURE or dst in _TEMPERATURE:
        if src not in _TEMPERATURE or dst not in _TEMPERATURE:
            raise ComputeError("Conversion de temperature incompatible.", "incompatible_units")
        return _convert_temperature(value, src, dst)
    for table in _DIMENSIONS.values():
        if src in table and dst in table:
            return value * table[src] / table[dst]
    raise ComputeError(
        "Unites inconnues ou de dimensions differentes.", "incompatible_units"
    )


_TEMPERATURE = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}


def _convert_temperature(value: float, src: str, dst: str) -> float:
    # to Celsius
    if src in ("c", "celsius"):
        celsius = value
    elif src in ("f", "fahrenheit"):
        celsius = (value - 32) * 5 / 9
    else:  # kelvin
        celsius = value - 273.15
    if dst in ("c", "celsius"):
        return celsius
    if dst in ("f", "fahrenheit"):
        return celsius * 9 / 5 + 32
    return celsius + 273.15


def _format_number(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    rounded = round(value, 4)
    text = f"{rounded}"
    return text.rstrip("0").rstrip(".") if "." in text else text
