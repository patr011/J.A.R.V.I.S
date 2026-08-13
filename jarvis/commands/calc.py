"""Calculadora.

Un modelo de lenguaje acierta casi siempre en las cuentas fáciles, pero
"casi siempre" no vale para una suma. Aquí se resuelven de verdad.

Se evalúa el árbol sintáctico de Python en lugar de usar `eval`, que
ejecutaría cualquier cosa que le escribieran: solo se permiten números y
operaciones aritméticas, nada de llamadas ni de acceso a variables.
"""

from __future__ import annotations

import ast
import math
import operator
import re

from .base import CommandResult, normalize

# Operaciones permitidas. Cualquier otra cosa se rechaza.
_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_FUNCTIONS = {
    "raiz": math.sqrt, "sqrt": math.sqrt,
    "abs": abs, "redondear": round, "round": round,
    "sen": math.sin, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log10, "ln": math.log,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}

# Cómo se dicen las operaciones hablando.
_WORD_OPERATORS = [
    (r"\bmas\b|\bsumado a\b|\by\b(?=\s*\d)", "+"),
    (r"\bmenos\b|\brestado\b", "-"),
    (r"\bpor\b|\bmultiplicado por\b|\bveces\b", "*"),
    (r"\bentre\b|\bdividido entre\b|\bdividido por\b|\bdividido\b", "/"),
    (r"\belevado a\b|\ba la potencia de\b", "**"),
    (r"\braiz cuadrada de\b|\braiz de\b", "raiz"),
    (r"\bcoma\b", "."),
]


class CalcError(ValueError):
    """La expresión no es una cuenta válida."""


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalcError("solo se admiten números")
        return node.value
    if isinstance(node, ast.BinOp):
        op = _BINARY.get(type(node.op))
        if op is None:
            raise CalcError("operación no permitida")
        right = _evaluate(node.right)
        if op in (operator.truediv, operator.floordiv, operator.mod) and right == 0:
            raise CalcError("no se puede dividir entre cero")
        # Un exponente enorme colgaria el programa calculando durante minutos.
        if op is operator.pow and abs(right) > 1000:
            raise CalcError("el exponente es demasiado grande")
        return op(_evaluate(node.left), right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARY.get(type(node.op))
        if op is None:
            raise CalcError("operación no permitida")
        return op(_evaluate(node.operand))
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise CalcError(f"no sé qué es «{node.id}»")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise CalcError("función no permitida")
        args = [_evaluate(a) for a in node.args]
        try:
            return _FUNCTIONS[node.func.id](*args)
        except (ValueError, TypeError) as exc:
            raise CalcError(str(exc)) from exc
    raise CalcError("no entiendo la expresión")


def to_expression(text: str) -> str:
    """Pasa lo que ha dicho el usuario a una expresión matemática."""
    expr = normalize(text)
    expr = re.sub(r"\b(cuanto es|cuanto son|calcula|calcular|resultado de|"
                  r"dime cuanto es|cuanto vale)\b", " ", expr)
    expr = expr.replace("×", "*").replace("÷", "/").replace(",", ".")

    # "el 20 por ciento de 350"  ->  "(20/100)*350"
    porcentaje = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|por ciento)\s*de\s*(\d+(?:\.\d+)?)", expr)
    if porcentaje:
        return f"({porcentaje.group(1)}/100)*{porcentaje.group(2)}"
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", expr)

    for pattern, symbol in _WORD_OPERATORS:
        expr = re.sub(pattern, f" {symbol} ", expr)

    # "raiz 16" -> "raiz(16)"
    expr = re.sub(r"\braiz\s*\(?\s*(\d+(?:\.\d+)?)\s*\)?", r"raiz(\1)", expr)
    return re.sub(r"\s+", " ", expr).strip(" ?¿.!¡")


def looks_like_math(text: str) -> bool:
    """¿Esto es una cuenta y no una frase cualquiera?"""
    expr = to_expression(text)
    if not expr or not re.search(r"\d", expr):
        return False
    # Tiene que haber al menos un operador y nada más que cuentas.
    if not re.search(r"[+\-*/%]|raiz|\*\*", expr):
        return False
    return bool(re.fullmatch(r"[\d\s+\-*/%.()]*(raiz|sqrt|abs|sen|sin|cos|tan|log|ln|pi|e)?"
                             r"[\d\s+\-*/%.()]*", expr))


def calculate(text: str) -> CommandResult:
    expr = to_expression(text)
    if not expr:
        return CommandResult.fail("¿Qué quiere que calcule?")
    try:
        tree = ast.parse(expr, mode="eval")
        value = _evaluate(tree)
    except CalcError as exc:
        return CommandResult.fail(f"No puedo con esa cuenta: {exc}.")
    except (SyntaxError, ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CommandResult.fail(f"No he entendido la operación «{expr}».")

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return CommandResult.fail("El resultado no es un número válido.")
        # 46.0 se lee mejor como 46; 3.333333 se recorta a 3.33.
        resultado = str(int(value)) if value == int(value) else f"{value:.4f}".rstrip("0").rstrip(".")
    else:
        resultado = str(value)

    return CommandResult.done(f"{expr.replace('**', '^')} = {resultado}", result=value)
