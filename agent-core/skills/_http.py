"""
skills/_http.py — 共用 HTTP 韌性層 (Shared HTTP Resilience Layer)
=====================================================
治本基礎：所有對外抓取都應改用這裡的 session_get / session_post / fetch_json，
一次獲得整個 skills 樹缺失的四件事：

  1. 連線重用       — 單一 pooled requests.Session（省去每次 TCP+TLS 握手）
  2. 自動重試退避   — 429 / 5xx 指數退避，尊重 Retry-After（GET/HEAD only；POST 不自動重試，保護下單冪等性）
  3. 每主機限流     — token-bucket 最小間隔，避免單一 IP 爆量被 ban（免費層殺手）
  4. 統一 UA/逾時   — 集中管理 User-Agent 與 (connect, read) 逾時預設

另附 fetch_json()：一致的「抓取即驗證」入口，抓失敗一律拋 FetchError，
杜絕「靜默失敗當成有效數據」（稽核 #1 風險）。呼叫端 catch 後轉成自己的工具結果 dict。
"""
import time
import threading
from typing import Optional, Dict, Any, Iterable
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except Exception:  # noqa: BLE001 - 極少數環境路徑不同
    from requests.packages.urllib3.util.retry import Retry  # type: ignore


# 當前一般瀏覽器 UA（部分來源會擋預設 python-requests UA）
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = (3.05, 15)  # (connect, read) 秒

# 每主機最小請求間隔（秒）— 依各免費層限制保守設定，未列的主機不限流
_MIN_INTERVAL: Dict[str, float] = {
    "api.coingecko.com": 0.7,             # Demo key 100 req/min（≈85/min 保守值）
    "pro-api.coinmarketcap.com": 2.5,     # 免費信用點數有限
    "www.reddit.com": 2.0,
    "oauth.reddit.com": 1.0,
    "api.pushshift.io": 2.0,
    "fapi.binance.com": 0.25,             # 權重制，避免 418 IP ban
    "api.bybit.com": 0.25,
    "www.okx.com": 0.25,
    "max-api.maicoin.com": 0.3,
    "capi.coinglass.com": 1.0,
    "open-api-v4.coinglass.com": 1.0,
    "html.duckduckgo.com": 3.0,
    "lite.duckduckgo.com": 3.0,
    "openapi.sosovalue.com": 3.4,         # Demo 免費層 ~20 req/min → 保守 >3s 間隔（ETF/財庫/指數/概念股共用）
    "api.coinalyze.net": 1.6,             # 免費層 40 req/min → 保守 ~1.5s 間隔
    "api.stlouisfed.org": 0.6,            # FRED 免費層寬鬆，保守限流
    "www.alphavantage.co": 13.0,          # 免費層 5 req/min → 保守 >12s 間隔
}
_DEFAULT_INTERVAL = 0.0

_last_call: Dict[str, float] = {}
_throttle_lock = threading.Lock()


class FetchError(Exception):
    """對外抓取失敗（網路、HTTP 4xx/5xx、非 JSON、缺欄位）。呼叫端應轉為工具錯誤結果。"""


def _host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return ""


def _throttle(host: str) -> None:
    """每主機最小間隔限流；sleep 時不持鎖，避免拖累其他主機。"""
    interval = _MIN_INTERVAL.get(host, _DEFAULT_INTERVAL)
    if interval <= 0:
        return
    while True:
        with _throttle_lock:
            now = time.monotonic()
            wait = interval - (now - _last_call.get(host, 0.0))
            if wait <= 0:
                _last_call[host] = now
                return
        time.sleep(min(wait, interval))


_session: Optional[requests.Session] = None
_session_lock = threading.Lock()


def _build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=2,
        status=3,
        backoff_factor=0.6,                              # 0.6,1.2,2.4s…
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),      # 不重試 POST（下單非冪等，安全第一）
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=32)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": DEFAULT_UA,
        "Accept-Encoding": "gzip, deflate",
    })
    return s


def get_session() -> requests.Session:
    """回傳行程內共用的 pooled Session（延遲建立、執行緒安全）。"""
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = _build_session()
    return _session


def session_get(url: str, *, timeout=DEFAULT_TIMEOUT, throttle: bool = True, **kwargs) -> requests.Response:
    """共用 Session 的 GET：連線重用 + 自動重試退避 + 每主機限流。"""
    if throttle:
        _throttle(_host_of(url))
    return get_session().get(url, timeout=timeout, **kwargs)


def session_post(url: str, *, timeout=DEFAULT_TIMEOUT, throttle: bool = True, **kwargs) -> requests.Response:
    """共用 Session 的 POST：連線重用 + 限流，但『不』自動重試（保護下單冪等性）。"""
    if throttle:
        _throttle(_host_of(url))
    return get_session().post(url, timeout=timeout, **kwargs)


def session_delete(url: str, *, timeout=DEFAULT_TIMEOUT, throttle: bool = True, **kwargs) -> requests.Response:
    """共用 Session 的 DELETE：連線重用 + 限流，不自動重試（撤單非冪等）。"""
    if throttle:
        _throttle(_host_of(url))
    return get_session().delete(url, timeout=timeout, **kwargs)


def fetch_json(
    url: str,
    *,
    method: str = "GET",
    expect_keys: Optional[Iterable[str]] = None,
    ok_status: Iterable[int] = (200,),
    **kwargs,
) -> Any:
    """
    抓取即驗證：GET/POST → 檢查狀態 → 解析 JSON →（可選）驗證必要欄位。
    任一步失敗一律拋 FetchError（杜絕靜默失敗）。呼叫端 catch 後轉成工具結果。
    """
    fn = session_post if method.upper() == "POST" else session_get
    try:
        resp = fn(url, **kwargs)
    except requests.RequestException as e:
        raise FetchError(f"連線失敗 {_host_of(url)}: {e.__class__.__name__}") from e
    if resp.status_code not in ok_status:
        raise FetchError(f"HTTP {resp.status_code} @ {_host_of(url)}")
    try:
        data = resp.json()
    except ValueError as e:
        raise FetchError(f"非 JSON 回應 @ {_host_of(url)}") from e
    if expect_keys and isinstance(data, dict):
        missing = [k for k in expect_keys if k not in data]
        if missing:
            raise FetchError(f"回應缺少預期欄位 {missing} @ {_host_of(url)}")
    return data


def set_min_interval(host: str, seconds: float) -> None:
    """執行期調整某主機限流間隔（供測試或動態調速）。"""
    _MIN_INTERVAL[host] = seconds


def reset_state() -> None:
    """重置 Session 與限流狀態（僅供測試）。"""
    global _session
    with _session_lock:
        _session = None
    with _throttle_lock:
        _last_call.clear()
