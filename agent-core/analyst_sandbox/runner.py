"""
analyst_sandbox/runner.py — 沙盒子行程進入點（獨立行程，無金鑰、受限 exec）
=====================================================
以【乾淨環境】被 sandbox.py 啟動。從 stdin 讀使用者分析程式，在受限命名空間執行：
  - 移除 __import__ / open / eval / compile / input → 無法 import 任何模組、開檔、二次 eval
  - 提供 np / pd / math / statistics + call_skill(name, **kwargs)（經 socket RPC 由父行程取資料）
  - 使用者把結論賦值給 `result`

本檔刻意『不匯入專案任何 skills 模組』（那會把金鑰載入本行程）。金鑰不存在於此行程。
"""

import sys
import json
import struct
import io
import contextlib
import traceback
import builtins as _builtins

_SOCK_FD = int(sys.argv[1])
import socket  # noqa: E402  只用於與父行程通訊的既有 fd（非對外連線）
_sock = socket.socket(fileno=_SOCK_FD)


def _readn(n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = _sock.recv(n - len(buf))
        if not chunk:
            raise EOFError("與父行程連線中斷")
        buf += chunk
    return buf


def _send(obj) -> None:
    b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    _sock.sendall(struct.pack(">I", len(b)) + b)


def _recv():
    n = struct.unpack(">I", _readn(4))[0]
    return json.loads(_readn(n).decode("utf-8"))


def call_skill(name, **kwargs):
    """沙盒內取得唯讀 skill 資料：實際由父行程(持金鑰)執行，只回傳資料。"""
    _send({"op": "call", "name": name, "kwargs": kwargs})
    resp = _recv()
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "skill 呼叫失敗"))
    return resp["data"]


# ── 受控 import：只開放『純運算』庫；os/socket/requests/subprocess 等 I/O 系統庫一律擋 ──
_ALLOWED_IMPORT_ROOTS = {
    "numpy", "pandas", "math", "statistics", "datetime", "collections",
    "itertools", "functools", "operator", "re", "json", "random",
    "decimal", "fractions", "heapq", "bisect", "cmath",
    "scipy", "statsmodels", "sklearn",   # 若已安裝即可用（純運算）；未裝則回清楚的 ModuleNotFound
}
_real_import = _builtins.__import__


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = (name or "").split(".")[0]
    if level == 0 and root in _ALLOWED_IMPORT_ROOTS:
        return _real_import(name, globals, locals, fromlist, level)
    raise ImportError(
        f"分析沙盒不允許 import '{name}'（僅開放純運算庫，禁止 I/O/系統/網路庫）。"
        f"可用：{', '.join(sorted(_ALLOWED_IMPORT_ROOTS))}。需要其他套件請告知開發者評估加入。")


# ── 安全 builtins：白名單，移除 open/eval/compile/input/exec；__import__ 改用受控版 ──
_SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes", "callable",
    "chr", "complex", "dict", "divmod", "enumerate", "filter", "float", "format",
    "frozenset", "getattr", "hasattr", "hash", "hex", "int", "isinstance", "issubclass",
    "iter", "len", "list", "map", "max", "min", "next", "oct", "ord", "pow", "print",
    "range", "repr", "reversed", "round", "set", "slice", "sorted", "str", "sum",
    "tuple", "type", "zip",
    "True", "False", "None", "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "ZeroDivisionError", "StopIteration", "RuntimeError", "ArithmeticError",
    "AttributeError", "NotImplementedError", "OverflowError", "FloatingPointError",
]
_safe_builtins = {n: getattr(_builtins, n) for n in _SAFE_BUILTIN_NAMES if hasattr(_builtins, n)}
_safe_builtins["__import__"] = _guarded_import


def main() -> None:
    code = sys.stdin.read()
    # 安全計算模組（父行程已限制資源；此處僅注入純運算庫，不注入任何 skills/os/net）
    try:
        import numpy as np
        import pandas as pd
        import math
        import statistics
        import datetime
        import collections
        import itertools
        import functools
        import re
        import json as _json
        import random
    except Exception as e:  # noqa: BLE001
        _send({"op": "error", "error": f"分析環境載入失敗: {e}"})
        return

    ns = {
        "__builtins__": _safe_builtins,
        # 預先注入常用純運算庫（不 import 也能直接用；import 亦可經受控白名單）
        "np": np, "pd": pd, "math": math, "statistics": statistics,
        "datetime": datetime, "collections": collections, "itertools": itertools,
        "functools": functools, "re": re, "json": _json, "random": random,
        "call_skill": call_skill,
        "result": None,
    }
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            exec(code, ns)   # noqa: S102 — 受限命名空間 + 行程隔離 + 無金鑰
        _send({"op": "done", "result": _sanitize(ns.get("result")),
               "stdout": out.getvalue()[:4000]})
    except Exception as e:  # noqa: BLE001
        _send({"op": "error", "error": f"{type(e).__name__}: {e}",
               "trace": traceback.format_exc()[-1500:], "stdout": out.getvalue()[:2000]})


def _sanitize(obj, depth: int = 0):
    """把 result 轉 JSON-safe（numpy/pandas → 原生）。"""
    if depth > 12:
        return "…(too deep)"
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        return obj if (obj == obj and obj not in (float("inf"), float("-inf"))) else None
    tmod = type(obj).__module__
    if tmod.startswith("numpy"):
        try:
            return _sanitize(obj.item() if getattr(obj, "ndim", 1) == 0 else obj.tolist(), depth + 1)
        except Exception:  # noqa: BLE001
            return str(obj)
    if tmod.startswith("pandas"):
        try:
            return _sanitize(obj.to_dict() if hasattr(obj, "to_dict") else obj.tolist(), depth + 1)
        except Exception:  # noqa: BLE001
            return str(obj)
    if isinstance(obj, dict):
        return {str(k): _sanitize(v, depth + 1) for k, v in list(obj.items())[:2000]}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize(v, depth + 1) for v in list(obj)[:5000]]
    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except Exception:  # noqa: BLE001
            pass
    return str(obj)


if __name__ == "__main__":
    main()
