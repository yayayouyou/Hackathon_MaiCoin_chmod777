"""
skills/gold/schemas.py — 黃金資料層 Tool JSON Schema 定義
=======================================================
OpenAI-compatible function schema，供 LLM 工具調用與 mcp_server 曝露。
"""

GET_GOLD_PRICE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_gold_price",
        "description": (
            "【黃金·免Key】獲取代幣化黃金 PAXG 與 XAUT 的即時報價、24 小時漲跌與市值（各錨定 1 金衡盎司黃金，"
            "單價≈黃金現貨每盎司價），並回傳兩者價差。用於『現在黃金/金價多少』或 MAX 黃金交易對報價。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vs_currency": {"type": "string", "description": "報價貨幣，如 'usd'、'twd'，預設 'usd'", "default": "usd"},
            },
        },
    },
}

GET_GOLD_MACRO_CONTEXT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_gold_macro_context",
        "description": (
            "【黃金·需FRED免費Key】獲取黃金總經驅動脈絡：10年實質利率、美元指數、政策利率、CPI 年增與倫敦金定盤，"
            "各附對黃金的方向影響（順風/逆風）與一個月趨勢，並彙整總經體制。回答『黃金為什麼漲跌』。"
            "缺 Key 時回傳啟用指引而非報錯。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

ANALYZE_GOLD_MARKET_SCHEMA = {
    "type": "function",
    "function": {
        "name": "analyze_gold_market",
        "description": (
            "【黃金·綜合】黃金市場綜合簡報：整合代幣化報價 (PAXG/XAUT)、總經體制（實質利率/美元…）、"
            "黃金與 BTC 的滾動相關性（檢驗『數位黃金』敘事此刻成不成立）、以及代幣化溢價，產出結構化判讀。"
            "適用『幫我看黃金現在狀況 / 該不該布局黃金』。僅供佐證、不自動下單。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exchange_id": {"type": "string", "description": "計算相關性用的行情交易所，預設 'binance'", "default": "binance"},
                "tokenized_symbol": {"type": "string", "description": "代幣化黃金交易對，預設 'PAXG/USDT'", "default": "PAXG/USDT"},
                "corr_days": {"type": "integer", "description": "黃金-BTC 相關性回看天數，預設 30", "default": 30},
            },
        },
    },
}

GOLD_TOOLS = [
    GET_GOLD_PRICE_SCHEMA,
    GET_GOLD_MACRO_CONTEXT_SCHEMA,
    ANALYZE_GOLD_MARKET_SCHEMA,
]

GOLD_TOOL_MAP = {
    "get_gold_price":          "skills.gold.tokenized_gold.get_gold_price",
    "get_gold_macro_context":  "skills.gold.macro.get_gold_macro_context",
    "analyze_gold_market":     "skills.gold.gold_analysis.analyze_gold_market",
}
