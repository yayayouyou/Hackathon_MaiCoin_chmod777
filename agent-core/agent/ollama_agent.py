"""
agent/ollama_agent.py

Ollama Agent 決策大腦與工具調用循環核心
=============================================
"""

import os
import re
import json
from typing import Dict, Any, List, Generator, Optional, Tuple
from loguru import logger

from agent.prompts import get_system_prompt, ALL_TOOLS
from agent.tool_router import select_tools, route_intents
from agent import reader_agent
from agent import memory_store
from agent.audit_logger import AuditTrail
from agent.llm import get_provider, LLMError, LLMResponse, ToolCall, parse_text_tool_call

# 向後相容：舊測試/程式仍以 _parse_tool_call 匯入文字解析器（現已移至 agent.llm.base）
_parse_tool_call = parse_text_tool_call

# 匯入所有交易工具
from skills.market_data.ccxt_fetcher import get_ohlcv, get_ticker, get_orderbook, list_exchanges
from skills.market_data.coinglass_client import get_funding_rate, get_open_interest, get_liquidation_history, get_long_short_ratio
from skills.market_data.coinglass_scraper import (
    get_coinglass_liquidation_chart,
    get_coinglass_open_interest_info,
    get_coinglass_home_stats,
    get_coinglass_ahr999,
    get_coinglass_altcoin_season,
    get_coinglass_mayer_multiple,
    get_coinglass_etf_flow,
    get_coinglass_grayscale_stats,
    get_coinglass_liquidation_heatmap,
)
from skills.market_data.dex_screener import (
    search_dex_pairs,
    get_dex_token_info,
)
from skills.derivatives.multi_exchange import get_aggregated_funding_rate, get_aggregated_open_interest
from skills.derivatives.binance_futures import get_binance_open_interest_history, get_binance_long_short_ratio
from skills.derivatives.bybit_derivatives import get_bybit_open_interest_history
from skills.derivatives.coinalyze_client import get_coinalyze_long_short_ratio, get_coinalyze_predicted_funding
from skills.max_exchange.max_public import (
    get_max_markets, get_max_tickers, get_max_depth, get_max_klines, get_max_public_trades,
    get_max_currencies, get_max_interest_rates, get_max_index_prices,
)
from skills.max_exchange.max_private import (
    get_max_member_info, get_max_accounts, get_max_orders, get_max_order,
    get_max_order_history, get_max_my_trades, get_max_deposits, get_max_withdrawals,
    get_max_ad_ratio, get_max_fund_transactions, get_max_converts,
    get_max_withdraw_addresses, get_max_internal_transfers,
)
from skills.market_data.onchain_flow import get_smart_money_flow, validate_smart_money_signal, run_token_due_diligence
from skills.market_data.chain_trace import trace_deposit_source
from skills.market_intel.coingecko_client import get_coingecko_coin_price, get_coingecko_global_stats, get_coingecko_trending
from skills.market_intel.cmc_client import get_cmc_latest_quotes, get_cmc_global_metrics
from skills.market_intel.blockchain_client import get_blockchain_btc_stats, get_btc_unconfirmed_tx
from skills.market_intel.fng_client import get_crypto_fear_and_greed_index
from skills.market_intel.news_client import get_latest_crypto_news
from skills.market_intel.btc_treasuries import get_btc_treasuries
from skills.market_intel.sosovalue_extras import get_crypto_sector_indices, get_crypto_stocks
from skills.market_intel import fetch_reddit_sentiment, search_web_duckduckgo, fetch_trump_truth_posts, fetch_twitter_user_tweets
from skills.analytics import (
    calculate_indicators,
    run_backtest,
    save_strategy,
    list_strategies,
    run_backtest_on_saved_strategy,
    backtest_strategy,
    run_twitter_mention_backtest,
    detect_market_regime,
    analyze_portfolio
)
from skills.analytics.analyst_desk import run_analyst_desk
from skills.analytics.event_study import run_signal_backtest, run_composite_backtest
from analyst_sandbox.sandbox import run_analysis
from skills.execution.order_executor import create_order, cancel_order, cancel_all_orders
from skills.execution.live_guard import ledger_summary as get_trading_guard_status
from skills.education import (
    explain_crypto_term,
    get_max_guide,
    get_beginner_safety_checklist,
    get_max_fee_info,
)
from skills.calculators import (
    calculate_dca,
    calculate_position_size,
    calculate_pnl,
    calculate_average_down,
    calculate_target_sell_price,
)

# 註冊所有工具函數對照表
TOOL_CALLABLES = {
    # CCXT 行情與 DEX
    "get_ohlcv": get_ohlcv,
    "get_ticker": get_ticker,
    "get_orderbook": get_orderbook,
    "list_exchanges": list_exchanges,
    "search_dex_pairs": search_dex_pairs,
    "get_dex_token_info": get_dex_token_info,
    "get_smart_money_flow": get_smart_money_flow,
    "validate_smart_money_signal": validate_smart_money_signal,
    "run_token_due_diligence": run_token_due_diligence,
    # Coinglass 數據 (選填)
    "get_funding_rate": get_funding_rate,
    "get_open_interest": get_open_interest,
    "get_liquidation_history": get_liquidation_history,
    "get_long_short_ratio": get_long_short_ratio,
    # Coinglass 免 Key 抓取工具
    "get_coinglass_liquidation_chart": get_coinglass_liquidation_chart,
    "get_coinglass_open_interest_info": get_coinglass_open_interest_info,
    "get_coinglass_home_stats": get_coinglass_home_stats,
    "get_coinglass_ahr999": get_coinglass_ahr999,
    "get_coinglass_altcoin_season": get_coinglass_altcoin_season,
    "get_coinglass_mayer_multiple": get_coinglass_mayer_multiple,
    "get_coinglass_etf_flow": get_coinglass_etf_flow,
    "get_coinglass_grayscale_stats": get_coinglass_grayscale_stats,
    "get_coinglass_liquidation_heatmap": get_coinglass_liquidation_heatmap,
    # 衍生品聚合
    "get_aggregated_funding_rate": get_aggregated_funding_rate,
    "get_aggregated_open_interest": get_aggregated_open_interest,
    "get_binance_open_interest_history": get_binance_open_interest_history,
    "get_binance_long_short_ratio": get_binance_long_short_ratio,
    "get_bybit_open_interest_history": get_bybit_open_interest_history,
    "get_coinalyze_long_short_ratio": get_coinalyze_long_short_ratio,
    "get_coinalyze_predicted_funding": get_coinalyze_predicted_funding,
    # MAX 交易所
    "get_max_markets": get_max_markets,
    "get_max_tickers": get_max_tickers,
    "get_max_depth": get_max_depth,
    "get_max_klines": get_max_klines,
    "get_max_public_trades": get_max_public_trades,
    "get_max_member_info": get_max_member_info,
    "get_max_accounts": get_max_accounts,
    "get_max_orders": get_max_orders,
    "get_max_order": get_max_order,
    "get_max_order_history": get_max_order_history,
    "get_max_my_trades": get_max_my_trades,
    "get_max_deposits": get_max_deposits,
    "get_max_withdrawals": get_max_withdrawals,
    "get_max_currencies": get_max_currencies,
    "get_max_interest_rates": get_max_interest_rates,
    "get_max_index_prices": get_max_index_prices,
    "get_max_ad_ratio": get_max_ad_ratio,
    "get_max_fund_transactions": get_max_fund_transactions,
    "get_max_converts": get_max_converts,
    "get_max_withdraw_addresses": get_max_withdraw_addresses,
    "get_max_internal_transfers": get_max_internal_transfers,
    "trace_deposit_source": trace_deposit_source,
    # 市場情報
    "get_coingecko_coin_price": get_coingecko_coin_price,
    "get_coingecko_global_stats": get_coingecko_global_stats,
    "get_coingecko_trending": get_coingecko_trending,
    "get_cmc_latest_quotes": get_cmc_latest_quotes,
    "get_cmc_global_metrics": get_cmc_global_metrics,
    "get_blockchain_btc_stats": get_blockchain_btc_stats,
    "get_btc_unconfirmed_tx": get_btc_unconfirmed_tx,
    "get_crypto_fear_and_greed_index": get_crypto_fear_and_greed_index,
    "get_latest_crypto_news": get_latest_crypto_news,
    "get_btc_treasuries": get_btc_treasuries,
    "get_crypto_sector_indices": get_crypto_sector_indices,
    "get_crypto_stocks": get_crypto_stocks,
    "fetch_reddit_sentiment": fetch_reddit_sentiment,
    "search_web_duckduckgo": search_web_duckduckgo,
    "fetch_trump_truth_posts": fetch_trump_truth_posts,
    "fetch_twitter_user_tweets": fetch_twitter_user_tweets,
    # 分析模組
    "calculate_indicators": calculate_indicators,
    "run_backtest": run_backtest,
    "backtest_strategy": backtest_strategy,
    "save_strategy": save_strategy,
    "list_strategies": list_strategies,
    "run_backtest_on_saved_strategy": run_backtest_on_saved_strategy,
    "run_twitter_mention_backtest": run_twitter_mention_backtest,
    "detect_market_regime": detect_market_regime,
    "analyze_portfolio": analyze_portfolio,
    "run_analyst_desk": run_analyst_desk,
    "run_signal_backtest": run_signal_backtest,
    "run_composite_backtest": run_composite_backtest,
    "run_analysis": run_analysis,
    # 交易執行
    "create_order": create_order,
    "cancel_order": cancel_order,
    "cancel_all_orders": cancel_all_orders,
    # 小白教育
    "explain_crypto_term": explain_crypto_term,
    "get_max_guide": get_max_guide,
    "get_beginner_safety_checklist": get_beginner_safety_checklist,
    "get_max_fee_info": get_max_fee_info,
    # 實用計算機
    "calculate_dca": calculate_dca,
    "calculate_position_size": calculate_position_size,
    "calculate_pnl": calculate_pnl,
    "calculate_average_down": calculate_average_down,
    "calculate_target_sell_price": calculate_target_sell_price,
}

# 併入使用者記憶工具（remember_about_me / recall_history / forget_about_me）
TOOL_CALLABLES.update(memory_store.MEMORY_CALLABLES)

# 併入社群情緒分析工具（analyze_figure_sentiment / analyze_crowd_sentiment）
from skills.market_intel.social_analysis import SOCIAL_ANALYSIS_CALLABLES
TOOL_CALLABLES.update(SOCIAL_ANALYSIS_CALLABLES)

# 併入資金對帳／成本基礎工具（事件帳本重播 vs 交易所實際餘額）
from skills.analytics.position_ledger import reconcile_holdings, get_cost_basis_positions
TOOL_CALLABLES.update({
    "reconcile_holdings": reconcile_holdings,
    "get_cost_basis_positions": get_cost_basis_positions,
    "get_trading_guard_status": get_trading_guard_status,
})
from skills.analytics.lot_engine import get_open_positions, get_realized_pnl
from skills.analytics.shadow_account import analyze_trading_behavior
TOOL_CALLABLES.update({
    "get_open_positions": get_open_positions,
    "get_realized_pnl": get_realized_pnl,
    "analyze_trading_behavior": analyze_trading_behavior,
})

# 併入交易 DNA 面板工具（淨值曲線 / 六軸性格分數 / 反事實「買了就抱」）。
# 預設吃訪客示範帳戶的 CSV 種子 → 沒有 MAX 金鑰、沒有網路也跑得出畫面；
# 綁定金鑰後同一批工具用 source='ledger' 換成真實帳本。
from skills.analytics.csv_source import load_demo_account_ledger
from skills.analytics.equity_curve import get_equity_curve
from skills.analytics.dna_score import get_trading_dna_score
from skills.analytics.counterfactual import compare_sell_vs_hold
TOOL_CALLABLES.update({
    "load_demo_account_ledger": load_demo_account_ledger,
    "get_equity_curve": get_equity_curve,
    "get_trading_dna_score": get_trading_dna_score,
    "compare_sell_vs_hold": compare_sell_vs_hold,
})

# 併入黃金資料層工具（get_gold_price / get_gold_macro_context / analyze_gold_market）
from skills.gold import get_gold_price, get_gold_macro_context, analyze_gold_market
TOOL_CALLABLES.update({
    "get_gold_price": get_gold_price,
    "get_gold_macro_context": get_gold_macro_context,
    "analyze_gold_market": analyze_gold_market,
})

# 吃自己的狗糧（標準化試點）：AGENT_MCP_DOGFOOD=1 時，同名旗艦工具改走 MAX MCP Server 的
# MCP 介面（單一工具定義來源）；未啟用回空 dict、零影響。放最後 → 覆蓋原生 callable。
from agent.mcp_client import load_mcp_callables
TOOL_CALLABLES.update(load_mcp_callables())

# 判斷最終答覆是否為「買賣/多空建議」——只有這類才需要 Critic 審查（省時、避免對知識性回答硬審）
_RECOMMENDATION_RE = re.compile(
    r"(買入|賣出|做多|做空|強烈買|強烈賣|加倉|減倉|抄底|逃頂|進場|出場|止損|止盈|建倉|評級|"
    r"看多|看空|偏多|偏空|strong\s*(buy|sell)|\bbuy\b|\bsell\b|\blong\b|\bshort\b)",
    re.IGNORECASE,
)

# 判斷模型是否在「反問是否要繼續執行工具」卻沒真的呼叫（需要 nudge 推它直接做）
_ASK_TO_CONTINUE_RE = re.compile(
    r"(是否要我|要不要我|是否直接繼續|請確認是否|需要我繼續|要我繼續執行|是否繼續執行|"
    r"是否要繼續|要我幫你.{0,8}嗎|可以嗎[？?]|要繼續嗎)"
)

MAX_NUDGES = 1  # 反問時最多自動推進幾次


def _is_recommendation(text: str) -> bool:
    return bool(_RECOMMENDATION_RE.search(text or ""))


def _asks_to_continue(text: str) -> bool:
    return bool(_ASK_TO_CONTINUE_RE.search(text or ""))


# 各工具『宣告的合法參數』白名單：防止模型幻覺或提示注入夾帶未宣告的敏感參數
# （例如對 create_order 注入 mode="live"/client_oid 以繞過安全預設）。
_TOOL_PARAMS: Dict[str, set] = {
    t["function"]["name"]: set(((t["function"].get("parameters") or {}).get("properties") or {}).keys())
    for t in ALL_TOOLS
}
# 分析師桌的 persona 由後端依已解析人格注入（不對 LLM 開放），列入白名單以免被 sanitize 剝除
if "run_analyst_desk" in _TOOL_PARAMS:
    _TOOL_PARAMS["run_analyst_desk"].add("persona")


def _sanitize_tool_args(name: str, args: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """只放行工具 schema 有宣告的參數；剝除其餘（防注入夾帶敏感參數）。未知工具則原樣通過。"""
    args = args or {}
    allowed = _TOOL_PARAMS.get(name)
    if allowed is None:
        return args
    dropped = [k for k in args if k not in allowed]
    if dropped:
        logger.warning(f"工具 {name} 收到未宣告參數，已剝除（防注入）：{dropped}")
    return {k: v for k, v in args.items() if k in allowed}


def _execute_tool_call(tc: ToolCall) -> Tuple[Any, str, bool]:
    """
    執行單一工具呼叫。回傳 (原始結果物件, 截斷後字串, 是否成功)。
    """
    if tc.name not in TOOL_CALLABLES:
        result = {"error": f"系統目前未註冊名為 '{tc.name}' 的工具。"}
        return result, json.dumps(result, ensure_ascii=False), False
    try:
        safe_args = _sanitize_tool_args(tc.name, tc.args)
        logger.info(f"執行工具: {tc.name} 參數: {safe_args}")
        result = TOOL_CALLABLES[tc.name](**safe_args)
        result_str = json.dumps(result, ensure_ascii=False)
        if len(result_str) > 4000:
            result_str = result_str[:4000] + "... [結果過長已被截斷]"
        return result, result_str, True
    except Exception as e:
        logger.error(f"工具 {tc.name} 執行失敗: {e}")
        result = {"error": f"工具執行失敗 {str(e)}"}
        return result, json.dumps(result, ensure_ascii=False), False


def _gate_order(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    交易核准互鎖閘門。判斷一筆 create_order 該：
      - {"kind": "execute"}       直接執行（政策 off／自動核准／參數該由 create_order 自行報錯）
      - {"kind": "risk_rejected"} 硬風控攔截（回傳 result 給模型）
      - {"kind": "pending", ...}  需人工核准（附 token/plan/hash/summary）
    """
    from skills.execution.order_executor import prepare_and_validate_order, get_risk_mode
    from agent import trade_approval as ta

    if str(args.get("exchange_id", "max")).lower() != "max":
        return {"kind": "execute"}  # 交給 create_order 回傳它自己的「不支援交易所」錯誤

    market = args.get("market", "")
    side = str(args.get("side", "")).lower()
    ord_type = str(args.get("ord_type", "limit")).lower()
    price = args.get("price")
    try:
        volume = float(args.get("volume"))
    except (TypeError, ValueError):
        return {"kind": "execute"}  # 參數異常，交給 create_order 報錯
    if ord_type == "limit" and price is None:
        return {"kind": "execute"}  # 限價缺 price，交給 create_order 報錯

    # 1. 硬編碼物理風控鎖：超限直接擋在核准之前（人工也不能放行超限單）
    prep = prepare_and_validate_order(market, side, volume, price, ord_type)
    if not prep["ok"]:
        return {"kind": "risk_rejected", "result": prep["response"]}

    # 2. 依政策決定是否需要人工核准
    if ta.get_policy() == "off":
        return {"kind": "execute"}
    plan = ta.build_order_plan(args, prep["latest_price"], get_risk_mode())
    if not ta.needs_approval(plan):
        return {"kind": "execute"}
    token, plan_h = ta.register_pending(plan)
    return {"kind": "pending", "token": token, "plan": plan, "hash": plan_h,
            "summary": ta.human_summary(plan)}


def _gate_cancel_all(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    全帳戶撤單互鎖：指定 market 的撤單安全、直接執行；『無 market＝清掉全部市場掛單』
    （含止損/止盈保護單）則走與下單相同的人工核准，避免單一幻覺/注入呼叫清空帳戶。
    """
    from skills.execution.order_executor import get_risk_mode
    from skills.max_exchange.max_private import _normalize_market_id
    from agent import trade_approval as ta

    if str(args.get("exchange_id", "max")).lower() != "max":
        return {"kind": "execute"}
    m = args.get("market")
    m = m.strip() if isinstance(m, str) else ""
    if m and _normalize_market_id(m):
        return {"kind": "execute"}          # 指定市場的撤單，安全，直接執行
    # 全帳戶撤單：政策 off 交給函式的 confirm 防呆；否則一律人工核准
    if ta.get_policy() == "off":
        return {"kind": "execute"}
    plan = ta.build_cancel_all_plan("max", get_risk_mode())
    token, plan_h = ta.register_pending(plan)
    return {"kind": "pending", "token": token, "plan": plan, "hash": plan_h,
            "summary": ta.human_summary(plan)}


def run_agent_turn(
    history_messages: List[Dict[str, str]],
    model_name: str = "qwen2.5:7b",
    host: Optional[str] = None,
    max_steps: int = 8,
    persona_key: str = "default",
    provider=None,
) -> Generator[Dict[str, Any], None, None]:
    """
    【大腦執行循環】多輪思考 + 工具調用，使用 Generator 實時 yield 進度給前端。

    - 透過 LLM 供應商抽象層 (agent.llm) 呼叫模型，支援 Ollama 原生 tools 與 OpenRouter。
    - 每一輪可執行「多個」工具呼叫（原生 function-calling），大幅提升五維分析的完成度。
    - 支持投資大師人格切換與不可變審計日誌記錄。
    """
    from datetime import datetime, timezone, timedelta
    tz_taipei = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_taipei).strftime("%Y-%m-%d %H:%M:%S")

    user_query = history_messages[-1].get("content", "") if history_messages else ""

    # 供應商提早建立（供 LLM 角色分流用；失敗直接回錯誤結束）
    if provider is None:
        try:
            provider = get_provider(model_name=model_name, host=host)
        except LLMError as e:
            yield {"type": "error", "content": f"大腦供應商初始化失敗: {e}"}
            return

    # 角色派發：鎖定角色直接用；'auto'/空 → 先用一次輕量 LLM 呼叫判斷該由哪個角色回答（比關鍵字準，
    # 追求準確度）。可設環境變數 AGENT_PERSONA_ROUTER=off 關閉 LLM 分流、退回關鍵字啟發式（省一次呼叫）。
    from agent.personas import resolve_persona, get_persona, classify_persona_llm
    if persona_key in (None, "", "auto"):
        if os.getenv("AGENT_PERSONA_ROUTER", "on").strip().lower() != "off":
            yield {"type": "status", "content": "正在判斷最適合的分析角色…"}
            persona_key = classify_persona_llm(user_query, provider)
        else:
            persona_key = resolve_persona("auto", user_query)
    else:
        persona_key = resolve_persona(persona_key, user_query)
    _persona = get_persona(persona_key)

    base_system_prompt = get_system_prompt(persona_key)
    time_context = f"\n<current_time>\n當前系統真實時間 (台北時間 UTC+8): {now_str}\n請以此時間作為分析『最近』、『目前』、『最新』行情或歷史回測的參考基準點。\n</current_time>\n"
    # 分層記憶：注入使用者長期偏好與近期紀錄（無資料則為空字串）
    mem_context = memory_store.build_memory_context()
    full_system_prompt = base_system_prompt + time_context + (("\n" + mem_context + "\n") if mem_context else "")

    messages: List[Dict[str, Any]] = [{"role": "system", "content": full_system_prompt}] + list(history_messages)

    audit = AuditTrail(user_query=user_query, model_name=model_name, persona=persona_key)
    # 先讓前端知道本輪實際由哪個角色回答（自動派發時尤其重要）
    yield {"type": "persona", "key": persona_key, "name": _persona.get("name"), "icon": _persona.get("icon")}

    # 供交易日誌記錄用：本輪用過的工具與（若有）下單計畫
    journal_tools: List[str] = []
    journal_order: Optional[Dict[str, Any]] = None

    # 工具路由：依問題挑選相關工具子集（而非每輪送全部 69 個），減少 prompt、
    # 提升小模型 function-calling 準確率。整輪對話沿用同一子集以維持 KV prefix 穩定。
    routed_tools = select_tools(user_query)
    logger.info(f"工具路由：{len(routed_tools)}/{len(ALL_TOOLS)} 個工具 → {[t['function']['name'] for t in routed_tools][:12]}…")

    # gemma4 原生思考模式：off（預設）/ on / auto（僅多空分析類問題才開，避免簡單題浪費 token）
    # 注意：off 必須明確送 think=False —— 不送這個欄位時 gemma4 會**預設開啟思考**，
    # 實測一句話的問題可燒掉 600+ token 全在 thinking、content 仍是空的（done_reason=length）。
    # 送 think=False 後同一題 7 秒給出乾淨答案。auto 模式的非分析題同理要送 False 而非 None。
    _think_mode = os.getenv("AGENT_THINK", "off").strip().lower()
    if _think_mode == "on":
        use_think: Optional[bool] = True
    elif _think_mode == "auto":
        use_think = "analysis_full" in route_intents(user_query)
    else:
        use_think = False

    # 建立供應商（可由呼叫端注入，方便測試）
    if provider is None:
        try:
            provider = get_provider(model_name=model_name, host=host)
        except LLMError as e:
            yield {"type": "error", "content": f"大腦供應商初始化失敗: {e}"}
            audit.set_final_decision(f"ERROR: {e}")
            audit.finalize_and_write()
            return

    nudges = 0  # 已對「反問是否繼續」自動推進的次數
    for current_step in range(1, max_steps + 1):
        logger.info(f"Agent Loop 步驟 {current_step}/{max_steps}")
        # 分階段進度：首輪顯示連線大腦，之後帶「輪次 + 已呼叫工具」讓多輪 ReAct 有進度感
        if current_step == 1:
            # 不用「大腦」這種擬人化說法，也不把 provider:model 這種內部細節放在等待畫面上
            # （模型是誰可在系統狀態面板看）。使用者要知道的是「現在在幹嘛」。
            _stage = "讀題並挑選要用的資料來源…"
        else:
            _used = "、".join(dict.fromkeys(journal_tools)) or "無"
            _stage = f"第 {current_step} 輪推理中（已用工具：{_used}）…"
        yield {"type": "status", "content": _stage, "step": current_step, "max_steps": max_steps}

        streamed = ""   # 本輪串流暫顯的文字（工具回合會被 answer_reset 清掉）
        try:
            if hasattr(provider, "chat_stream"):
                resp = None
                for _kind, _payload in provider.chat_stream(messages, tools=routed_tools, think=use_think):
                    if _kind == "delta":
                        if _payload:
                            streamed += _payload
                            yield {"type": "answer_delta", "content": _payload}
                    elif _kind == "final":
                        resp = _payload
                if resp is None:                 # 串流未回 final（保險）→ 退回非串流
                    resp = provider.chat(messages, tools=routed_tools, think=use_think)
            else:                                 # 無串流能力（FakeProvider/OpenRouter）→ 維持原本一次回覆
                resp: LLMResponse = provider.chat(messages, tools=routed_tools, think=use_think)
        except LLMError as e:
            logger.error(f"LLM 請求出錯: {e}")
            yield {"type": "error", "content": f"大腦連接錯誤: {str(e)}"}
            audit.set_final_decision(f"ERROR: {str(e)}")
            audit.finalize_and_write()
            return

        # 原生思考通道：推理不進最終答案，僅送 UI 終端顯示（think 模式時）
        if resp.thinking:
            yield {"type": "thinking", "content": resp.thinking}

        content = resp.content or ""
        if content:
            yield {"type": "thought", "content": content}
            audit.log_thought(content)

        # 有工具呼叫：本輪可能一次多個，全部執行後回饋，再進下一輪
        if resp.tool_calls:
            if streamed:                          # 本輪串流出的文字其實是工具前導 → 通知前端清掉暫顯答案
                yield {"type": "answer_reset"}
            messages.append(resp.raw_message or {"role": "assistant", "content": content})

            collected = []  # 文字備援時彙整成單一回饋訊息，避免多則 user 訊息讓模型誤判
            for tc in resp.tool_calls:
                # 分析師桌：注入本輪解析出的人格，讓 5 層權重跟隨用戶策略（LLM 不自行指定）
                if tc.name == "run_analyst_desk" and isinstance(tc.args, dict):
                    tc.args.setdefault("persona", persona_key)
                yield {"type": "tool_call", "name": tc.name, "args": tc.args}
                journal_tools.append(tc.name)

                # ── 交易核准互鎖：create_order 與『全帳戶撤單』不直接執行，先過閘門 ──
                if tc.name in ("create_order", "cancel_all_orders"):
                    gate = _gate_order(tc.args or {}) if tc.name == "create_order" else _gate_cancel_all(tc.args or {})
                    if gate["kind"] == "pending":
                        journal_order = gate["plan"]
                        # 送人工核准；模型只會拿到「等待核准、尚未成交」，避免它宣稱已下單
                        yield {
                            "type": "approval_request",
                            "name": tc.name,
                            "token": gate["token"],
                            "plan": gate["plan"],
                            "hash": gate["hash"],
                            "summary": gate["summary"],
                        }
                        result = {
                            "status": "PENDING_APPROVAL",
                            "message": ("此訂單已送出，正在等待使用者於介面上點擊核准；"
                                        "在使用者核准前『尚未成交、尚未送出』。"
                                        "請告知使用者你已備妥這筆訂單、正等待他確認，切勿宣稱已成交。"),
                            "plan": gate["plan"],
                        }
                        result_str = json.dumps(result, ensure_ascii=False)
                        ok = True
                        audit.log_tool_call(tc.name, tc.args, "PENDING_APPROVAL", success=True)
                    elif gate["kind"] == "risk_rejected":
                        result = gate["result"]
                        result_str = json.dumps(result, ensure_ascii=False)
                        ok = False
                        yield {"type": "tool_result", "name": tc.name, "result": result}
                        audit.log_tool_call(tc.name, tc.args, result_str[:500], success=False)
                    else:  # execute（政策 off／自動核准／該由 create_order 自行報錯）
                        result, result_str, ok = _execute_tool_call(tc)
                        yield {"type": "tool_result", "name": tc.name, "result": result}
                        audit.log_tool_call(tc.name, tc.args, result_str[:500], success=ok)
                else:
                    result, result_str, ok = _execute_tool_call(tc)
                    yield {"type": "tool_result", "name": tc.name, "result": result}
                    audit.log_tool_call(tc.name, tc.args, result_str[:500], success=ok)

                # ── Reader 淨化層：不可信外部內容（新聞/社群/搜尋）餵回主大腦前先消毒 ──
                model_content = result_str
                if reader_agent.is_untrusted(tc.name) and ok:
                    san = reader_agent.sanitize(tc.name, result_str, provider=provider, user_query=user_query)
                    model_content = san["content_for_model"]
                    yield {
                        "type": "reader",
                        "name": tc.name,
                        "injection_detected": san["injection_detected"],
                        "flags": san["flags"],
                        "reader_used": san["reader_used"],
                    }
                    if san["injection_detected"]:
                        logger.warning(f"Reader 於 {tc.name} 偵測到疑似注入並已淨化：{san['flags']}")

                if resp.native_tools:
                    # 原生 function-calling：以 tool 角色回饋，附 tool_call_id
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "tool_name": tc.name,  # gemma4 renderer 以 tool_name 標記回應來源，缺了會標成 unknown
                        "content": model_content,
                    })
                else:
                    collected.append((tc.name, model_content))

            # 文字備援：把所有結果彙整成「一則」正向明確的回饋，
            # 措辭上肯定「工具已實際執行」，避免模型反過來說自己沒呼叫工具。
            if collected:
                lines = "\n".join(f"【{name}】{rs}" for name, rs in collected)
                messages.append({
                    "role": "user",
                    "content": (
                        "工具已『實際執行完畢』，以下為真實回傳結果：\n" + lines +
                        f"\n\n請直接根據以上真實數據，完整回答使用者最初的問題：「{user_query}」。"
                        "務必回扣問題的每一部分——若問題含『這是什麼幣／在做什麼』這類概念，"
                        "先用你的知識簡短說明，再帶入數據分析與（若有問到的）多空/前景結論。"
                        "失敗的工具就略過，不要反問、不要重寫工具呼叫、不要說自己沒有呼叫工具。"
                    ),
                })
            continue

        # 沒有工具呼叫且內容為空：提示模型根據工具結果續答
        if not content.strip():
            messages.append({"role": "user", "content": "請根據以上工具結果，給出完整的中文分析與結論。"})
            continue

        # 模型反問「是否要繼續執行工具」卻沒真的呼叫 → 有限次數自動推進，避免卡住空等
        if nudges < MAX_NUDGES and _asks_to_continue(content):
            nudges += 1
            logger.info("偵測到模型反問是否繼續，自動推進 (nudge)")
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": "不要詢問，請直接把需要的工具全部呼叫完，再一次給出結論。"})
            continue

        # Critic 只在「真正的買賣/多空建議」時才啟動（省時，且避免對知識性回答硬審與拖長）
        final_content = content
        if _is_recommendation(content):
            yield {"type": "status", "content": "啟動 Critic Agent 進行決策邏輯審查..."}
            from agent.critic_agent import evaluate_decision
            critic_feedback = evaluate_decision(
                reasoning_steps=audit.reasoning_steps,
                draft_decision=content,
                provider=provider,
            )
            # 「審查通過」時隱藏 Critic 報告；否則附上「精簡」的警示與審查意見。
            if "審查通過" not in critic_feedback.replace(" ", ""):
                disclaimer = (
                    "\n\n---\n**🚨 風險警示：** 本內容為 AI 分析，僅供參考、不構成投資建議；加密貨幣風險極高，請自行審慎判斷。"
                )
                final_content = content + disclaimer + "\n\n**🤖 Critic：** " + critic_feedback

        audit.set_final_decision(final_content)
        audit.finalize_and_write()
        # 分層記憶：把本輪精簡紀錄寫入交易日誌（供未來對話回讀與搜尋）
        memory_store.append_journal(user_query, final_content, journal_tools, journal_order)
        yield {"type": "final_answer", "content": final_content}
        return

    # 迴圈用盡仍未收斂
    msg = f"大腦思考次數達到上限 ({max_steps} 步)，已停止。請縮小問題範圍或稍後再試。"
    audit.set_final_decision(msg)
    audit.finalize_and_write()
    memory_store.append_journal(user_query, msg, journal_tools, journal_order)
    yield {"type": "final_answer", "content": msg}
