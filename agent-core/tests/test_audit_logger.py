"""
tests/test_audit_logger.py

不可變決策審計日誌單元測試
"""

import os
import json
import pytest
import tempfile
from unittest.mock import patch

from agent.audit_logger import AuditTrail, _sanitize_args, get_recent_audit_records


class TestAuditTrail:
    """審計追蹤器核心功能測試"""
    
    def test_create_audit_trail(self):
        """測試建立審計追蹤器"""
        audit = AuditTrail(user_query="分析 BTC", model_name="qwen2.5:7b", persona="buffett")
        assert len(audit.trace_id) == 12
        assert audit.user_query == "分析 BTC"
        assert audit.model_name == "qwen2.5:7b"
        assert audit.persona == "buffett"
        assert len(audit.reasoning_steps) == 0
    
    def test_log_tool_call(self):
        """測試記錄工具調用"""
        audit = AuditTrail(user_query="test", model_name="test_model")
        audit.log_tool_call(
            tool_name="get_ohlcv",
            args={"symbol": "BTC/USDT", "timeframe": "1d"},
            result_summary='{"close": [50000, 51000]}',
            success=True
        )
        assert len(audit.reasoning_steps) == 1
        step = audit.reasoning_steps[0]
        assert step["tool"] == "get_ohlcv"
        assert step["success"] is True
        assert step["step"] == 1
        
    def test_log_multiple_steps(self):
        """測試多步驟記錄"""
        audit = AuditTrail(user_query="test", model_name="test_model")
        audit.log_tool_call("tool_a", {}, "result_a", True)
        audit.log_thought("正在分析數據...")
        audit.log_tool_call("tool_b", {"key": "val"}, "result_b", True)
        
        assert len(audit.reasoning_steps) == 3
        assert audit.reasoning_steps[0]["step"] == 1
        assert audit.reasoning_steps[1]["step"] == 2
        assert audit.reasoning_steps[1]["type"] == "thought"
        assert audit.reasoning_steps[2]["step"] == 3

    def test_finalize_produces_valid_record(self):
        """測試最終記錄結構完整性"""
        audit = AuditTrail(user_query="分析 ETH", model_name="gemma3n")
        audit.log_tool_call("get_ticker", {"symbol": "ETH/USDT"}, '{"price": 3000}', True)
        audit.set_final_decision("建議買入 ETH")
        
        # Monkey-patch 寫入路徑避免影響真實日誌
        with patch("agent.audit_logger.AUDIT_LOG_FILE", os.path.join(tempfile.gettempdir(), "test_audit.jsonl")):
            record = audit.finalize_and_write()
        
        assert "trace_id" in record
        assert "timestamp" in record
        assert "model" in record
        assert "reasoning_steps" in record
        assert "record_hash" in record
        assert "chain_hash" in record
        assert record["model"] == "gemma3n"
        assert record["total_steps"] == 1
        assert record["final_decision_preview"] == "建議買入 ETH"

    def test_record_hash_is_sha256(self):
        """確認記錄哈希是有效的 SHA-256"""
        audit = AuditTrail(user_query="test", model_name="test")
        audit.set_final_decision("done")
        
        with patch("agent.audit_logger.AUDIT_LOG_FILE", os.path.join(tempfile.gettempdir(), "test_audit2.jsonl")):
            record = audit.finalize_and_write()
        
        assert len(record["record_hash"]) == 64  # SHA-256 = 64 hex chars
        assert all(c in "0123456789abcdef" for c in record["record_hash"])


class TestSanitizeArgs:
    """參數消毒功能測試"""
    
    def test_normal_args_pass_through(self):
        """正常參數應原樣通過"""
        args = {"symbol": "BTC/USDT", "timeframe": "1d"}
        result = _sanitize_args(args)
        assert result == args
    
    def test_sensitive_args_redacted(self):
        """敏感參數應被遮罩"""
        args = {"api_key": "sk-12345", "symbol": "BTC"}
        result = _sanitize_args(args)
        assert result["api_key"] == "***REDACTED***"
        assert result["symbol"] == "BTC"
    
    def test_long_string_truncated(self):
        """過長字串應被截斷"""
        args = {"data": "x" * 500}
        result = _sanitize_args(args)
        assert len(result["data"]) < 500
        assert result["data"].endswith("...[truncated]")
    
    def test_password_redacted(self):
        """密碼字段應被遮罩"""
        args = {"password": "mypass123", "host": "localhost"}
        result = _sanitize_args(args)
        assert result["password"] == "***REDACTED***"
        assert result["host"] == "localhost"


class TestGetRecentRecords:
    """測試讀取最近審計記錄"""
    
    def test_empty_when_no_file(self):
        """檔案不存在時應返回空列表"""
        with patch("agent.audit_logger.AUDIT_LOG_FILE", "/tmp/nonexistent_audit.jsonl"):
            records = get_recent_audit_records()
            assert records == []
    
    def test_limit_works(self):
        """limit 參數應限制返回數量"""
        # 創建臨時日誌文件
        tmp_file = os.path.join(tempfile.gettempdir(), "test_limit_audit.jsonl")
        with open(tmp_file, "w", encoding="utf-8") as f:
            for i in range(10):
                f.write(json.dumps({"trace_id": f"test-{i}"}) + "\n")
        
        with patch("agent.audit_logger.AUDIT_LOG_FILE", tmp_file):
            records = get_recent_audit_records(limit=3)
            assert len(records) == 3
            # 應返回最後 3 條
            assert records[0]["trace_id"] == "test-7"
        
        # 清理
        os.unlink(tmp_file)
