"""
skills/execution/schemas.py

模塊六：交易執行與風控 Tool JSON Schema 定義
=============================================
定義本模塊所有函數的 OpenAI-compatible JSON Schema。
"""

# ──────────────────────────────────────────────
#  Schema 1：create_order
# ──────────────────────────────────────────────
CREATE_ORDER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_order",
        "description": (
            "【交易下單】在指定交易所下單買入或賣出加密貨幣。此操作涉及真實資金交易。"
            "下單前會自動檢查最新報價與底層物理風控鎖限制（如單筆 TWD 限額 50,000，滑點限額 3%），"
            "若違反風控規則將自動攔截拒絕委託。"
            "例如：'以 2,000,000 限價買入 0.01 BTC' 或 '幫我市價賣出 0.5 ETH'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exchange_id": {
                    "type": "string",
                    "description": "交易所 ID，目前現貨交易僅支援 'max'",
                    "enum": ["max"],
                    "default": "max"
                },
                "market": {
                    "type": "string",
                    "description": "交易對符號，例如 'BTC/TWD' 或 'btctwd'"
                },
                "side": {
                    "type": "string",
                    "description": "交易方向，'buy' 代表買入，'sell' 代表賣出",
                    "enum": ["buy", "sell"]
                },
                "volume": {
                    "type": "number",
                    "description": "委託下單的交易數量"
                },
                "price": {
                    "type": "number",
                    "description": "限價委託價格。如果委託類型為 'market' (市價單) 則不需填寫。"
                },
                "ord_type": {
                    "type": "string",
                    "description": "委託委託類型。'limit' 代表限價委託，'market' 代表市價委託",
                    "enum": ["limit", "market"],
                    "default": "limit"
                }
            },
            "required": ["exchange_id", "market", "side", "volume"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 2：cancel_order
# ──────────────────────────────────────────────
CANCEL_ORDER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "cancel_order",
        "description": "【撤單】撤銷指定交易所的單筆活動掛單。",
        "parameters": {
            "type": "object",
            "properties": {
                "exchange_id": {
                    "type": "string",
                    "description": "交易所 ID，目前僅支援 'max'",
                    "enum": ["max"],
                    "default": "max"
                },
                "order_id": {
                    "type": "integer",
                    "description": "要撤銷的訂單 ID"
                }
            },
            "required": ["exchange_id", "order_id"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 3：cancel_all_orders
# ──────────────────────────────────────────────
CANCEL_ALL_ORDERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "cancel_all_orders",
        "description": "【全撤】撤銷指定交易所在特定市場或全市場的所有活動掛單。",
        "parameters": {
            "type": "object",
            "properties": {
                "exchange_id": {
                    "type": "string",
                    "description": "交易所 ID，目前僅支援 'max'",
                    "enum": ["max"],
                    "default": "max"
                },
                "market": {
                    "type": "string",
                    "description": "選填。僅撤銷特定交易對（例如 'BTC/TWD'）的所有掛單。如果不填則撤銷該交易所全市場的所有掛單。"
                },
                "confirm_all_markets": {
                    "type": "boolean",
                    "description": "未指定 market 要撤銷『全市場所有掛單』（含止損/止盈保護單）時的防呆確認，需明確 true 才會執行。",
                    "default": False
                }
            },
            "required": ["exchange_id"]
        }
    }
}

# ──────────────────────────────────────────────
#  統一工具清單與映射
# ──────────────────────────────────────────────
EXECUTION_TOOLS = [
    CREATE_ORDER_SCHEMA,
    CANCEL_ORDER_SCHEMA,
    CANCEL_ALL_ORDERS_SCHEMA,
]

EXECUTION_TOOL_MAP = {
    "create_order":       "skills.execution.order_executor.create_order",
    "cancel_order":       "skills.execution.order_executor.cancel_order",
    "cancel_all_orders":  "skills.execution.order_executor.cancel_all_orders",
}

GET_TRADING_GUARD_STATUS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_trading_guard_status",
        "description": "查看實盤交易防線的目前狀態：生效模式（模擬/實盤/已停手）、授權剩餘時間、"
                       "全域停止開關、近期累計曝險（金額與筆數對上限），以及最近的下單決策紀錄"
                       "（含被風控擋下的）。用於回答：現在是實盤還是模擬？我今天下了多少？"
                       "為什麼那筆單被擋？交易有沒有被停掉？",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "回傳最近幾筆決策紀錄，預設 20", "default": 20},
            },
            "required": [],
        },
    },
}

EXECUTION_TOOLS = EXECUTION_TOOLS + [GET_TRADING_GUARD_STATUS_SCHEMA]
