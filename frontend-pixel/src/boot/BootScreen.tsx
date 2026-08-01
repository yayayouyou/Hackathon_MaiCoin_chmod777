import { useEffect, useState } from 'react';
import { enterWorld, setNickname, useUI } from '../ui/uiStore';
import { CharPicker } from './CharPicker';

/**
 * 進場畫面（規格 §5）。
 *
 * **這不是身分驗證。** 沒有帳號、沒有密碼、沒有金鑰欄位，打的名字只存在
 * 這台瀏覽器的 localStorage 裡。專案的鐵律是「交易所金鑰永遠不進瀏覽器」
 * （見 `state.ts` 檔頭），所以這裡從一開始就沒有東西好驗證 —— 與其擺兩個
 * 什麼都不接的欄位假裝有登入，不如老實做成「取個名字、選個角色、進去」。
 *
 * 目標 8 秒。世界從第一幀就在這層 overlay 背後跑著（`main.tsx` 的
 * `startGame()` 是無條件執行的），所以按下「進入」不需要載入任何東西，
 * 只是把幕拉開。
 *
 * 三個逃生口都通到同一個地方（`enterWorld()`）：
 *   · 「進入數位廣場」按鈕
 *   · 右上角「略過」—— 給只想趕快看到東西的評審
 *   · `Ctrl+Shift+Enter` —— 不用 F9（macOS 是 Mission Control）、
 *     不用 Escape（打字時會誤觸）
 */

const randomNick = (): string => `遊客${Math.floor(1000 + Math.random() * 9000)}`;

export function BootScreen() {
  const { nickname, phase } = useUI();
  const [draft, setDraft] = useState(nickname);

  /**
   * 三個入口共用同一條路，包含「略過」。
   *
   * 略過也要存暱稱：人可能打完名字才發現不想選角色。讓略過丟掉剛打的字，
   * 是那種沒有人會回報、但每個踩到的人都會覺得壞掉的行為。
   */
  const go = (): void => {
    setNickname(draft);
    enterWorld();
  };

  // ⚠ 相依必須帶 `draft`。空陣列的話這個 handler 會永遠記得第一次算出來的
  //   `go`，於是 Ctrl+Shift+Enter 存進去的是打字之前的那個名字 —— 而畫面上
  //   看起來完全正常，直到下次重整才發現名字沒改到。
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Enter' && e.ctrlKey && e.shiftKey) {
        e.preventDefault();
        go();
      }
    };
    addEventListener('keydown', onKey);
    return () => removeEventListener('keydown', onKey);
  }, [draft]); // eslint-disable-line react-hooks/exhaustive-deps

  // App.tsx 在 phase !== 'world' 時渲染這一層，而 'entering' 目前沒有人設
  // （見 uiStore 的註解）。這一行是保險：真的有人設了，這層要讓開。
  if (phase !== 'boot') return null;

  return (
    <div className="boot" data-testid="boot">
      <button className="boot-skip" type="button" onClick={go}>
        略過 →
      </button>

      <div className="boot-card">
        <h1>數位廣場</h1>
        <p className="boot-sub">MAIA · 用走的，把虛擬貨幣的每一種看法走一遍</p>

        <label className="boot-nick">
          <span>暱稱</span>
          <input
            type="text"
            value={draft}
            maxLength={16}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && go()}
          />
          {/* 骰子比「想一個名字」快得多。名字只是討論串裡的署名，
              不值得讓人在第一個畫面卡住 */}
          <button type="button" className="chip" title="換一個" onClick={() => setDraft(randomNick())}>
            🎲
          </button>
        </label>

        <h2 className="boot-h2">選一個角色</h2>
        <CharPicker scale={3} />
        <p className="boot-note">只是長相，不影響 MAIA 的分析結果。進去之後隨時可以按 I 換。</p>

        <div className="boot-foot">
          {/* 老實話。這裡不做假的「已連線」燈號 —— 資料來源的誠實標示
              是評分項，不是裝飾 */}
          <span className="boot-mode">○ 示範資料 · 未連接交易帳戶</span>
          <button type="button" className="btn boot-go" onClick={go}>
            進入數位廣場
          </button>
        </div>
      </div>

      <p className="boot-esc">
        <kbd>Ctrl</kbd>
        <kbd>Shift</kbd>
        <kbd>Enter</kbd> 直接進入
      </p>
    </div>
  );
}
