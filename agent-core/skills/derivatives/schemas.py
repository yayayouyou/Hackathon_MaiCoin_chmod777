"""
skills/derivatives/schemas.py

模塊二：衍生品聚合與對比 Tool JSON Schema 定義
=============================================
定義本模塊所有函數對應的 OpenAI-compatible JSON Schema，方便 LLM 調用。
"""

# ──────────────────────────────────────────────
#  Schema 1：get_aggregated_funding_rate
# ──────────────────────────────────────────────
GET_AGGREGATED_FUNDING_RATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_aggregated_funding_rate",
        "description": (
            "獲取並對比多個主流期貨交易所（Binance, Bybit, OKX）的最新資金費率。"
            "提供平均費率、各所最新費率、跨所價差 (Spread)，並判斷市場整體情緒與發現無風險套利機會。"
            "例如：'分析一下當前 BTC 的資金費率與套利機會' 或 '比較一下 Binance 和 OKX 的 SOL 費率走勢'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": (
                        "交易對代碼，格式如 'BTC/USDT'、'ETH/USDT' 或 'SOL/USDT'。"
                        "背後會自動對應到各交易所的永續合約。未指定時預設 BTC/USDT。"
                    ),
                    "default": "BTC/USDT"
                }
            },
            "required": []
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 2：get_aggregated_open_interest
# ──────────────────────────────────────────────
GET_AGGREGATED_OPEN_INTEREST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_aggregated_open_interest",
        "description": (
            "獲取並對比多個交易所的即時持倉量 (Open Interest)。"
            "有助於分析全網主力與散戶的未平倉熱度對比。"
            "例如：'現在全網 BTC 的持倉量在各交易所是如何分佈的？'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "交易對代碼，例如 'BTC/USDT'、'ETH/USDT'。未指定時預設 BTC/USDT。",
                    "default": "BTC/USDT"
                }
            },
            "required": []
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 3：get_binance_open_interest_history
# ──────────────────────────────────────────────
GET_BINANCE_OPEN_INTEREST_HISTORY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_binance_open_interest_history",
        "description": (
            "獲取幣安 (Binance Futures) 的持倉量 (Open Interest) 歷史統計數據。"
            "包含持倉金額與數量的變化趨勢、首尾變動百分比，判斷持倉是上升、下降還是震盪走勢。"
            "例如：'幫我看一下過去 30 小時 BTC 在幣安的持倉量趨勢'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "交易對符號，例如 'BTC/USDT', 'ETH/USDT'"
                },
                "period": {
                    "type": "string",
                    "description": "時間間隔週期",
                    "enum": ["5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"],
                    "default": "1h"
                },
                "limit": {
                    "type": "integer",
                    "description": "獲取的數據長度上限，最大為 500",
                    "default": 30
                }
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 4：get_binance_long_short_ratio
# ──────────────────────────────────────────────
GET_BINANCE_LONG_SHORT_RATIO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_binance_long_short_ratio",
        "description": (
            "獲取幣安 (Binance Futures) 的全球多空帳戶比率歷史統計數據。"
            "可用於衡量市場整體散戶與大戶的倉位比率分佈，提供多空情緒標籤。"
            "例如：'BTC 當前的多空比是多少？多頭多還是空頭多？'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "交易對符號，例如 'BTC/USDT'"
                },
                "period": {
                    "type": "string",
                    "description": "時間週期",
                    "enum": ["5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"],
                    "default": "1h"
                },
                "limit": {
                    "type": "integer",
                    "description": "獲取數據的長度上限，最大為 500",
                    "default": 30
                }
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 5：get_bybit_open_interest_history
# ──────────────────────────────────────────────
GET_BYBIT_OPEN_INTEREST_HISTORY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_bybit_open_interest_history",
        "description": (
            "獲取 Bybit 交易所永續合約的持倉量 (Open Interest) 歷史統計數據。"
            "例如：'我想看 Bybit 上的 ETH 歷史持倉量變化'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "交易對符號，例如 'BTC/USDT'"
                },
                "interval": {
                    "type": "string",
                    "description": "時間週期",
                    "enum": ["5m", "15m", "30m", "1h", "4h", "1d"],
                    "default": "1h"
                },
                "limit": {
                    "type": "integer",
                    "description": "獲取數據長度上限，最大為 200",
                    "default": 30
                }
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 6：get_coinalyze_long_short_ratio（跨 ~25 所彙整，免限流）
# ──────────────────────────────────────────────
GET_COINALYZE_LONG_SHORT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coinalyze_long_short_ratio",
        "description": (
            "獲取跨 ~25 家交易所彙整的多空帳戶比（long/short account ratio），比單一交易所更能代表全市場情緒，"
            "且不受 Binance 統計端點權重限流影響（需一次性免費 Coinalyze 金鑰）。"
            "例如：'現在全市場散戶偏多還偏空？'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "幣種符號，例如 'BTC', 'ETH'"},
                "interval": {"type": "string", "description": "時間週期",
                             "enum": ["5m", "15m", "30m", "1h", "4h", "1d"], "default": "1h"},
                "limit": {"type": "integer", "description": "回溯桶數，預設 24", "default": 24},
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
#  Schema 7：get_coinalyze_predicted_funding（前瞻資金費）
# ──────────────────────────────────────────────
GET_COINALYZE_PREDICTED_FUNDING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_coinalyze_predicted_funding",
        "description": (
            "獲取跨所『預測』的下一期資金費率（前瞻信號）。正值＝多方將付費給空方（多頭擁擠、槓桿偏多）；"
            "負值反之。用於預判即將到來的資金成本與多空擁擠度（需一次性免費 Coinalyze 金鑰）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "幣種符號，例如 'BTC', 'ETH'"},
            },
            "required": ["symbol"]
        }
    }
}

# ──────────────────────────────────────────────
#  統一工具清單與映射
# ──────────────────────────────────────────────
DERIVATIVES_TOOLS = [
    GET_AGGREGATED_FUNDING_RATE_SCHEMA,
    GET_AGGREGATED_OPEN_INTEREST_SCHEMA,
    GET_BINANCE_OPEN_INTEREST_HISTORY_SCHEMA,
    GET_BINANCE_LONG_SHORT_RATIO_SCHEMA,
    GET_BYBIT_OPEN_INTEREST_HISTORY_SCHEMA,
    GET_COINALYZE_LONG_SHORT_SCHEMA,
    GET_COINALYZE_PREDICTED_FUNDING_SCHEMA,
]

DERIVATIVES_TOOL_MAP = {
    "get_aggregated_funding_rate":        "skills.derivatives.multi_exchange.get_aggregated_funding_rate",
    "get_aggregated_open_interest":       "skills.derivatives.multi_exchange.get_aggregated_open_interest",
    "get_binance_open_interest_history":  "skills.derivatives.binance_futures.get_binance_open_interest_history",
    "get_binance_long_short_ratio":       "skills.derivatives.binance_futures.get_binance_long_short_ratio",
    "get_bybit_open_interest_history":    "skills.derivatives.bybit_derivatives.get_bybit_open_interest_history",
    "get_coinalyze_long_short_ratio":     "skills.derivatives.coinalyze_client.get_coinalyze_long_short_ratio",
    "get_coinalyze_predicted_funding":    "skills.derivatives.coinalyze_client.get_coinalyze_predicted_funding",
}
