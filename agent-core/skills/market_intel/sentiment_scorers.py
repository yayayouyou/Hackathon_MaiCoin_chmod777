"""
skills/market_intel/sentiment_scorers.py — 群眾情緒『批次量化打分器』
=================================================================
慢軌（大眾長期看法）的『量化補強層』。用便宜的本地打分器對『大量貼文』逐則打分，
產出情緒分佈（多空比例／均值／離散度／兩極化），補足 gemma 只做一次質性彙整、
無法規模化讀完上百則的缺口。兩者互補：

  - 量化打分器：快、可規模化、給出『分佈與兩極化』，但淺（不懂反諷/上下文）。
  - gemma 彙整：慢、只做一次，但深（主題、與價格背離、反諷）。
  兩者若『方向不一致』本身就是有用的元訊號（分歧＝低信心）。

兩層打分器（自動挑最佳可用者，預設走輕量那層，不強迫下載大模型）：
  1) VADER + 『加密圈黑話詞庫增強』（預設；純 Python、無 torch、~130KB，永遠可用）
     VADER 的詞典是一般英文社群語，缺加密黑話（hodl/moon/rug/rekt/fud/ath…），
     因此我們把這些詞灌進 VADER 詞典再打分。
  2) CryptoBERT（可選；需 transformers+torch，約 2GB）— ElKulako/cryptobert，
     BERTweet 在加密社群語料微調的三分類模型。僅在環境變數 SENTIMENT_ENGINE=cryptobert
     且套件可用時啟用；否則優雅回落 VADER。

本層只提供『量化佐證』，不做交易決策。
"""
import os
import re
from typing import Dict, Any, List, Optional
from statistics import fmean, pstdev

from loguru import logger

# ── 加密圈黑話詞庫（灌進 VADER；值域約 -4(極空) ~ +4(極多)，與 VADER lexicon 一致）──
# 只收 VADER 一般詞典『缺少或會誤判』的加密專有語；一般情緒詞交給 VADER 原詞典。
CRYPTO_LEXICON: Dict[str, float] = {
    # 多方黑話
    "moon": 2.4, "mooning": 2.4, "moonshot": 2.0, "mooned": 1.8,
    "hodl": 1.3, "hodling": 1.3, "hodler": 1.0, "hodlers": 1.0,
    "bullish": 2.6, "bull": 1.4, "bullrun": 2.7, "bullruns": 2.5,
    "pump": 1.4, "pumping": 1.5, "pumped": 1.0, "pumps": 1.2,
    "ath": 1.9, "breakout": 1.6, "breakouts": 1.5,
    "accumulate": 1.0, "accumulating": 1.0, "accumulation": 0.8,
    "lambo": 1.7, "wagmi": 2.6, "lfg": 2.0, "gm": 0.6,
    "undervalued": 1.6, "adoption": 1.4, "bullposting": 1.8,
    "diamondhands": 2.2, "moonbound": 2.2, "sendit": 1.6,
    # 空方黑話
    "rug": -2.8, "rugged": -3.0, "rugpull": -3.2, "rugpulled": -3.0, "rugpulls": -3.0,
    "rekt": -2.6, "dump": -1.9, "dumping": -2.0, "dumped": -1.6, "dumps": -1.7,
    "fud": -1.6, "fudding": -1.7, "bearish": -2.6, "bear": -1.4,
    "capitulation": -2.2, "capitulate": -2.0, "capitulating": -2.1,
    "ngmi": -2.4, "ponzi": -2.6, "bagholder": -1.7, "bagholders": -1.7,
    "bagholding": -1.7, "bags": -0.7, "bloodbath": -2.8,
    "liquidated": -2.2, "liquidation": -1.8, "liquidations": -1.8,
    "selloff": -2.0, "tanking": -2.2, "tank": -1.4, "tanked": -1.8,
    "overbought": -0.8, "shitcoin": -1.8, "shitcoins": -1.8, "scamcoin": -2.6,
    "deadcoin": -2.6, "exitliquidity": -2.4, "downonly": -2.2,
}

# VADER 標準門檻：compound >= 0.05 偏多、<= -0.05 偏空、之間為中性
_POS_TH = 0.05
_NEG_TH = -0.05

_vader_singleton = None
_cryptobert_state = {"tried": False, "pipe": None}  # 只嘗試載入一次


def _get_vader():
    """取得（並快取）灌入加密詞庫後的 VADER 分析器。"""
    global _vader_singleton
    if _vader_singleton is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        sia = SentimentIntensityAnalyzer()
        sia.lexicon.update(CRYPTO_LEXICON)  # 加密黑話覆蓋／補進原詞典
        _vader_singleton = sia
        logger.info(f"VADER 情緒打分器就緒（+{len(CRYPTO_LEXICON)} 加密詞）")
    return _vader_singleton


def _vader_score(text: str) -> float:
    """回傳 VADER compound 分數，範圍 [-1, 1]。"""
    return float(_get_vader().polarity_scores(text or "")["compound"])


def _get_cryptobert():
    """惰性載入 CryptoBERT pipeline；失敗只記錄一次並回 None（之後不再重試）。"""
    if _cryptobert_state["tried"]:
        return _cryptobert_state["pipe"]
    _cryptobert_state["tried"] = True
    try:
        from transformers import pipeline  # 需 transformers + torch（可選重依賴）
        _cryptobert_state["pipe"] = pipeline(
            "text-classification", model="ElKulako/cryptobert",
            top_k=None, truncation=True, max_length=128)
        logger.success("CryptoBERT 打分器就緒（ElKulako/cryptobert）")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"CryptoBERT 不可用，回落 VADER：{e.__class__.__name__}: {e}")
        _cryptobert_state["pipe"] = None
    return _cryptobert_state["pipe"]


def _cryptobert_score(text: str, pipe) -> float:
    """CryptoBERT 三分類 → 分數 = P(Bullish) - P(Bearish)，範圍 [-1, 1]。"""
    out = pipe(text or "")
    rows = out[0] if (out and isinstance(out[0], list)) else out
    probs = {str(r["label"]).lower(): float(r["score"]) for r in rows}
    return round(probs.get("bullish", 0.0) - probs.get("bearish", 0.0), 4)


def _resolve_engine(prefer: Optional[str]) -> str:
    """決定用哪個引擎。預設 VADER（安全、不觸發大模型下載）；只有明確要求才走 CryptoBERT。"""
    prefer = (prefer or os.getenv("SENTIMENT_ENGINE") or "vader").lower().strip()
    if prefer in ("cryptobert", "bert"):
        return "cryptobert" if _get_cryptobert() is not None else "vader"
    return "vader"


def _label(score: float) -> str:
    if score >= _POS_TH:
        return "bullish"
    if score <= _NEG_TH:
        return "bearish"
    return "neutral"


def score_text(text: str, engine: Optional[str] = None) -> Dict[str, Any]:
    """對『單則文字』打分。回傳 {score(-1~1), label, engine}。"""
    eng = _resolve_engine(engine)
    if eng == "cryptobert":
        pipe = _get_cryptobert()
        if pipe is not None:
            s = _cryptobert_score(text, pipe)
            return {"score": s, "label": _label(s), "engine": "cryptobert"}
    s = round(_vader_score(text), 4)
    return {"score": s, "label": _label(s), "engine": "vader"}


def _aggregate(scores: List[float]) -> Dict[str, Any]:
    """把逐則分數彙整成分佈統計。"""
    n = len(scores)
    bull = sum(1 for s in scores if s >= _POS_TH)
    bear = sum(1 for s in scores if s <= _NEG_TH)
    neu = n - bull - bear
    bull_share = round(bull / n, 3)
    bear_share = round(bear / n, 3)
    net = round(bull_share - bear_share, 3)                 # 淨情緒 [-1,1]
    # 兩極化：多空各佔比越接近＝越分歧；min(多,空)*2 → 0(一面倒) ~ 1(完全對半)
    polarization = round(min(bull_share, bear_share) * 2, 3)
    is_polarized = polarization >= 0.4
    # 標籤：先看是否明顯分歧，再看淨情緒強弱
    if is_polarized and abs(net) < 0.3:
        label = "divided"
    elif net >= 0.5:
        label = "strong_bullish"
    elif net >= 0.15:
        label = "bullish"
    elif net <= -0.5:
        label = "strong_bearish"
    elif net <= -0.15:
        label = "bearish"
    else:
        label = "neutral"
    return {
        "sample_size": n,
        "mean_score": round(fmean(scores), 4),
        "dispersion": round(pstdev(scores), 4) if n > 1 else 0.0,
        "bullish_share": bull_share,
        "bearish_share": bear_share,
        "neutral_share": round(neu / n, 3),
        "net_sentiment": net,
        "polarization": polarization,
        "is_polarized": is_polarized,
        "label": label,
    }


def bulk_score(texts: List[str], engine: Optional[str] = None,
               keep_examples: int = 3) -> Dict[str, Any]:
    """
    對『一批文字』逐則量化打分並彙整分佈。這是慢軌的量化補強核心。

    Args:
        texts: 文字列表（貼文/標題）。
        engine: 'vader'（預設）或 'cryptobert'（需 transformers，否則自動回落）。
        keep_examples: 各挑幾則最偏多／最偏空的代表例回傳（供人看）。

    回傳：{engine, aggregate{...}, most_bullish[], most_bearish[]}。
    """
    clean = [re.sub(r"\s+", " ", (t or "")).strip() for t in (texts or [])]
    clean = [t for t in clean if t]
    if not clean:
        return {"error": "無可打分的文字", "aggregate": _aggregate([0.0]) | {"sample_size": 0}}

    eng = _resolve_engine(engine)
    if eng == "cryptobert":
        pipe = _get_cryptobert()
        scores = [_cryptobert_score(t, pipe) for t in clean] if pipe else None
        if scores is None:
            eng = "vader"
    if eng == "vader":
        sia = _get_vader()
        scores = [round(float(sia.polarity_scores(t)["compound"]), 4) for t in clean]

    scored = sorted(zip(clean, scores), key=lambda x: x[1])
    k = max(0, keep_examples)
    most_bear = [{"text": t[:160], "score": s} for t, s in scored[:k] if s <= _NEG_TH]
    most_bull = [{"text": t[:160], "score": s} for t, s in reversed(scored[-k:]) if s >= _POS_TH]
    return {
        "engine": eng,
        "aggregate": _aggregate(scores),
        "most_bullish": most_bull,
        "most_bearish": most_bear,
    }
