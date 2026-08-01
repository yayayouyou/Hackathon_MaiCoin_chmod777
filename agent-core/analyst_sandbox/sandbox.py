"""
analyst_sandbox/sandbox.py — run_analysis()：唯讀分析沙盒主 API
=====================================================
以【乾淨環境(無金鑰)】啟動 runner.py 子行程執行 agent 撰寫的分析程式；
透過 socketpair 服務其 skill 請求（skill 在本(父)行程用金鑰執行，只回資料）；
逾時 / 資源上限保護。金鑰與下單能力永不進入沙盒。
"""

import ast
import os
import sys
import json
import struct
import socket
import subprocess
import tempfile
from typing import Any, Dict, Optional

from loguru import logger

from analyst_sandbox import broker

_RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner.py")
_DEFAULT_TIMEOUT = 20
_MAX_CODE_BYTES = 20_000

# 與 runner.py 的 _ALLOWED_IMPORT_ROOTS 保持同步（此處為執行前的 AST 前置檢查，runner 的受控 import 為權威）
_AST_ALLOWED_ROOTS = {
    "numpy", "pandas", "math", "statistics", "datetime", "collections",
    "itertools", "functools", "operator", "re", "json", "random",
    "decimal", "fractions", "heapq", "bisect", "cmath", "scipy", "statsmodels", "sklearn",
}
_AST_FORBIDDEN_NAMES = {"eval", "exec", "compile", "open", "__import__", "input",
                        "globals", "locals", "vars", "breakpoint", "memoryview", "exit", "quit"}


def _strip_code_fence(code: str) -> str:
    """剝除模型常見的 markdown 圍欄（```python ... ```），避免純因圍欄導致 AST 語法失敗。
    活體 E2E 發現：gemma4 常把程式碼包在 ``` 內，沙盒應寬容處理。"""
    s = (code or "").strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]                 # 去掉開頭 ```lang 那一行
        s = s.rstrip()
        if s.endswith("```"):
            s = s[:-3].rstrip()            # 去掉結尾 ```
    return s


def _ast_check(code: str) -> Optional[str]:
    """執行前 AST 前置檢查：擋非白名單 import、dunder 屬性逃逸、危險內建名（防禦縱深 + 給模型更快回饋）。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"語法錯誤（第 {e.lineno} 行）：{e.msg}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _AST_ALLOWED_ROOTS:
                    return f"不允許 import '{a.name}'（僅開放純運算庫：{', '.join(sorted(_AST_ALLOWED_ROOTS))}）"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root not in _AST_ALLOWED_ROOTS:
                return f"不允許 from '{node.module}' import（僅開放純運算庫）"
        elif isinstance(node, ast.Attribute):
            if isinstance(node.attr, str) and node.attr.startswith("__") and node.attr.endswith("__"):
                return f"不允許存取 dunder 屬性 '{node.attr}'（沙盒逃逸防護）"
        elif isinstance(node, ast.Name) and node.id in _AST_FORBIDDEN_NAMES:
            return f"不允許使用 '{node.id}'（受限內建）"
    return None


def _clean_env(home: str) -> Dict[str, str]:
    """子行程的乾淨環境：只保留執行 python/numpy 所需，剝除所有金鑰與機密。"""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": home,
        "TMPDIR": home,
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "OPENBLAS_NUM_THREADS": "2",
        "MKL_NUM_THREADS": "2",
    }


def _preexec(timeout: int):
    def _fn():
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))       # 1 GB 記憶體
            resource.setrlimit(resource.RLIMIT_CPU, (int(timeout) + 3, int(timeout) + 3))  # CPU 秒
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))                    # 禁止寫檔（大小 0）
        except Exception:  # noqa: BLE001
            pass
        if sys.platform.startswith("linux"):
            try:  # 生產(Linux)：切斷子行程對外網路
                import ctypes
                libc = ctypes.CDLL("libc.so.6", use_errno=True)
                libc.unshare(0x40000000)  # CLONE_NEWNET
            except Exception:  # noqa: BLE001
                pass
    return _fn


def _recv_msg(sock: socket.socket, timeout: float):
    sock.settimeout(max(0.1, timeout))

    def _readn(n):
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise EOFError
            buf += chunk
        return buf
    n = struct.unpack(">I", _readn(4))[0]
    return json.loads(_readn(n).decode("utf-8"))


def _send_msg(sock: socket.socket, obj) -> None:
    b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack(">I", len(b)) + b)


def _terminate(proc) -> None:
    """確實殺掉並回收子行程（避免孤兒）。"""
    if proc is None:
        return
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
    try:
        proc.wait(timeout=2)
    except Exception:  # noqa: BLE001
        pass


def _drain_stderr(proc) -> str:
    """只在子行程已死後讀 stderr（此時 EOF 立即返回，不會阻塞）。"""
    try:
        return (proc.stderr.read() or b"").decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def run_analysis(code: str, goal: str = "", timeout: int = _DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """
    【LLM Tool】在唯讀分析沙盒中執行你臨場撰寫的 Python 分析程式（Code-as-Action）。

    可用：call_skill(name, **kwargs) 取任何唯讀資料 skill 的結果、np/pd/math/statistics 運算。
    把最終結論賦值給變數 `result`。沙盒【無網路、無金鑰、無下單能力】——僅供分析/校驗想法。

    Args:
        code : 要執行的 Python 分析程式。務必把結論賦值給 `result`。
        goal : （選填）這段分析的目的，供記錄。
        timeout : 逾時秒數（預設 20）。
    """
    if not isinstance(code, str) or not code.strip():
        return {"error": "code 不可為空。"}
    code = _strip_code_fence(code)   # 寬容處理模型常見的 ``` markdown 圍欄
    if len(code.encode("utf-8")) > _MAX_CODE_BYTES:
        return {"error": f"code 過長（>{_MAX_CODE_BYTES} bytes）。"}
    ast_err = _ast_check(code)   # 執行前 AST 前置檢查（不啟動子行程即擋下）
    if ast_err:
        return {"error": f"程式碼未通過沙盒 AST 檢查：{ast_err}", "goal": goal}
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT
    timeout = max(3, min(60, timeout))

    parent_sock, child_sock = socket.socketpair()
    home = tempfile.mkdtemp(prefix="analyst_sbx_")
    proc: Optional[subprocess.Popen] = None
    skill_calls = 0
    try:
        proc = subprocess.Popen(
            [sys.executable, _RUNNER, str(child_sock.fileno())],
            pass_fds=[child_sock.fileno()],
            env=_clean_env(home),
            cwd=home,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            preexec_fn=_preexec(timeout) if os.name == "posix" else None,
        )
        child_sock.close()
        try:
            proc.stdin.write(code.encode("utf-8"))
            proc.stdin.close()
        except BrokenPipeError:
            pass

        import time
        deadline = time.time() + timeout
        final = None
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                _terminate(proc)     # 先殺，避免後續讀 stderr 卡在存活子行程
                return {"error": f"分析逾時（>{timeout}s）——請縮小運算量或減少 skill 呼叫。", "skill_calls": skill_calls}
            try:
                msg = _recv_msg(parent_sock, remaining)
            except (socket.timeout, EOFError, ConnectionError, OSError):
                _terminate(proc)     # 先殺再讀 stderr（否則子行程存活時 read 會永久阻塞→孤兒）
                return {"error": "沙盒子行程中止（逾時/資源上限/崩潰）。",
                        "detail": _drain_stderr(proc)[:400], "skill_calls": skill_calls}
            op = msg.get("op")
            if op == "call":
                skill_calls += 1
                if skill_calls > 60:
                    _send_msg(parent_sock, {"ok": False, "error": "skill 呼叫次數過多（>60），請彙整查詢。"})
                    continue
                _send_msg(parent_sock, broker.execute(msg.get("name"), msg.get("kwargs")))
            elif op in ("done", "error"):
                final = msg
                break

        if final.get("op") == "error":
            return {"error": final.get("error", "分析程式執行錯誤"), "traceback": final.get("trace", ""),
                    "stdout": final.get("stdout", ""), "skill_calls": skill_calls, "goal": goal}
        return {
            "ok": True,
            "goal": goal,
            "result": final.get("result"),
            "stdout": final.get("stdout", ""),
            "skill_calls": skill_calls,
            "note": "唯讀分析沙盒（無金鑰/無下單）；結果為 agent 臨場程式計算所得。",
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"沙盒執行失敗: {e}")
        return {"error": f"沙盒啟動失敗: {e.__class__.__name__}: {str(e)[:120]}"}
    finally:
        try:
            parent_sock.close()
        except Exception:  # noqa: BLE001
            pass
        if proc and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                pass
        try:
            import shutil
            shutil.rmtree(home, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass


def list_skills() -> Dict[str, Any]:
    """回傳沙盒可 call_skill 的唯讀 skill 目錄（供 agent 參考）。"""
    return {"count": len(broker.whitelist()), "by_group": broker.catalog()}
