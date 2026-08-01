"""
agent/ollama_config.py

Ollama 連線設定 (從環境變數讀取，不硬編碼任何機密)
=====================================================
在此集中管理 Ollama host 與 (選填的) HTTP Basic Auth，避免把帳密/主機 IP
寫死在原始碼中而在開源時外洩。

環境變數：
  OLLAMA_HOST      Ollama 伺服器位址，預設 http://localhost:11434
  OLLAMA_USER      (選填) HTTP Basic Auth 使用者名稱
  OLLAMA_PASSWORD  (選填) HTTP Basic Auth 密碼
"""

import os
from typing import Optional, Tuple

from dotenv import load_dotenv

# override=True：讓專案 .env 的設定優先於作業系統既有的環境變數
# （例如安裝 Ollama 後系統常帶有 OLLAMA_HOST=0.0.0.0:11434，會蓋掉 .env）
load_dotenv(override=True)

DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def resolve_host(override: Optional[str] = None) -> str:
    """回傳要使用的 Ollama host。優先序：呼叫端傳入 > 環境變數 > localhost 預設。"""
    if override:
        return override
    return os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)


def resolve_auth() -> Optional[Tuple[str, str]]:
    """
    回傳 requests 用的 auth tuple；若未在環境變數設定使用者/密碼則回傳 None
    (代表該 Ollama 伺服器不需要 Basic Auth)。
    """
    user = os.getenv("OLLAMA_USER")
    password = os.getenv("OLLAMA_PASSWORD")
    if user and password:
        return (user, password)
    return None
