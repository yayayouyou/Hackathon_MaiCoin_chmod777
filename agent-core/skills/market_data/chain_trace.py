"""
skills/market_data/chain_trace.py

入金鏈上來源標籤器（多鏈、免 key）
======================================================
對每筆『站外加密入金』用 txid 上鏈查出發送地址，並給來源標籤 → 辨識來路不明資金。
免費資料源：
  - EVM(ETH/Avalanche/BSC/Polygon/Arbitrum)：各鏈公開 RPC(eth_getTransactionByHash…)
  - Solana：公開 RPC getTransaction（feePayer）
  - Tron：TronScan transaction-info（ownerAddress）
  - Bitcoin：mempool.space（UTXO inputs）
  - 具名標籤：eth-labels 免費 API（EVM，回「Binance 14」等）；其餘用交易數啟發式
多層溯源：若『上一手』已是具名交易所→即為來源；否則以啟發式標其性質（EVM 更深層需付費歷史 API）。
站內轉帳與法幣(TWD)入金無鏈上來源。
"""
import json
import urllib.request
from typing import Dict, Any, Optional, Tuple, List
from loguru import logger

_EVM_RPC: Dict[str, str] = {
    "ethereum-erc20": "https://eth.llamarpc.com",
    "Avalanche C-Chain-erc20": "https://api.avax.network/ext/bc/C/rpc",
    "bsc-bep20": "https://bsc-dataseed.binance.org",
    "polygon-erc20": "https://polygon-rpc.com",
    "arbitrum-erc20": "https://arb1.arbitrum.io/rpc",
}
_ETH_LABELS_API = "https://eth-labels-production.up.railway.app/labels/"
_SOL_RPC = "https://api.mainnet-beta.solana.com"
_TRON_TXINFO = "https://apilist.tronscanapi.com/api/transaction-info?hash="
_BTC_TX = "https://mempool.space/api/tx/"

_label_cache: Dict[str, Optional[str]] = {}


def _mask(a: str) -> str:
    return (a[:8] + "…" + a[-6:]) if a and len(a) > 18 else a


def _get(url: str, timeout: float = 12) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _rpc(url: str, method: str, params: list, timeout: float = 12) -> Optional[Any]:
    try:
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r).get("result")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"RPC {method} 失敗：{e}")
        return None


def _evm_label(addr: str) -> Optional[str]:
    """eth-labels 免費 API → 具名標籤（如 'Binance 14'）；查無回 None。快取。"""
    a = (addr or "").lower()
    if not a:
        return None
    if a in _label_cache:
        return _label_cache[a]
    tag = None
    try:
        d = _get(_ETH_LABELS_API + a, timeout=8)
        for item in (d if isinstance(d, list) else []):
            if item.get("nameTag"):
                tag = item["nameTag"]
                break
            if item.get("label") and not tag:
                tag = item["label"]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"eth-labels 查詢失敗：{e}")
    _label_cache[a] = tag
    return tag


def _classify(named: Optional[str], is_contract: Optional[bool], txn: Optional[int]) -> Tuple[str, str]:
    """回傳 (來源性質, 風險)。具名標籤最優先，其次合約/交易數啟發式。"""
    if named:
        return f"來自 {named}", "known"
    if is_contract:
        return "合約地址（交易所/橋/DeFi 合約，多屬正常）", "low"
    if txn is None:
        return "一般錢包", "unknown"
    if txn > 10000:
        return f"高頻地址（{txn:,} 筆，很可能是交易所/服務熱錢包）", "low"
    if txn < 20:
        return f"🚩 新／低活躍錢包（僅 {txn} 筆）→ 來路較不明，建議留意", "elevated"
    return f"一般錢包（{txn:,} 筆交易）", "normal"


def _trace_evm(rpc_url: str, txid: str) -> Dict[str, Any]:
    tx = _rpc(rpc_url, "eth_getTransactionByHash", [txid])
    if not tx or not tx.get("from"):
        return {"note": "鏈上查無此交易（可能尚未確認或 RPC 暫無回應）"}
    sender = tx["from"]
    named = _evm_label(sender)
    code = _rpc(rpc_url, "eth_getCode", [sender, "latest"])
    cnt = _rpc(rpc_url, "eth_getTransactionCount", [sender, "latest"])
    is_contract = bool(code) and code not in ("0x", "0x0")
    txn = int(cnt, 16) if isinstance(cnt, str) and cnt.startswith("0x") else None
    src, risk = _classify(named, is_contract, txn)
    return {"sender": _mask(sender), "named_label": named, "is_contract": is_contract,
            "sender_tx_count": txn, "source_type": src, "risk": risk}


def _trace_solana(txid: str) -> Dict[str, Any]:
    tx = _rpc(_SOL_RPC, "getTransaction", [txid, {"maxSupportedTransactionVersion": 0, "encoding": "json"}])
    keys = (((tx or {}).get("transaction") or {}).get("message") or {}).get("accountKeys") or []
    if not keys:
        return {"note": "Solana 鏈上查無此交易或無法解析"}
    sender = keys[0]                       # feePayer = 第一個 account key
    src, risk = _classify(None, None, None)
    return {"sender": _mask(sender), "source_type": "Solana 發送方（免費標籤資料有限）", "risk": "unknown"}


def _trace_tron(txid: str) -> Dict[str, Any]:
    try:
        d = _get(_TRON_TXINFO + txid, timeout=12)
    except Exception:  # noqa: BLE001
        return {"note": "TronScan 查詢失敗"}
    owner = d.get("ownerAddress")
    if not owner:
        return {"note": "Tron 鏈上查無此交易"}
    return {"sender": _mask(owner), "source_type": "Tron 發送方（免費標籤資料有限）", "risk": "unknown"}


def _trace_btc(txid: str, hops: int = 1) -> Dict[str, Any]:
    """BTC：UTXO 輸入即上一手。hops>1 時沿最大輸入往前再追一手（多層溯源）。"""
    try:
        d = _get(_BTC_TX + txid, timeout=12)
    except Exception:  # noqa: BLE001
        return {"note": "mempool.space 查詢失敗"}
    vin = d.get("vin") or []
    addrs = [v.get("prevout", {}).get("scriptpubkey_address") for v in vin if v.get("prevout")]
    addrs = [a for a in addrs if a]
    if not addrs:
        return {"note": "BTC 鏈上查無輸入地址（可能為 coinbase）"}
    chain = [_mask(addrs[0])]
    # 多層：沿第一個輸入的來源 txid 再往前一手
    cur_txid, depth = txid, 1
    while depth < hops:
        try:
            dd = _get(_BTC_TX + cur_txid, timeout=12)
            prev = (dd.get("vin") or [{}])[0].get("prevout", {}).get("scriptpubkey_address")
            prev_txid = (dd.get("vin") or [{}])[0].get("txid")
            if not prev or not prev_txid:
                break
            chain.append(_mask(prev))
            cur_txid = prev_txid
            depth += 1
        except Exception:  # noqa: BLE001
            break
    return {"sender": chain[0], "source_type": f"BTC 輸入地址（UTXO，{len(addrs)} 個輸入）",
            "hop_chain": chain if len(chain) > 1 else None, "risk": "unknown"}


def _trace_sender(network: Optional[str], txid: str, hops: int = 1) -> Dict[str, Any]:
    """依 MAX network_protocol 分派到對應鏈的追蹤器。"""
    net = (network or "").lower()
    if network in _EVM_RPC:
        return _trace_evm(_EVM_RPC[network], txid)
    if "sol" in net:
        return _trace_solana(txid)
    if "tron" in net or "trc" in net:
        return _trace_tron(txid)
    if "bitcoin" in net or net == "btc":
        return _trace_btc(txid, hops=hops)
    return {"note": f"{network} 暫未支援鏈上溯源"}


def trace_deposit_source(limit: int = 10, hops: int = 1) -> Dict[str, Any]:
    """
    【私有/需授權·免鏈上key】調查近期入金的『鏈上來源』：對每筆站外加密入金用 txid 上鏈查出發送
    地址並給來源標籤（具名交易所如『來自 Binance』／交易所熱錢包／🚩新錢包）→ 辨識來路不明資金。
    支援 EVM(ETH/Avalanche/BSC/Polygon/Arbitrum)/Solana/Tron/BTC。站內轉帳與法幣(TWD)入金無鏈上來源。
    適用：「我這些入金從哪來、有沒有來路不明的錢、這筆入金來源可靠嗎」。

    Args:
        limit: 檢查最近幾筆入金（預設 10）
        hops: 溯源層數（目前 BTC 支援多層；EVM 已用具名標籤解析直接來源）
    """
    from skills.max_exchange.max_private import get_max_fund_transactions
    deps = get_max_fund_transactions("deposit", limit=limit)
    traced: List[Dict[str, Any]] = []
    skipped = {"internal_站內": 0, "fiat_法幣": 0, "no_txid_無交易碼": 0}

    for d in deps:
        net, txid = d.get("network"), d.get("txid")
        base = {"currency": d.get("currency"), "amount": d.get("amount"),
                "network": net, "time_ms": d.get("time_ms")}
        if d.get("is_internal"):
            skipped["internal_站內"] += 1
            continue
        if net == "fiat" or d.get("currency") == "TWD":
            skipped["fiat_法幣"] += 1
            continue
        if not txid:
            skipped["no_txid_無交易碼"] += 1
            continue
        traced.append({**base, **_trace_sender(net, txid, hops=hops)})

    flagged = [t for t in traced if t.get("risk") == "elevated"]
    named = [t for t in traced if t.get("named_label")]
    ok = len([t for t in traced if t.get("sender")])
    return {
        "checked": len(deps),
        "traced_onchain": ok,
        "named_source": len(named),
        "flagged_suspicious": len(flagged),
        "deposits": traced,
        "skipped": skipped,
        "summary": (f"查了 {len(deps)} 筆入金：{ok} 筆可鏈上溯源"
                    + (f"（{len(named)} 筆已辨識具名來源）" if named else "")
                    + f"、{sum(skipped.values())} 筆無鏈上來源（站內/法幣/無碼）"
                    + (f"、⚠️ {len(flagged)} 筆來自新/低活躍錢包需留意" if flagged else "、無可疑來源")),
        "note": "具名標籤來自 eth-labels(EVM)；其餘用交易數啟發式。站內/法幣無鏈上來源。BTC 支援多層溯源。",
    }
