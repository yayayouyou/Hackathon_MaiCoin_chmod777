import { useEffect, useRef, useState } from 'react';
import { getEvents, getNews } from '../../api';
import { PixelCover, eventCover, newsCover, type CoverKind } from '../../ui/PixelCover';
import { setViewInset } from '../../engine/viewport';

/**
 * 行情列正下方的第二條跑馬燈：MAX 最新公告與活動。
 *
 * 為什麼是一條 strip 而不是畫面正中央的浮卡：中央整塊是刻意留給像素世界的
 * （常駐 overlay 會蓋住金幣雕像那個視覺中心，還會擋住點擊移動）。做成貼在
 * 行情列下方的邊條，複用行情跑馬燈那套「兩份等寬內容 + translateX(-50%)」
 * 的純 CSS 無縫捲動，不佔任何一幀 JS、不擋世界。
 *
 * 跟行情列不同的是：這裡的內容**只載入一次**（活動/公告不是每 5 秒在跳的
 * 即時數字），所以直接用一次性的 fetch + state，載完就靜止 —— `#hud-root`
 * 的 childList 在角色走動期間仍維持 0（載入那一次不在走動期間）。
 */

type Chip = { id: string; kind: CoverKind; tag: string; title: string; meta: string };

/** 兩份一模一樣的內容排在一起，動畫捲一半寬度就無縫接回。 */
function Row({ chips }: { chips: Chip[] }) {
  return (
    <>
      {chips.map((c) => (
        <span className="ann-item" key={c.id}>
          <PixelCover kind={c.kind} size={18} />
          <span className="ann-tag">{c.tag}</span>
          <span className="ann-title">{c.title}</span>
          {c.meta && <span className="ann-meta">{c.meta}</span>}
        </span>
      ))}
    </>
  );
}

export function AnnounceStrip() {
  const ref = useRef<HTMLDivElement>(null);
  const [chips, setChips] = useState<Chip[]>([]);

  // 內容一次載入：活動在前（比較搶眼），公告在後。
  useEffect(() => {
    let alive = true;
    Promise.all([getEvents(), getNews()]).then(([events, news]) => {
      if (!alive) return;
      const next: Chip[] = [
        ...events.map((e) => ({
          id: `ev-${e.id}`,
          kind: eventCover(e),
          tag: '活動',
          title: e.title,
          meta: e.reward,
        })),
        ...news.map((n) => ({
          id: `nw-${n.id}`,
          kind: newsCover(n),
          tag: n.category,
          title: n.title,
          meta: n.date,
        })),
      ];
      setChips(next);
    });
    return () => {
      alive = false;
    };
  }, []);

  // 回報遮擋高度給鏡頭。這條在行情列下方，兩條一起佔掉頂部一塊；因為
  // setViewInset 是「每個邊覆蓋寫入」，由下方這條回報**兩條合計**的底邊
  // （getBoundingClientRect().bottom 已含行情列高度），才不會互相蓋掉。
  // 行情列的 effect 先跑（在 Hud 裡排在前面），--ticker-h 這時已就位。
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const bottom = Math.round(el.getBoundingClientRect().bottom);
    setViewInset({ top: bottom });
    // 頂部兩條 strip 的合計底邊。右側 MAIA dock 與收合 tab 的 top 吃這個
    // 變數讓位（沒有它時退回只讓行情列的 --ticker-h），否則 dock 標題列會被
    // 這條公告跑馬燈壓在底下。
    document.documentElement.style.setProperty('--strips-h', `${bottom}px`);
    return () => {
      const tick =
        parseInt(getComputedStyle(document.documentElement).getPropertyValue('--ticker-h')) || 28;
      setViewInset({ top: tick });
      document.documentElement.style.removeProperty('--strips-h');
    };
  }, []);

  return (
    <div className="ann" ref={ref} data-testid="announce-strip">
      <div className="ann-track">
        <div className="ann-row">
          <Row chips={chips} />
        </div>
        <div className="ann-row" aria-hidden="true">
          <Row chips={chips} />
        </div>
      </div>
      <span className="ann-badge">MAX · 公告 / 活動</span>
    </div>
  );
}
