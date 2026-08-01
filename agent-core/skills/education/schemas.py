"""
skills/education/schemas.py

小白教育技能 Tool JSON Schema 定義 (OpenAI-compatible)
=============================================
"""

EXPLAIN_CRYPTO_TERM_SCHEMA = {
    "type": "function",
    "function": {
        "name": "explain_crypto_term",
        "description": (
            "用白話解釋一個加密貨幣或交易名詞（如 現貨、合約、槓桿、爆倉、資金費率、RSI、均線、"
            "私鑰、助記詞、穩定幣、DCA、MAX Token）。適合回答新手『XX 是什麼』『看不懂 OO』。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "term": {"type": "string", "description": "要查詢的名詞，例如『資金費率』或『合約』"},
            },
            "required": ["term"],
        },
    },
}

GET_MAX_GUIDE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_guide",
        "description": (
            "取得 MAX 交易所的白話操作教學。topic 可為：開戶、台幣入金、台幣出金、買幣、手續費、api金鑰、安全設定。"
            "適合回答『MAX 怎麼入金』『第一次怎麼買幣』『怎麼申請 API』。不填 topic 會列出所有主題。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "教學主題，例如『台幣入金』『開戶』『手續費』"},
            },
            "required": [],
        },
    },
}

GET_BEGINNER_SAFETY_CHECKLIST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_beginner_safety_checklist",
        "description": (
            "新手防詐與安全守則。category 可為：詐騙、資產安全、心態。"
            "適合回答『這是不是詐騙』『怎麼保護資產』『新手該注意什麼』。不填則回傳全部。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "分類：詐騙 / 資產安全 / 心態；可不填取全部"},
            },
            "required": [],
        },
    },
}

GET_MAX_FEE_INFO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_max_fee_info",
        "description": (
            "回傳 MAX 交易所手續費與 MAX Token 折抵的結構化說明（Maker/Taker、出入金費、省手續費方法）。"
            "適合回答『MAX 手續費多少』『怎麼省手續費』『MAX Token 能幹嘛』。"
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

EDUCATION_TOOLS = [
    EXPLAIN_CRYPTO_TERM_SCHEMA,
    GET_MAX_GUIDE_SCHEMA,
    GET_BEGINNER_SAFETY_CHECKLIST_SCHEMA,
    GET_MAX_FEE_INFO_SCHEMA,
]
