"""
agent/gen_tool_examples.py — 用 LLM 自動為每個工具生成「使用者會怎麼問」的範例問句
=====================================================
Re-Invoke / ToolBench 做法：離線用 LLM 為每個工具產生多樣的合成 query，一起做語意索引，
拉近「工具向量 ↔ 使用者口語」的距離，大幅提升模糊/改寫/口語查詢的命中率。

輸出：agent/tool_examples_auto.json = {tool_name: {"desc_hash": ..., "examples": [...]}}
（可 commit，其他環境不必重跑；工具描述變了會標記需重生成該筆。）

執行：.venv/bin/python -m agent.gen_tool_examples
環境：需要本地 ollama + 生成模型（預設 gemma4:12b，可用 GEN_MODEL 覆蓋）。
"""
import os
import json
import hashlib

from loguru import logger

from agent.prompts import ALL_TOOLS

_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_examples_auto.json")
_MODEL = os.getenv("GEN_MODEL", "gemma4:12b")

_SCHEMA = {
    "type": "object",
    "properties": {"examples": {"type": "array", "items": {"type": "string"}}},
    "required": ["examples"],
}


def _desc_hash(desc: str) -> str:
    return hashlib.sha256((desc or "").encode()).hexdigest()[:12]


def _prompt(name: str, desc: str) -> str:
    return (
        "你在幫一個台灣的加密貨幣交易 App 建立工具檢索索引。以下是一個後端工具的功能說明。\n"
        "請站在『真實使用者』角度，產生 8 個他們可能會用來觸發這個工具的**口語問句**。要求：\n"
        "1) 繁體中文、台灣用語；2) 多樣化：長短不一、正式與口語都有、不同說法/同義詞；\n"
        "3) 貼近真人隨口問的樣子（可省略主詞）；4) 不要編造這工具沒有的功能。\n"
        "只輸出 JSON：{\"examples\": [\"...\", ...]}。\n\n"
        f"工具名稱：{name}\n功能說明：{desc}"
    )


def generate(overwrite: bool = False) -> None:
    data = {}
    if os.path.exists(_OUT):
        try:
            with open(_OUT, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            data = {}

    from agent.llm.factory import get_provider
    provider = get_provider(model_name=_MODEL)

    tools = [(t["function"]["name"], t["function"].get("description", "")) for t in ALL_TOOLS]
    total = len(tools)
    for i, (name, desc) in enumerate(tools, 1):
        dh = _desc_hash(desc)
        if not overwrite and data.get(name, {}).get("desc_hash") == dh and data[name].get("examples"):
            print(f"[{i}/{total}] {name} — 已存在，略過")
            continue
        try:
            resp = provider.chat(
                messages=[{"role": "user", "content": _prompt(name, desc)}],
                temperature=0.7, format=_SCHEMA,
            )
            ex = (json.loads(resp.content or "{}") or {}).get("examples") or []
            ex = [str(e).strip()[:60] for e in ex if str(e).strip()][:10]
            if ex:
                data[name] = {"desc_hash": dh, "examples": ex}
                # 每筆即時落盤，跑一半中斷也保留進度
                tmp = _OUT + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, _OUT)
                print(f"[{i}/{total}] {name} — {len(ex)} 例：{ex[:2]}")
            else:
                print(f"[{i}/{total}] {name} — 無輸出，略過")
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{total}] {name} — 失敗：{str(e)[:80]}")
    print(f"完成，已寫入 {_OUT}（共 {len(data)} 個工具）")


if __name__ == "__main__":
    generate()
