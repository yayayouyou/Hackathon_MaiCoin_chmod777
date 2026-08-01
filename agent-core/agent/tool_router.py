"""
agent/tool_router.py — 關鍵字工具路由器（精選 per-intent 工具集）
=====================================================
依使用者問題挑選「相關的工具子集」，而非每輪都把 94 個工具全部送給模型。

研究依據 (Less-is-More, arXiv 2411.15399)：給小模型過多工具會顯著降低
function-calling 準確率並拖慢 prefill；聚焦子集能同時提升準確率與速度。

設計：
  - 每個「細意圖」只掛真正需要的少量工具（不是整個粗分組）。
  - 只有真正的「多空決策分析 (analysis_full)」才展開完整旗艦堆疊，維持五步驗證品質。
  - CORE 工具（MAX 公開行情 + 恐貪指數）永遠可用 → 確保 G6「優先 MAX」與基本報價隨時可達。
  - 命中多個意圖時取聯集；完全沒命中時先用 embedding 語意檢索補救關鍵字漏接
    （見 tool_embeddings.py），embedding 不可用才退回精簡 price 集合。
    安全不變式：語意 fallback 絕不引入 execution 工具（下單須明確意圖）。
  - 輸出依 ALL_TOOLS 固定順序 → 穩定，有利 Ollama KV prefix cache。
"""
import os
import re
import json
from datetime import datetime
from typing import List, Dict, Any, Set

from agent.prompts import ALL_TOOLS

_ALL_BY_NAME: Dict[str, Dict[str, Any]] = {t["function"]["name"]: t for t in ALL_TOOLS}

# ── 永遠可用的核心工具（MAX 公開行情 + 恐貪 + 使用者記憶）─────────────────────────
CORE: Set[str] = {
    "get_max_tickers", "get_max_klines", "get_max_depth", "get_max_markets",
    "get_crypto_fear_and_greed_index",
    "remember_about_me", "recall_history",
}

# ── 細意圖 → 該意圖需要的工具 ─────────────────────────
INTENT_TOOLS: Dict[str, Set[str]] = {
    "price": {
        "get_ticker", "get_orderbook", "get_max_public_trades",
        "get_coingecko_coin_price", "get_cmc_latest_quotes",
        "search_dex_pairs", "get_dex_token_info", "get_max_index_prices",
    },
    "onchain": {"get_smart_money_flow", "validate_smart_money_signal", "run_token_due_diligence",
                 "search_dex_pairs", "get_dex_token_info"},  # 鏈上資金流/聰明錢 + 訊號驗證 + 盡職調查
    "technical": {"get_ohlcv", "calculate_indicators"},
    # 註：CoinGlass v4 付費工具（get_funding_rate/get_open_interest/get_liquidation_history/
    #   get_long_short_ratio，需付費金鑰）已從預設集移除——改用下列免費等價工具，避免 LLM 誤選導致必失敗。
    "derivatives": {
        "get_aggregated_funding_rate",
        "get_aggregated_open_interest", "get_binance_open_interest_history",
        "get_binance_long_short_ratio", "get_bybit_open_interest_history",
        "get_coinglass_liquidation_chart", "get_coinglass_liquidation_heatmap",
        "get_coinglass_open_interest_info",
        "get_coinalyze_long_short_ratio", "get_coinalyze_predicted_funding",
    },
    "indices": {
        "get_coinglass_ahr999", "get_coinglass_altcoin_season",
        "get_coinglass_mayer_multiple", "get_coinglass_etf_flow",
        "get_coinglass_grayscale_stats", "get_coinglass_home_stats",
    },
    "intel": {
        "get_latest_crypto_news", "fetch_reddit_sentiment", "search_web_duckduckgo",
        "fetch_trump_truth_posts", "fetch_twitter_user_tweets",
        "get_coingecko_trending", "get_coingecko_global_stats",
        "get_cmc_global_metrics", "get_blockchain_btc_stats", "get_btc_unconfirmed_tx",
        "analyze_figure_sentiment", "analyze_crowd_sentiment",  # 社群情緒分析（短期事件 + 長期大眾）
        "analyze_sentiment_divergence", "analyze_influence_decay",  # 菁英vs群眾背離 + 名人喊單影響力半衰期
        "get_btc_treasuries",  # 企業財庫持幣動向（機構級籌碼信號）
        "get_crypto_sector_indices", "get_crypto_stocks",  # 板塊輪動 + 加密概念股
    },
    "analytics": {
        "run_backtest", "backtest_strategy", "save_strategy", "list_strategies",
        "run_backtest_on_saved_strategy", "run_twitter_mention_backtest",
        "detect_market_regime", "analyze_portfolio", "run_analyst_desk",
        "run_signal_backtest", "run_composite_backtest", "run_analysis",
        "get_equity_curve",   # 「最大回撤/淨值走勢」本來就是這顆工具在答（它直接回 max_drawdown_pct）
    },
    "gold": {  # 黃金資料層（代幣化報價 + 總經驅動 + 綜合簡報）
        "get_gold_price", "get_gold_macro_context", "analyze_gold_market",
    },
    "education": {
        "explain_crypto_term", "get_max_guide",
        "get_beginner_safety_checklist", "get_max_fee_info",
    },
    "calculators": {
        "calculate_dca", "calculate_position_size", "calculate_pnl",
        "calculate_average_down", "calculate_target_sell_price",
    },
    # ── 帳戶類（P1：由單一巨大 account 拆成子意圖，避免任一帳戶問題就灌 15 個工具）──
    # 餘額/資產/持倉（含「我的資產這一年怎麼變化」→ 曲線才答得出來，不能只給當下快照）
    "acct_balance": {"get_max_accounts", "get_max_ad_ratio", "get_equity_curve"},
    "acct_fees": {"get_max_member_info"},                                   # 手續費/VIP/等級
    "acct_margin": {"get_max_ad_ratio", "get_max_accounts", "get_max_interest_rates"},  # 融資/維持率/借幣利率
    "acct_orders": {"get_max_orders", "get_max_order", "get_max_order_history"},        # 委託/掛單
    "acct_trades": {"get_max_my_trades"},                                   # 成交歷史
    "acct_funds": {                                                         # 入出金/提幣/閃兌/轉帳/白名單/入金溯源
        "get_max_fund_transactions", "get_max_deposits", "get_max_withdrawals",
        "get_max_converts", "get_max_withdraw_addresses", "get_max_internal_transfers",
        "trace_deposit_source",
    },
    "acct_pnl": {                                                           # 資金對帳/成本基礎/損益可信度
        "reconcile_holdings", "get_cost_basis_positions", "get_open_positions", "get_realized_pnl",
        "analyze_trading_behavior",
        "get_max_my_trades", "get_max_accounts",
    },
    "trading_dna": {                                                        # 交易 DNA 面板（曲線/六軸/反事實）
        "get_trading_dna_score", "get_equity_curve", "compare_sell_vs_hold",
        "load_demo_account_ledger", "analyze_trading_behavior",
    },
    "coin_info": {"get_max_currencies"},                                    # 幣種提幣費/可質押/鏈別（公開參考）
    "execution": {"create_order", "cancel_order", "cancel_all_orders", "get_trading_guard_status"},
    "trade_guard": {"get_trading_guard_status", "get_max_orders"},   # 風控狀態/停手/曝險查詢
}

# 「多空決策分析」是 meta 意圖：展開成完整旗艦堆疊（五步驗證需要的所有數據維度）
ANALYSIS_FULL_GROUPS = ["price", "technical", "derivatives", "indices", "intel", "analytics"]

# ── 意圖 → 關鍵字 ─────────────────────────
KEYWORDS: Dict[str, List[str]] = {
    "price": ["多少錢", "價格", "報價", "現價", "現在多少", "幣價", "漲跌", "盤口", "深度", "市值", "指數價", "指數價格", "標記價", "標記價格"],
    # 鏈上資金流/聰明錢（get_smart_money_flow）
    "onchain": ["聰明錢", "鏈上資金", "鏈上買", "在累積", "偷偷買", "偷偷累積", "誰在買", "有沒有人買", "買盤強不強", "資金流向", "smart money", "鏈上流",
                 # 訊號驗證：真訊號 vs 噪音（validate_smart_money_signal）
                 "真訊號", "還是噪音", "訊號可靠", "歷史上有用", "這訊號準嗎", "進場後真的漲", "驗證訊號",
                 # 一鍵盡職調查（run_token_due_diligence）
                 "盡職調查", "能不能碰", "能碰嗎", "進場前", "看一遍", "綜合分析", "幫我看這幣", "值不值得進"],
    "technical": ["k線", "k 線", "kline", "rsi", "macd", "均線", "布林", "atr", "技術指標", "技術面", "支撐", "阻力", "背離"],
    "derivatives": ["資金費率", "費率", "爆倉", "清算", "未平倉", "持倉量", "多空", "多空比", "open interest", " oi ", "槓桿",
                     "散戶", "偏多", "偏空", "爆掉", "關鍵價位", "爆倉價", "液化", "預測資金", "下一期資金", "資金費會", "擁擠"],
    "indices": ["ahr999", "囤幣", "山寨季", "山寨幣季", "mayer", "梅耶", "etf", "灰度", "資金流", "溢價",
                 "大盤", "氣氛", "總覽", "全網", "全市場", "市場概況", "整體行情", "市場總覽", "行情如何"],
    "intel": ["新聞", "消息", "輿情", "reddit", "推特", "twitter", "馬斯克", "musk", "川普", "trump", "情緒", "恐慌", "貪婪", "恐懼", "搜尋", "熱度", "熱門", "利多", "利空", "大眾", "看法", "怎麼看", "社群", "輿論", "看好", "看壞", "氛圍", "共識", "討論",
               "財庫", "企業持幣", "企業買", "機構持幣", "機構買", "微策略", "microstrategy", "mstr", "metaplanet", "囤幣公司", "上市公司", "企業增持", "企業減持", "treasur",
               "板塊", "輪動", "類股", "賽道", "defi", "meme", "迷因", "板塊指數", "概念股", "礦股", "coin股", "哪個板塊", "哪類幣", "risk-on", "risk on",
               # 菁英 vs 群眾背離 + 名人喊單影響力（analyze_sentiment_divergence / analyze_influence_decay）
               "背離", "菁英", "散戶", "聰明錢", "大戶跟散戶", "喊單", "影響力", "半衰期", "喊加密", "號召力", "帶風向"],
    "analytics": ["回測", "策略", "勝率", "績效", "累計收益", "市場狀態", "投資組合", "portfolio", "regime", "買了就抱",
                   "增持後", "買入後", "買了會", "帶動", "連帶", "會不會漲", "之後會漲", "歷史上", "統計上",
                   "組合", "同時滿足", "同時觸發", "共振", "多重訊號", "雙重", "且", "又",
                   "自訂分析", "幫我算", "自己算", "寫程式", "客製", "特殊條件", "自己組", "算一下",
                   # 口語化「歷史/統計行為」線索（提升回測 recall，讓 run_signal_backtest 被送到模型面前）
                   "以前", "以前每次", "過往", "過去每次", "每次", "通常", "賺還是賠", "賺比較多還是賠", "賺的多還是賠",
                   "有沒有統計", "有人統計", "統計過", "有沒有紀錄", "以前的紀錄", "紀錄可以看", "有沒有以前",
                   "接刀", "追高", "會不會彈", "彈回來", "彈回去", "續漲", "繼續漲嗎", "之後幾天", "接下來幾天",
                   # 口語化「要實際運算」線索（提升 run_analysis recall）
                   "數一下", "幫我數", "有幾天", "相關係數", "反著走", "反著跑", "誰最強", "誰比較強", "排個序", "最大回撤", "標準差"],
    "gold": ["黃金", "金價", "gold", "xau", "paxg", "xaut", "避險", "實質利率", "美元指數", "dxy", "貴金屬", "通膨對沖"],
    # 註：execution/analysis_full 改採「寬鬆動作詞 + 資訊否決(_INFO_VETO)」策略（見 route_intents）——
    #   放寬買/賣/平倉等口語命令都能命中，再用否決詞擋掉『什麼是市價單/買入訊號/手續費』這類資訊題誤觸；
    #   「多空」歸 derivatives(『多空比/多空持倉比』本就是衍生品指標)；education 移除裸「如何」。
    "education": ["什麼是", "是什麼", "解釋", "名詞", "怎麼用", "怎麼買", "入金", "出金", "儲值", "提領", "開戶", "註冊", "手續費", "詐騙", "被騙", "安全嗎", "保護", "新手", "教學", "助記詞", "私鑰", "kyc", "冷錢包", "熱錢包"],
    "calculators": ["定投", "定期定額", "該買多少", "買多少", "部位", "倉位", "停損", "停利", "止損", "止盈", "攤平", "加碼", "減碼", "損益", "報酬", "目標價", "幾顆", "幾個", "多少顆", "多少張", "dca", "本金", "賣在", "均價"],
    # 帳戶類（P1 拆分：各子意圖只掛自己需要的工具，避免一問帳戶就灌 15 個）
    # 註：「清算/爆倉」歸 derivatives（市場爆倉），帳戶用「維持率/清算風險」；「資金流」歸 indices（ETF 資金流），
    #     帳戶用「資金流水/資金動態」；「我的持倉」避免比中 derivatives 的「持倉量」。
    "acct_balance": ["帳戶", "帳戶狀態", "帳戶總覽", "資產", "資產分佈", "餘額", "我的持倉", "身家", "我的部位", "有多少錢", "對帳", "我的資產"],
    "acct_fees": ["手續費", "手續費等級", "交易手續費", "我的費率", "費率等級", "vip", "vip等級", "會員等級", "我的等級", "折扣", "費率多少", "手續費多少", "打幾折", "折扣多少"],
    "acct_margin": ["融資", "融資錢包", "m錢包", "維持率", "負債", "借貸", "借幣", "槓桿", "融資利率", "借幣利率", "借貸利率", "年化利率", "資金成本", "借幣利息", "利率多少", "清算風險", "會被清算", "爆倉價", "清算價"],
    "acct_orders": ["我的訂單", "我的委託", "委託紀錄", "委託單", "掛單歷史", "掛單中", "未成交", "訂單狀態", "查訂單"],
    "acct_trades": ["成交紀錄", "成交歷史", "我的成交", "交易紀錄", "我買過", "我賣過", "歷史成交"],
    "acct_funds": ["入金", "出金", "充值", "提現", "入帳", "提領記錄", "提幣記錄", "入金記錄", "出金記錄", "我的提幣",
                    "資金流水", "資金紀錄", "資金動態", "轉帳", "互轉", "站內轉帳", "閃兌", "換幣紀錄", "換成",
                    "提幣地址", "提幣白名單", "白名單", "地址簿",
                    # 入金來源溯源（trace_deposit_source）
                    "入金來源", "資金來源", "來路不明", "從哪來", "從哪裡來", "錢從哪", "溯源", "資金溯源", "來源可靠"],
    "trade_guard": ["實盤還是模擬", "現在是實盤嗎", "交易模式", "風控狀態", "停止交易", "停手",
                     "今天下了多少", "累計下單", "曝險", "為什麼被擋", "為什麼那筆", "被擋下", "被拒絕", "訂單被拒", "下單紀錄", "授權到期", "kill switch", "緊急停止"],
    "acct_pnl": ["對帳", "資金對帳", "帳對得上", "對得上嗎", "數字可信", "損益可信", "帳本", "資金追蹤",
                  "成本基礎", "成本價", "我的成本", "持倉成本", "均價", "平均成本", "買入成本",
                  "已實現損益", "未實現損益", "實現損益", "浮動損益", "賺多少", "賠多少", "虧多少",
                  "艙位", "倉位", "部位損益", "每筆損益", "損益計算", "資金流向缺口",
                  "交易習慣", "行為偏誤", "我的問題", "常犯的錯", "追高", "追漲", "殺跌",
                  "攤平", "抱不住", "捨不得", "處置效應", "手續費花太多", "過度交易", "交易紀律"],
    # 交易 DNA 面板：性格雷達圖 / 淨值曲線 / 「都不賣會怎樣」的反事實
    "trading_dna": ["交易dna", "交易 dna", "交易性格", "交易風格", "什麼類型的交易者", "哪種交易者",
                     "雷達圖", "性格分數", "交易畫像", "投資性格", "我是哪種", "我屬於哪",
                     "淨值曲線", "資產曲線", "淨值變化", "資產變化", "資產走勢",
                     "都不賣", "不賣會", "買了就抱", "一直抱", "抱著不動", "頻繁進出", "進出到底",
                     "示範帳戶", "範例帳戶", "先看範例", "還沒綁", "沒有帳號",
                     # 以下補的是「工具 description 自己承諾能答、關鍵字卻漏接」的問法
                     # （驗證時實測全部零命中；沒被選中的工具等於沒註冊）
                     "投資風格", "交易個性", "個性", "archetype",              # 性格類同義說法
                     "哪一項最弱", "哪一項最強", "哪一軸", "最弱的一項", "弱點", "強項",  # 六軸追問
                     "回撤", "最大回撤",                                       # 曲線健康度（get_equity_curve 直接回）
                     "資產怎麼變", "資產這一年", "這一年怎麼變", "一年怎麼變化",  # 曲線的口語問法
                     "我這一年", "全年回顧", "年度回顧", "交易得怎麼樣", "交易得如何"],
    "coin_info": ["提幣手續費", "提幣費", "提幣最低", "最低提幣", "可質押", "哪些幣可質押", "哪些幣", "走哪條鏈", "哪條鏈", "區塊鏈網路", "提幣網路", "存提"],
    "execution": ["下單", "賣掉", "市價買", "市價賣", "限價買", "限價賣", "掛單", "掛買", "掛賣", "撤單", "撤掉", "取消訂單", "取消委託", "取消掛單", "平倉", "平掉", "建倉", "清倉", "賣光", "出清", "委託買", "委託賣", "幫我買", "幫我賣", "我要買", "我要賣"],
    "analysis_full": ["該不該", "評級", "看漲", "看跌", "會漲", "會跌", "漲不漲", "前景", "趨勢", "值得買", "值得投", "能不能買", "可以買嗎", "抄底", "逃頂", "起飛", "布局", "佈局", "完整分析", "幫我分析", "分析一下", "該進場", "該出場", "進不進場", "多空決策", "多空分析", "多空建議", "綜合分析", "深度分析"],
}

# 資訊/定義/指標『否決詞』：出現代表是「是什麼/怎麼算/手續費/訊號量」等資訊題，
# 不應觸發下單(execution)或旗艦分析(analysis_full)——即使句中含買/賣/平倉/趨勢等詞。
# 資訊/定義/指標題否決（同時擋 execution 與 analysis_full）
_INFO_VETO = ["什麼是", "是什麼", "什麼叫", "何謂", "代表什麼", "什麼意思", "意思", "定義", "解釋",
              "為什麼", "怎麼算", "怎麼計算", "如何算", "如何", "手續費", "訊號", "成本", "教學",
              "新手", "怎麼買", "怎麼賣", "會不會", "掛單量", "是多少", "未平倉", "賣壓", "買盤", "賣盤"]

# 意見/評估題否決（只擋 execution，保留 analysis_full）：「該不該平倉/值得建倉嗎」是問建議不是下命令
_OPINION_VETO = ["該不該", "值得", "適合", "時機", "要不要", "能不能", "可不可以", "好不好", "好嗎"]

# 口語數量命令：買/賣(可含 入/出/進) 緊接數字（如「買 0.01」「買入 0.1」）→ 下單；不誤中「該買多少/值得買」
_EXEC_QTY_RE = re.compile(r"[買賣][入出進]?\s*[0-9]")


# ── 語意增補參數（P3 recall 安全網：細分後仍不漏掉可用工具）─────────────────────────
_AUGMENT_MIN_SCORE = 0.55    # 有關鍵字命中時，只補相似度 ≥ 此值的「高相關」工具（避免又灌爆）
_AUGMENT_MAX_ADD = 6         # 每題語意增補上限（會乘上 _K_SCALE）
_AUGMENT_BASE_MAX = 14       # 只在關鍵字選出的集合「夠窄」時才增補（針對細分帳戶等 recall 風險高的題；
                             #   價格/技術/旗艦分析等本就夠廣，不再補以免失焦）

# ── 信心自適應候選數 ─────────────────────────
# 原則：語意最高分越低（越不確定：模糊語句/錯字/跨域）→ 給越多候選，交給 LLM 容錯精選；
#       分數越高（明確命中）→ 給越精簡。另有模型能力旋鈕與全餵逃生口（強模型可放很寬）。
_K_SCALE = float(os.getenv("AGENT_TOOL_K_SCALE", "1") or "1")    # 模型能力旋鈕：強模型可調大


def _fallback_k(top_score: float) -> int:
    """完全沒關鍵字命中時，依語意最高分決定候選數（越不確定給越多）。"""
    if top_score >= 0.62:
        k = 5      # 明確命中 → 精簡
    elif top_score >= 0.55:
        k = 8      # 普通
    else:
        k = 14     # 低信心（模糊/錯字/跨域）→ 放寬，別賭窄集合
    return max(5, round(k * _K_SCALE))


def _feed_all_mode() -> bool:
    """全餵逃生口：強模型可直接吃全部工具（跳過檢索）。仍守 execution 安全不變式。"""
    return os.getenv("AGENT_TOOL_FEED_ALL", "0").strip().lower() in ("1", "true", "yes")

_ROUTING_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "conversation_logs", "routing_log.jsonl",
)


def _log_routing(query: str, intents: Set[str], tools: Set[str], used_semantic: bool,
                 top_score: float = None, mode: str = "") -> None:
    """把路由決策寫入 JSONL（供事後找『漏工具』的洞：fallback、工具數過小、低信心的題）。
    預設關閉（ROUTING_LOG=1 開啟；app 啟動時開），失敗絕不影響路由。"""
    if os.getenv("ROUTING_LOG", "0").strip().lower() in ("0", "false", "no"):
        return
    try:
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "query": (query or "")[:200],
            "intents": sorted(intents),
            "fallback": not (intents & (set(INTENT_TOOLS) | {"analysis_full"})),
            "used_semantic": bool(used_semantic),
            "top_score": round(top_score, 3) if top_score is not None else None,
            "mode": mode,
            "n_tools": len(tools),
            "tools": sorted(tools),
        }
        os.makedirs(os.path.dirname(_ROUTING_LOG), exist_ok=True)
        with open(_ROUTING_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _match(q: str, keywords: List[str]) -> bool:
    return any(k in q for k in keywords)


def route_intents(user_query: str) -> Set[str]:
    """回傳命中的意圖集合（供除錯/測試）。"""
    q = f" {(user_query or '').lower()} "
    hits = {intent for intent, kws in KEYWORDS.items() if _match(q, kws)}
    if _EXEC_QTY_RE.search(q):
        hits.add("execution")
    # 資訊/定義題：同時擋下單與旗艦分析（『什麼是市價單/未平倉量/什麼叫背離』）
    if any(v in q for v in _INFO_VETO):
        hits -= {"execution", "analysis_full"}
    # 意見/評估題：只擋下單、保留旗艦分析（『該不該買入/值得平倉嗎』是要分析、不是要下單）
    if any(v in q for v in _OPINION_VETO):
        hits.discard("execution")
    return hits


def select_tool_names(user_query: str) -> Set[str]:
    """回傳挑選到的工具名稱集合。"""
    intents = route_intents(user_query)

    # 全餵逃生口（強模型用）：直接吃全部工具，但仍守 execution 安全不變式
    if _feed_all_mode():
        names = set(_ALL_BY_NAME)
        if "execution" not in intents:
            names -= INTENT_TOOLS["execution"]
        _log_routing(user_query, intents, names, used_semantic=False, mode="feed_all")
        return names

    names: Set[str] = set(CORE)
    if "analysis_full" in intents:
        for g in ANALYSIS_FULL_GROUPS:
            names |= INTENT_TOOLS[g]
    for intent in intents:
        if intent in INTENT_TOOLS:
            names |= INTENT_TOOLS[intent]

    data_intents = intents & (set(INTENT_TOOLS) | {"analysis_full"})

    # 語意檢索一律取「所有工具的相似度分數」，用途分兩種（皆排除 execution：下單須明確意圖）：
    #   有命中 → 只把「高相關(≥門檻)」工具增補進來 → recall 安全網，避免細分後漏掉可用工具，
    #            但有門檻+上限 → 不會又灌爆。
    #   沒命中 → 取語意 top-k 當主力（原 P0 fallback，修關鍵字漏接如「換成/英文/打幾折」）。
    # embedding 不可用（無 ollama/模型/逾時）時優雅降級：有命中就純關鍵字、沒命中退回 price。
    scored = None
    try:
        from agent.tool_embeddings import semantic_tool_scores
        scored = semantic_tool_scores(user_query, ALL_TOOLS)
    except Exception:  # noqa: BLE001
        scored = None

    exec_tools = INTENT_TOOLS["execution"]
    top_score = scored[0][1] if scored else None
    mode = ""
    if data_intents:
        mode = "keyword"
        if scored and len(names) <= _AUGMENT_BASE_MAX:     # 只補「窄集合」，廣意圖維持精簡
            max_add = max(1, round(_AUGMENT_MAX_ADD * _K_SCALE))
            added = 0
            for n, s in scored:                       # scored 已由高到低排序
                if added >= max_add or s < _AUGMENT_MIN_SCORE:
                    break
                if n in _ALL_BY_NAME and n not in exec_tools and n not in names:
                    names.add(n)
                    added += 1
    else:
        if scored:
            k = _fallback_k(top_score)                # 信心自適應：越不確定給越多
            mode = f"semantic(k={k})"
            names |= {n for n, _ in scored[:k] if n in _ALL_BY_NAME and n not in exec_tools}
        else:
            mode = "price_degraded"
            names |= INTENT_TOOLS["price"]

    result = {n for n in names if n in _ALL_BY_NAME}
    _log_routing(user_query, intents, result, used_semantic=scored is not None,
                 top_score=top_score, mode=mode)
    return result


def select_tools(user_query: str) -> List[Dict[str, Any]]:
    """依問題挑選工具子集（依 ALL_TOOLS 固定順序，永不為空，永遠含 CORE）。"""
    chosen = select_tool_names(user_query)
    return [t for t in ALL_TOOLS if t["function"]["name"] in chosen]
