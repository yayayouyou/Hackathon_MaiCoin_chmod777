/* MAIA 圖示系統 ——「統一來自約束，可辨來自主題」
   ================================================================
   建構規則（所有圖示一律遵守，這是一致性的來源，不靠美感）：
     · 網格      24×24，內容留 2px 邊距（實際作圖區 20×20）
     · 線寬      2（stroke-width，不縮放；小尺寸靠 CSS 縮放整體）
     · 端點/轉角 round / round（全系統統一，不混用方端）
     · 填充      無（純線性）。需要實心強調時用外框容器上色，不改圖示本身
     · 細節      每個圖示最多 3 個造型元素，避免有的繁複有的空曠
     · 光學重量  以「視覺份量」對齊而非數學尺寸 —— 圓形類略放大、方形類略收

   為什麼是線性 2px：與現行幣安骨架（緊湊、扁平、無陰影）同調；
   實心圖示在深色面上會變成大色塊，會跟色塊分區的圖表打架。

   分類：
     ui      介面控制      generic  通用概念（等同 Lucide 的常見集合）
     status  狀態          trade    交易領域專屬（開源套件沒有的，自行在同網格上繪製）

   刻意不納入：人格符號（🎭🤖🐣🐋🎩）。它們的作用是「有個性」，
   線性圖示傳達不了鯨魚/大師這種角色感，換掉反而失去意義 —— 這是
   有意識的例外，不是漏做。 */

(function (global) {
  "use strict";

  // path/圓/線段以外不使用其他元素；每個值是 <svg> 內部內容
  const P = {
    /* ── ui：介面控制 ─────────────────────────── */
    // 用滑桿而非齒輪：齒輪的齒在 15px 下糊成一團；也刻意不用「圓+射線」
    // 那會與 sun 幾乎同形，違反「可辨」。
    settings: '<path d="M4 9h8M16 9h4M4 16h4M12 16h8"/><circle cx="14" cy="9" r="2.2"/><circle cx="9" cy="16" r="2.2"/>',
    panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M14 4v16"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M22 12h-2M4 12H2M18.4 5.6l-1.4 1.4M7 17l-1.4 1.4M18.4 18.4L17 17M7 7L5.6 5.6"/>',
    moon: '<path d="M20 14.5A8.5 8.5 0 019.5 4a8.5 8.5 0 1010.5 10.5z"/>',
    download: '<path d="M12 3v12M7 11l5 5 5-5M4 20h16"/>',
    send: '<path d="M4 12h14M12 5l7 7-7 7"/>',
    search: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.4-4.4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 20a8 8 0 0116 0"/>',

    /* ── status：狀態（一律形狀＋顏色雙編碼，不可只靠顏色）── */
    check: '<path d="M4 12.5l5.5 5.5L20 7"/>',
    cross: '<path d="M6 6l12 12M18 6L6 18"/>',
    alert: '<path d="M12 3L2 20h20L12 3z"/><path d="M12 10v4M12 17h.01"/>',
    flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    clock: '<circle cx="12" cy="12" r="8"/><path d="M12 8v4.5l3 2"/>',
    shield: '<path d="M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6l7-3z"/>',
    lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>',
    info: '<circle cx="12" cy="12" r="8"/><path d="M12 11v5M12 8h.01"/>',
    halt: '<circle cx="12" cy="12" r="8"/><path d="M9 9h6v6H9z"/>',

    /* ── generic：通用概念 ───────────────────── */
    chart: '<path d="M4 20V4"/><path d="M4 20h16"/><path d="M8 16v-5M13 16V7M18 16v-8"/>',
    trend: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    flask: '<path d="M9 3h6M10 3v6L5 19a2 2 0 001.8 3h10.4a2 2 0 001.8-3l-5-10V3"/><path d="M7.5 15h9"/>',
    compass: '<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5 5-2z"/>',
    book: '<path d="M4 5a2 2 0 012-2h13v18H6a2 2 0 01-2-2V5z"/><path d="M8 3v18"/>',
    gift: '<rect x="3" y="9" width="18" height="12" rx="2"/><path d="M3 13h18M12 9v12"/><path d="M12 9S9.5 3 7.5 4.5 10 9 12 9zM12 9s2.5-6 4.5-4.5S14 9 12 9z"/>',
    brain: '<path d="M12 5a3 3 0 00-6 0 3 3 0 00-2 5.5A3 3 0 006 16a3 3 0 006 1z"/><path d="M12 5a3 3 0 016 0 3 3 0 012 5.5A3 3 0 0118 16a3 3 0 01-6 1z"/>',
    inbox: '<path d="M3 13h5l2 3h4l2-3h5"/><path d="M4.5 6h15l1.5 7v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6L4.5 6z"/>',
    doc: '<path d="M6 3h8l5 5v13H6V3z"/><path d="M14 3v5h5"/><path d="M9 13h7M9 17h5"/>',
    news: '<rect x="3" y="5" width="14" height="15" rx="2"/><path d="M17 9h4v9a2 2 0 01-4 0V9z"/><path d="M6.5 9h7M6.5 13h7M6.5 16.5h4"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a15 15 0 010 18 15 15 0 010-18z"/>',

    /* ── trade：交易領域專屬（開源套件沒有，在同網格上自行繪製）── */
    // 爆倉地圖：價格軸上的密集熱區 —— 用長短不一的直條表示強度分布
    liquidation: '<path d="M3 20h18"/><path d="M6 20v-4M9.5 20v-9M13 20v-6M16.5 20v-11M20 20v-3"/>',
    // 資金費率：多空兩側的週期性收付 —— 上下箭頭夾一條時間軸
    // 時間軸 + 貼著軸線的上下對稱收付箭頭（原本箭頭離軸太遠，小尺寸像三個分離元素）
    funding: '<path d="M3 12h18"/><path d="M8 10V5M8 5L6 7M8 5l2 2"/><path d="M16 14v5M16 19l-2-2M16 19l2-2"/>',
    // 對帳：兩份紀錄相互核對 —— 兩張單據加一個核對勾
    // 兩條並排的紀錄 + 一個大到看得見的核對勾（原本兩張單據錯開、勾太小，15px 下糊成方塊）
    reconcile: '<path d="M4 5h7M4 10h7M4 15h5"/><path d="M13 12.5l3 3 5-6"/>',
    // 艙位：分批堆疊的持有 —— 三層厚度不同的水平塊
    position: '<rect x="4" y="16" width="16" height="4" rx="1"/><rect x="6" y="10" width="12" height="4" rx="1"/><rect x="8" y="4" width="8" height="4" rx="1"/>',
    // 質押：鎖進去產生收益 —— 鎖體加向上的增長線
    staking: '<rect x="3" y="12" width="11" height="8" rx="2"/><path d="M5.5 12V9.5a3 3 0 016 0V12"/><path d="M16 12l2.5-2.5L21 12M18.5 9.5V20"/>',
    // 鏈上：區塊相連 —— 三個方塊由線串起
    onchain: '<rect x="2.5" y="7.5" width="9" height="9" rx="2"/><rect x="12.5" y="7.5" width="9" height="9" rx="2"/><path d="M11.5 12h1"/>',
    // 訂單簿：買賣兩側的深度 —— 中軸兩側長度相反的橫條
    // 不可用「中央直軸＋兩側對稱橫條」：那是漢字「丰」的結構，中文介面會被讀成字。
    // 改為左對齊的賣單/買單兩組深度條，中間一條價差線。
    orderbook: '<path d="M4 4h14M4 8h9"/><path d="M4 12h17"/><path d="M4 16h11M4 20h7"/>',
    // 資金流向：金額在不同去處之間移動 —— 分岔的箭頭
    flow: '<path d="M3 12h6"/><path d="M9 12l5-5h7M9 12l5 5h7"/><path d="M18 4l3 3-3 3M18 14l3 3-3 3"/>',
    // 情緒：市場心理刻度 —— 半圓儀表加指針
    sentiment: '<path d="M4 18a8 8 0 0116 0"/><path d="M12 18l4-5"/><circle cx="12" cy="18" r="1.2"/>',
    // 錢包/帳戶
    wallet: '<path d="M3 7a2 2 0 012-2h12v4"/><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M16 13h2"/>',
  };

  const VB = 24;

  /** 產生一個圖示的 SVG 字串。
   *  @param name  P 的鍵名
   *  @param size  像素尺寸（預設 16）
   *  @param cls   附加 class
   */
  function icon(name, size, cls) {
    const d = P[name];
    if (!d) return "";
    const s = size || 16;
    return (
      `<svg class="ic${cls ? " " + cls : ""}" width="${s}" height="${s}" ` +
      `viewBox="0 0 ${VB} ${VB}" fill="none" stroke="currentColor" ` +
      `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ` +
      `aria-hidden="true" focusable="false">${d}</svg>`
    );
  }

  icon.names = () => Object.keys(P);
  icon.has = (n) => Object.prototype.hasOwnProperty.call(P, n);
  global.icon = icon;
})(window);
