import ast
import operator
import re
from datetime import datetime

# Safe arithmetic evaluator — replaces eval()
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _safe_eval(expr: str) -> float:
    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_eval(node.operand))
        raise ValueError("unsupported expression")

    return _eval(ast.parse(expr, mode="eval").body)


class OfflineIntentPack:
    def handle(self, user_text: str):
        lower = user_text.lower().strip()

        if lower in ("hi", "hello", "hey"):
            return "Hello. I am here and ready to help.", True

        if "how are you" in lower:
            return "I am running well. How can I help right now?", True

        if "what can you do" in lower or "help" == lower:
            return (
                "I can handle alarms, time queries, routines, lights, and local music commands even in offline mode.",
                True,
            )

        if lower.startswith("calculate "):
            expr = lower.replace("calculate", "", 1).strip()
            if re.fullmatch(r"[0-9\s\+\-\*\/\(\)\.]+", expr):
                try:
                    value = _safe_eval(expr)
                    return f"The result is {value}.", True
                except Exception:
                    return "I could not calculate that expression.", True

        if "time" in lower and "now" in lower:
            return f"Local time is {datetime.now().strftime('%I:%M %p')}.", True

        return "", False
