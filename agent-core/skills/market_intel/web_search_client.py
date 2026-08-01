"""
skills/market_intel/web_search_client.py

網頁即時搜尋工具 — 基於 ddgs 套件（DuckDuckGo 等多後端聚合）
=================================================
免 API 金鑰即時網頁搜尋，回傳標題、摘要與原文連結。

治本改版：原本手刻正則爬 html.duckduckgo.com，DuckDuckGo 改版後回 0 筆且吐出
跳轉包裝網址（uddg 解碼判斷式從不觸發）。改用維護中的 `ddgs` 套件（前身
duckduckgo_search），由它處理後端切換、反爬與連結解碼；限流時會拋例外而非
靜默回空，因此「0 筆」代表真的無結果，不是爬蟲死掉。
"""
from typing import Dict, Any
from loguru import logger

from ddgs import DDGS


def search_web_duckduckgo(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    【LLM Tool】在網路上進行即時搜尋以獲取最新新聞、資料或公告資訊。

    Args:
        query: 搜尋關鍵字（例如 'MAX 交易所 充值活動 2026'）
        max_results: 限制返回的搜尋結果數量，預設為 5，上限為 10。
    """
    max_results = max(1, min(10, max_results))
    logger.info(f"正在使用 ddgs 進行網頁即時搜尋: '{query}'")

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
    except Exception as e:  # noqa: BLE001 — ddgs 限流/後端錯誤都在此；不靜默當成無結果
        logger.error(f"網頁搜尋失敗: {e}")
        return {"error": f"網頁搜尋出錯（可能被限流，請稍後再試）: {e.__class__.__name__}"}

    results = [
        {
            "title": (r.get("title") or "").strip(),
            "link": (r.get("href") or r.get("url") or "").strip(),
            "snippet": (r.get("body") or "").strip(),
        }
        for r in raw
    ]

    if not results:
        return {"query": query, "count": 0, "results": [],
                "message": "搜尋無結果（並非錯誤；可換關鍵字或改用即時新聞）"}

    logger.success(f"成功查找到 {len(results)} 條網頁搜尋結果")
    return {"query": query, "count": len(results), "results": results}
