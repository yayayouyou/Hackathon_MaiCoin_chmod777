"""
agent/critic_agent.py

自我批判代理 (Critic Agent)
=============================================
這是 Phase B 的創新功能。作為主要決策大腦的「副駕 (Co-pilot)」。
在主要大腦產出決策後，Critic Agent 會掃描其推理步驟與結論，
檢查是否存在以下問題：
1. Confirmation Bias (確認偏誤)
2. 矛盾訊號被忽略 (例如技術看多但鏈上資金流出)
3. 違反 Guardrails (防護欄) 的建議
"""

from loguru import logger

from agent.llm import get_provider, LLMError

CRITIC_SYSTEM_PROMPT = """你是「AI 投資審查官 (Critic Agent)」，只審查「買賣/多空建議」的致命邏輯漏洞。

檢查三點：確認偏誤（只挑有利數據）、明顯矛盾（訊號互斥卻仍強烈看多/空）、過度自信或缺乏風險揭示。

【輸出要求 — 務必極簡】
- 若無明顯漏洞：只回一句「審查通過：無發現明顯邏輯漏洞。」（不要多餘文字）
- 若有漏洞：最多 3 條「• 一句話點出問題」，並在最後一行給「建議評級：觀望/降級」。總長不超過 120 字，禁止長篇報告、禁止重述對方分析。
"""

def evaluate_decision(
    reasoning_steps: list,
    draft_decision: str,
    provider=None,
    model_name: str = None,
    host: str = None,
) -> str:
    """
    對主要大腦的決策草稿進行批判審查。

    Args:
        reasoning_steps: 主大腦的推理步驟（工具呼叫 + 思考）
        draft_decision:  主大腦的最終草稿結論
        provider:        LLM 供應商（通常由主迴圈注入以重用連線）；None 則自建
        model_name/host: 未注入 provider 時的後備建構參數
    """
    logger.info("啟動 Critic Agent 自我批判循環...")

    # 前置條件守衛：草稿為空 / 幾乎無內容時，直接視為通過，避免對空輸入產生
    # 「輸入資料缺失」之類的無效審查（實測 audit log 曾出現此 bug）。
    if not draft_decision or len(draft_decision.strip()) < 15:
        return "審查通過：無實質決策內容可審查。"

    # 格式化推理步驟
    steps_text = ""
    for step in reasoning_steps:
        if "tool" in step:
            steps_text += f"[Tool Call] {step['tool']}\nArgs: {step.get('args', {})}\nResult: {step.get('result_summary', '')}\n"
        elif step.get("type") == "thought":
            steps_text += f"[Thought] {step.get('content_preview', '')}\n"

    if not steps_text:
        steps_text = "[無工具調用或詳細推理步驟，大腦直接給出了最終回覆。]"

    user_prompt = f"""請審查以下 AI 交易員的決策：

【推理日誌】
{steps_text}

【最終草稿結論】
{draft_decision}

請給出你的批判結果。如果存在問題，請給出修正建議。
"""

    if provider is None:
        try:
            provider = get_provider(model_name=model_name, host=host)
        except LLMError as e:
            logger.error(f"Critic Agent 供應商初始化失敗: {e}")
            return f"審查官離線，無法進行批判審查。({str(e)})"

    try:
        resp = provider.chat(
            [
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        critic_review = (resp.content or "").strip()
        logger.info(f"Critic Agent 審查結果: {critic_review}")
        return critic_review or "審查通過：無發現明顯邏輯漏洞。"

    except Exception as e:
        logger.error(f"Critic Agent 執行失敗: {e}")
        return f"審查官離線，無法進行批判審查。({str(e)})"
