"""
skills/calculators/schemas.py

計算機技能 Tool JSON Schema 定義 (OpenAI-compatible)
=============================================
"""

CALCULATE_DCA_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculate_dca",
        "description": (
            "定期定額（DCA）回溯試算：模擬每期投入固定金額、在一串價格上分批買入，"
            "算出累積數量、平均成本、總手續費，並可對比一次性單筆投入。"
            "適合回答『每個月定投一萬買 BTC 會怎樣』『定期定額划不划算』這類新手問題。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "amount_per_period": {"type": "number", "description": "每一期投入的金額（TWD 或 USDT，由你決定單位）"},
                "prices": {"type": "array", "items": {"type": "number"}, "description": "每一期買入時的價格清單，例如 [900000, 950000, 1010000]"},
                "fee_rate": {"type": "number", "description": "交易手續費率，預設 0.001（0.1%）", "default": 0.001},
                "current_price": {"type": "number", "description": "（選填）目前市價，用來計算現值與損益"},
            },
            "required": ["amount_per_period", "prices"],
        },
    },
}

CALCULATE_POSITION_SIZE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculate_position_size",
        "description": (
            "風險控管的核心工具：先決定『這筆最多虧總資金的百分之幾』，再由停損距離反推現貨該買幾顆。"
            "適合回答『我有 10 萬，這筆該買多少才安全』『怎麼設部位大小』。純現貨、不含槓桿。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "account_balance": {"type": "number", "description": "總資金（本金）"},
                "risk_pct": {"type": "number", "description": "單筆最多願意虧損的資金百分比，建議 1~2"},
                "entry_price": {"type": "number", "description": "預計進場價格"},
                "stop_loss_price": {"type": "number", "description": "停損價格（需低於進場價）"},
                "fee_rate": {"type": "number", "description": "手續費率，預設 0.001", "default": 0.001},
            },
            "required": ["account_balance", "risk_pct", "entry_price", "stop_loss_price"],
        },
    },
}

CALCULATE_PNL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculate_pnl",
        "description": (
            "計算一筆交易的損益、報酬率與保本價（已含買賣來回手續費）。"
            "適合回答『我 90 萬買、100 萬賣，扣手續費實賺多少』『要回到成本要漲到哪』。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entry_price": {"type": "number", "description": "進場價"},
                "exit_price": {"type": "number", "description": "出場價"},
                "volume": {"type": "number", "description": "數量（顆數）"},
                "side": {"type": "string", "description": "buy/long（做多、現貨）或 sell/short（做空）", "enum": ["buy", "long", "sell", "short"], "default": "buy"},
                "fee_rate": {"type": "number", "description": "手續費率，預設 0.001", "default": 0.001},
            },
            "required": ["entry_price", "exit_price", "volume"],
        },
    },
}

CALCULATE_AVERAGE_DOWN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculate_average_down",
        "description": (
            "試算『再加碼一筆（攤平）』之後的新平均成本。add_amount（再投入金額）與 add_units（再買數量）擇一提供。"
            "適合回答『我均價 100 萬，現在跌到 80 萬，再買 5 萬均價變多少』。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "current_units": {"type": "number", "description": "目前持有數量"},
                "current_avg_cost": {"type": "number", "description": "目前平均成本"},
                "add_price": {"type": "number", "description": "加碼時的價格"},
                "add_amount": {"type": "number", "description": "（擇一）要再投入的金額"},
                "add_units": {"type": "number", "description": "（擇一）要再買的數量"},
                "fee_rate": {"type": "number", "description": "手續費率，預設 0.001", "default": 0.001},
            },
            "required": ["current_units", "current_avg_cost", "add_price"],
        },
    },
}

CALCULATE_TARGET_SELL_PRICE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculate_target_sell_price",
        "description": (
            "想拿到指定『淨報酬率』（已扣來回手續費），該賣在多少價位。"
            "適合回答『我想淨賺 10%，要賣在多少』。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entry_price": {"type": "number", "description": "進場價"},
                "target_net_roi_pct": {"type": "number", "description": "目標淨報酬率(%)，例如 10 代表 +10%"},
                "fee_rate": {"type": "number", "description": "手續費率，預設 0.001", "default": 0.001},
            },
            "required": ["entry_price", "target_net_roi_pct"],
        },
    },
}

CALCULATORS_TOOLS = [
    CALCULATE_DCA_SCHEMA,
    CALCULATE_POSITION_SIZE_SCHEMA,
    CALCULATE_PNL_SCHEMA,
    CALCULATE_AVERAGE_DOWN_SCHEMA,
    CALCULATE_TARGET_SELL_PRICE_SCHEMA,
]
