"""
skills/education/education.py

小白教育技能函數 (Beginner Education Skills)
=============================================
把 content.py 的策展內容包成 LLM 可呼叫的工具。全部離線、無外部 API。

  - explain_crypto_term         : 名詞白話解釋（含模糊比對）
  - get_max_guide               : MAX 使用教學（開戶/入金/出金/買幣/手續費/API/安全）
  - get_beginner_safety_checklist : 防詐與新手安全守則
  - get_max_fee_info            : MAX 手續費與 MAX Token 折抵結構化說明
"""

from typing import Any, Dict, List, Optional

from skills.education.content import (
    GLOSSARY, GLOSSARY_ALIASES,
    MAX_GUIDES, MAX_GUIDE_ALIASES, MAX_OFFICIAL_DOCS, MAX_SUPPORT,
    SAFETY, SAFETY_ALIASES,
)


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace("／", "/")


def explain_crypto_term(term: str) -> Dict[str, Any]:
    """
    【LLM Tool】用白話解釋一個加密貨幣/交易名詞（例如 現貨、合約、爆倉、資金費率、RSI）。
    找不到時會回傳可用名詞清單，方便引導使用者。
    """
    if not term or not str(term).strip():
        return {"available_terms": sorted(GLOSSARY.keys()), "note": "請提供想查詢的名詞。"}

    key = _norm(term)
    # 直接命中
    entry = GLOSSARY.get(key)
    # 別名命中
    if entry is None and key in GLOSSARY_ALIASES:
        key = GLOSSARY_ALIASES[key]
        entry = GLOSSARY.get(key)
    # 模糊：包含關係
    if entry is None:
        for k in GLOSSARY:
            if key and (key in k or k in key):
                entry, key = GLOSSARY[k], k
                break
    if entry is None:
        for alias, real in GLOSSARY_ALIASES.items():
            if key and (key in alias or alias in key):
                key, entry = real, GLOSSARY.get(real)
                break

    if entry is None:
        return {
            "found": False,
            "query": term,
            "available_terms": sorted(GLOSSARY.keys()),
            "note": f"字庫裡還沒有「{term}」。可從 available_terms 挑，或請大腦用一般知識白話解釋。",
        }

    return {
        "found": True,
        "term": key,
        "aka": entry.get("aka", ""),
        "explanation": entry.get("text", ""),
        "summary": f"{key}（{entry.get('aka','')}）：{entry.get('text','')}",
    }


def get_max_guide(topic: Optional[str] = None) -> Dict[str, Any]:
    """
    【LLM Tool】取得 MAX 交易所的白話操作教學。
    topic 可為：開戶 / 台幣入金 / 台幣出金 / 買幣 / 手續費 / api金鑰 / 安全設定。
    不填或無法對應時，回傳所有可用主題清單。
    """
    topics = list(MAX_GUIDES.keys())
    if not topic or not str(topic).strip():
        return {
            "available_topics": topics,
            "note": "請指定主題，例如『台幣入金』或『開戶』。",
            "official_docs": MAX_OFFICIAL_DOCS,
            "support": MAX_SUPPORT,
        }

    key = _norm(topic)
    guide_key = None
    if topic in MAX_GUIDES:
        guide_key = topic
    elif key in MAX_GUIDE_ALIASES:
        guide_key = MAX_GUIDE_ALIASES[key]
    else:
        for alias, real in MAX_GUIDE_ALIASES.items():
            if key and (key in alias or alias in key):
                guide_key = real
                break
        if guide_key is None:
            for t in MAX_GUIDES:
                if key and (key in _norm(t) or _norm(t) in key):
                    guide_key = t
                    break

    if guide_key is None:
        return {
            "found": False,
            "query": topic,
            "available_topics": topics,
            "note": "找不到對應主題，請從 available_topics 選一個。",
        }

    g = MAX_GUIDES[guide_key]
    return {
        "found": True,
        "topic": guide_key,
        "title": g["title"],
        "steps": g["steps"],
        "note": g.get("note", ""),
        "official_docs": MAX_OFFICIAL_DOCS,
        "disclaimer": "數字型資訊（手續費、限額、到帳時間）可能調整，請以 MAX 官方最新公告為準。",
    }


def get_beginner_safety_checklist(category: Optional[str] = None) -> Dict[str, Any]:
    """
    【LLM Tool】新手防詐與安全守則。category 可為：詐騙 / 資產安全 / 心態。
    不填則回傳全部三大類。
    """
    if not category or not str(category).strip():
        return {
            "categories": list(SAFETY.keys()),
            "checklist": SAFETY,
            "note": "涵蓋常見詐騙、資產安全與新手資金心態三大面向。",
        }

    key = _norm(category)
    cat_key = None
    if category in SAFETY:
        cat_key = category
    elif key in SAFETY_ALIASES:
        cat_key = SAFETY_ALIASES[key]
    else:
        for alias, real in SAFETY_ALIASES.items():
            if key and (key in alias or alias in key):
                cat_key = real
                break
        if cat_key is None:
            for c in SAFETY:
                if key and (key in _norm(c) or _norm(c) in key):
                    cat_key = c
                    break

    if cat_key is None:
        return {"found": False, "query": category, "categories": list(SAFETY.keys())}

    block = SAFETY[cat_key]
    return {
        "found": True,
        "category": cat_key,
        "title": block["title"],
        "items": block["items"],
        "note": block.get("note", ""),
    }


def get_max_fee_info() -> Dict[str, Any]:
    """
    【LLM Tool】MAX 交易所手續費與 MAX Token 折抵的結構化說明。
    """
    return {
        "trading_fee": {
            "default_maker": "0.05%",
            "default_taker": "0.15%",
            "best_vip": "約 0% / 0.045%（依 30 天交易量與 MAX Token 鎖倉量提升 VIP）",
            "maker_taker_note": "掛限價單被動成交 = Maker（較便宜）；直接吃市價立即成交 = Taker（較貴）。",
        },
        "twd_deposit_fee": "MAX 端不收；銀行跨行轉帳費可能另計（部分數位帳戶免跨轉費）。",
        "twd_withdraw_fee": "固定 15 TWD / 筆。",
        "max_token_discount": [
            "可開啟『用 MAX Token 折抵交易手續費』，系統自動換算等值台幣的 MAX 扣抵。",
            "用 MAX Token 支付提領手續費另享約 10% 折扣。",
            "鎖倉 MAX Token 可提升 VIP 等級、進一步降低費率。",
        ],
        "other_discounts": ["註冊填有效推薦碼通常可拿手續費折扣。"],
        "ways_to_save": "省手續費三招：多用限價單(Maker)、開 MAX Token 折抵、累積交易量/鎖倉升 VIP。",
        "official_docs": MAX_OFFICIAL_DOCS,
        "disclaimer": "費率會調整，實際以 MAX 官方公告為準。",
        "summary": (
            "MAX 交易費預設約 Maker 0.05% / Taker 0.15%，VIP 最低可到約 0%/0.045%；"
            "台幣入金免手續費、出金固定 15 元；用 MAX Token 可折抵交易費並享提領費 9 折。"
        ),
    }
