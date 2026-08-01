import { Panel } from '../Panel';
import { Trade } from './Trade';

/**
 * 現貨交易的獨立面板殼。
 *
 * `Trade` 本身是無 props 的完整元件（行情 + 下單 + 持倉），原本只活在
 * `CharPanel` 的分頁裡。包這一層讓它可以從世界的互動點直接開啟，
 * 不必先打開角色訊息窗再切到交易分頁。
 *
 * ⚠ `<Panel>` 不是裝飾，少了它是一個死結。
 *   這個檔原本直接 `return <Trade />` —— 於是從世界按 E 開現貨交易時：
 *   `activePanel` 被設成 'trade' → `game/index.ts` 的 `frozen` 為真、
 *   世界凍住 → 但畫面上沒有遮罩、沒有標題列、也沒有 ESC 監聽器
 *   （ESC 掛在 `Panel.tsx` 的 useEffect 裡，隨元件掛載才存在），
 *   交易面板就這樣裸貼在畫面左上角，關不掉、也走不動，只能重整。
 *   `uiStore.openPanel()` 的註解說「絕不能讓 activePanel 被設成一個渲染
 *   不出東西的值」，防的正是這件事，只是它守的是 id 有沒有註冊，守不到
 *   「註冊了但忘記包殼」。
 *
 *   症狀在測試裡是 6 條紅燈（互動回饋 / 觸控 / 狀態 / 功能條各兩條），
 *   全部長成「面板打不開」—— 因為它們等的是 `.panel` 這個 class。
 */
export function TradePanel() {
  return (
    <Panel title="MAX 現貨交易" accent="max" size="lg">
      <Trade />
    </Panel>
  );
}
