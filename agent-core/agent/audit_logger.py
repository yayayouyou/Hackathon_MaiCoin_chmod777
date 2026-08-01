"""
agent/audit_logger.py

不可變決策審計日誌模組 (Immutable Decision Audit Trail)
=====================================================
記錄 Agent 每一次決策循環的完整推理路徑，包括：
  - trace_id: 唯一追蹤 ID
  - 每一步工具調用的名稱、參數、結果摘要
  - 最終決策與信心水平
  - 風控校驗結果

日誌以 JSONL (JSON Lines) 格式寫入，每行一個完整的決策記錄，
便於後續合規審計、回溯與性能分析。
"""

import os
import json
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from loguru import logger

# 審計日誌存放路徑
AUDIT_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "audit_logs"
)
AUDIT_LOG_FILE = os.path.join(AUDIT_LOG_DIR, "decisions.jsonl")

# 確保目錄存在
os.makedirs(AUDIT_LOG_DIR, exist_ok=True)


def _load_last_chain_hash() -> Optional[str]:
    """
    讀取現有審計日誌最後一筆的 chain_hash，作為新一筆的 prev_hash。
    若檔案不存在或損毀則回傳 None（代表這是鏈的第一筆 / genesis）。
    """
    if not os.path.exists(AUDIT_LOG_FILE):
        return None
    last_hash: Optional[str] = None
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    last_hash = rec.get("chain_hash") or last_hash
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"讀取審計鏈上一筆哈希失敗: {e}")
        return None
    return last_hash


class AuditTrail:
    """
    單次決策會話的審計追蹤器。
    在 Agent 開始處理用戶請求時建立，結束時寫入日誌。
    """
    
    def __init__(self, user_query: str, model_name: str, persona: str = "default"):
        self.trace_id = str(uuid.uuid4())[:12]
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.user_query = user_query
        self.model_name = model_name
        self.persona = persona
        self.reasoning_steps: List[Dict[str, Any]] = []
        self.final_decision: Optional[str] = None
        self.total_steps = 0
        # 從磁碟載入上一筆紀錄的 chain_hash，讓雜湊鏈真正跨會話串接（防竄改鏈）
        self._prev_hash: Optional[str] = _load_last_chain_hash()
    
    def log_tool_call(self, tool_name: str, args: Dict[str, Any], result_summary: str, success: bool = True):
        """記錄一次工具調用"""
        self.total_steps += 1
        step = {
            "step": self.total_steps,
            "tool": tool_name,
            "args": _sanitize_args(args),
            "result_summary": result_summary[:500],  # 限制摘要長度
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.reasoning_steps.append(step)
    
    def log_thought(self, thought_content: str):
        """記錄大腦的一次思考輸出（非工具調用）"""
        self.total_steps += 1
        step = {
            "step": self.total_steps,
            "type": "thought",
            "content_preview": thought_content[:300],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.reasoning_steps.append(step)
    
    def set_final_decision(self, decision: str):
        """設定最終決策輸出"""
        self.final_decision = decision[:1000]
    
    def finalize_and_write(self) -> Dict[str, Any]:
        """
        組裝完整的審計記錄，計算加密哈希以確保不可變性，並寫入 JSONL 文件。
        """
        record = {
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "model": self.model_name,
            "persona": self.persona,
            "user_query": self.user_query[:500],
            "total_steps": len(self.reasoning_steps),
            "reasoning_steps": self.reasoning_steps,
            "final_decision_preview": self.final_decision,
        }
        
        # 計算記錄哈希以確保完整性 (鏈式哈希)
        record_json = json.dumps(record, ensure_ascii=False, sort_keys=True)
        current_hash = hashlib.sha256(record_json.encode("utf-8")).hexdigest()
        
        # 鏈式哈希：包含上一條記錄的哈希
        if self._prev_hash:
            chain_input = self._prev_hash + current_hash
            record["chain_hash"] = hashlib.sha256(chain_input.encode("utf-8")).hexdigest()
        else:
            record["chain_hash"] = current_hash
        
        record["record_hash"] = current_hash
        
        # 寫入 JSONL
        try:
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.info(f"審計日誌已寫入: trace_id={self.trace_id}, steps={len(self.reasoning_steps)}")
        except Exception as e:
            logger.error(f"審計日誌寫入失敗: {e}")
        
        return record


def _sanitize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    移除敏感參數（如 API 金鑰、密碼），只保留安全的參數摘要。
    """
    sanitized = {}
    sensitive_keys = {"api_key", "secret", "password", "token", "private_key"}
    for k, v in args.items():
        if k.lower() in sensitive_keys:
            sanitized[k] = "***REDACTED***"
        elif isinstance(v, str) and len(v) > 200:
            sanitized[k] = v[:200] + "...[truncated]"
        else:
            sanitized[k] = v
    return sanitized


def get_recent_audit_records(limit: int = 20) -> List[Dict[str, Any]]:
    """
    讀取最近的 N 條審計記錄。
    """
    if not os.path.exists(AUDIT_LOG_FILE):
        return []
    
    records = []
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error(f"讀取審計日誌失敗: {e}")
    
    return records[-limit:]
