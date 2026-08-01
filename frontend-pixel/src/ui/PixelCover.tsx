import type { EventItem, NewsItem } from '../api/types';

/**
 * 公告 / 活動的「封面圖」。
 *
 * MAX 的公告與活動資料本身沒有圖片欄位，而這個作品的硬規則是不加任何新的
 * runtime 相依、圖示一律零依賴手繪（像素世界那邊是 canvas，UI 這邊就用
 * inline SVG）。所以封面不是去載遠端 banner，而是**依類別／關鍵字程序化畫
 * 一張小像素圖示**：永遠不會 404、載入零延遲、風格跟整個站一致。
 *
 * 同一顆元件同時給 HUD 的活動跑馬燈與 MAX 面板的卡片用，尺寸用 `size` 調。
 */

export type CoverKind =
  | 'notice' // 一般公告
  | 'coin' // 上架 / 入金 / 回饋
  | 'wrench' // 維護 / 硬分叉
  | 'shield' // 資安
  | 'card' // 信用卡 / 幣享卡
  | 'ticket' // 抽獎
  | 'token' // MAX Token / 鎖倉
  | 'gift'; // 一般活動

/** 依公告分類決定封面。分類是嚴格聯集，switch 一定涵蓋到。 */
export function newsCover(n: NewsItem): CoverKind {
  switch (n.category) {
    case '上架':
      return 'coin';
    case '維護':
      return 'wrench';
    case '安全':
      return 'shield';
    default:
      return 'notice';
  }
}

/** 依活動標題關鍵字挑一張最貼切的封面，都不中就用禮物盒。 */
export function eventCover(e: EventItem): CoverKind {
  const t = e.title;
  if (/卡|刷|信用/.test(t)) return 'card';
  if (/抽|獎/.test(t)) return 'ticket';
  if (/token|鎖倉|持有/i.test(t)) return 'token';
  if (/usdt|入金|回饋|\$|回贈/i.test(t)) return 'coin';
  return 'gift';
}

/** 每種封面的底色。白色主圖形之上的細節也用這個色，做成雙色圖示。 */
const BG: Record<CoverKind, string> = {
  notice: '#3f5fd6',
  coin: '#e0a534',
  wrench: '#5f6f8a',
  shield: '#37b06a',
  card: '#4f74e6',
  ticket: '#9a6fe0',
  token: '#e0a534',
  gift: '#e07a4e',
};

const W = '#f2f6ff';

/** 各封面的主圖形。座標都在 16x16 的 viewBox 內，內容留在 3..13 一圈。 */
function Glyph({ kind, bg }: { kind: CoverKind; bg: string }) {
  switch (kind) {
    case 'notice':
      return (
        <>
          <rect x="4" y="2.6" width="8" height="10.8" rx="0.8" fill={W} />
          <rect x="5.6" y="5" width="4.8" height="1" fill={bg} />
          <rect x="5.6" y="7.2" width="4.8" height="1" fill={bg} />
          <rect x="5.6" y="9.4" width="3.2" height="1" fill={bg} />
        </>
      );
    case 'coin':
      return (
        <>
          <circle cx="8" cy="8" r="4.8" fill={W} />
          <circle cx="8" cy="8" r="2.5" fill="none" stroke={bg} strokeWidth="1.1" />
          <circle cx="8" cy="8" r="0.8" fill={bg} />
        </>
      );
    case 'token':
      return (
        <>
          <path d="M8 3 L12.2 5.4 V10.6 L8 13 L3.8 10.6 V5.4 Z" fill={W} />
          <path d="M6.3 9.6 V6.6 L8 8.3 L9.7 6.6 V9.6" fill="none" stroke={bg} strokeWidth="1" strokeLinejoin="round" />
        </>
      );
    case 'wrench':
      return (
        <>
          <circle cx="8" cy="8" r="3.1" fill={W} />
          <circle cx="8" cy="8" r="1.2" fill={bg} />
          <rect x="7.3" y="2.3" width="1.4" height="2.1" fill={W} />
          <rect x="7.3" y="11.6" width="1.4" height="2.1" fill={W} />
          <rect x="2.3" y="7.3" width="2.1" height="1.4" fill={W} />
          <rect x="11.6" y="7.3" width="2.1" height="1.4" fill={W} />
        </>
      );
    case 'shield':
      return (
        <>
          <path d="M8 2.6 L12.4 4.2 V8 C12.4 10.6 10.4 12.3 8 13.4 C5.6 12.3 3.6 10.6 3.6 8 V4.2 Z" fill={W} />
          <path d="M6 8 L7.4 9.4 L10 6.4" fill="none" stroke={bg} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        </>
      );
    case 'card':
      return (
        <>
          <rect x="2.6" y="4.4" width="10.8" height="7.2" rx="1.1" fill={W} />
          <rect x="2.6" y="6" width="10.8" height="1.7" fill={bg} />
          <rect x="4" y="9" width="3.2" height="1.4" rx="0.3" fill={bg} />
        </>
      );
    case 'ticket':
      return (
        <>
          <rect x="3" y="5" width="10" height="6" rx="1" fill={W} />
          <circle cx="3" cy="8" r="1.2" fill={bg} />
          <circle cx="13" cy="8" r="1.2" fill={bg} />
          <g stroke={bg} strokeWidth="1" strokeLinecap="round">
            <line x1="8" y1="6.4" x2="8" y2="9.6" />
            <line x1="6.6" y1="7.2" x2="9.4" y2="8.8" />
            <line x1="9.4" y1="7.2" x2="6.6" y2="8.8" />
          </g>
        </>
      );
    case 'gift':
      return (
        <>
          <rect x="3.4" y="6.6" width="9.2" height="6.4" rx="0.8" fill={W} />
          <rect x="7.2" y="6.6" width="1.6" height="6.4" fill={bg} />
          <path d="M8 6.4 C6.2 4.8 4.4 6 6.2 6.6 M8 6.4 C9.8 4.8 11.6 6 9.8 6.6" fill="none" stroke={W} strokeWidth="1.1" />
        </>
      );
  }
}

export function PixelCover({ kind, size = 28 }: { kind: CoverKind; size?: number }) {
  const bg = BG[kind];
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      role="img"
      aria-hidden="true"
      style={{ flex: 'none', display: 'block', borderRadius: Math.max(3, Math.round(size * 0.16)) }}
    >
      <rect width="16" height="16" rx="2.4" fill={bg} />
      {/* 內外兩道描邊：外深內亮，做出跟像素世界道具一致的斜角立體感 */}
      <rect x="0.5" y="0.5" width="15" height="15" rx="2" fill="none" stroke="#ffffff26" strokeWidth="1" />
      <rect x="0" y="0" width="16" height="16" rx="2.4" fill="none" stroke="#00000055" strokeWidth="1" />
      <g shapeRendering="geometricPrecision">
        <Glyph kind={kind} bg={bg} />
      </g>
    </svg>
  );
}
