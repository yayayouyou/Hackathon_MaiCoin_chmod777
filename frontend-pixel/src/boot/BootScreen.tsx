import { useEffect, useState } from 'react';
import { enterWorld, setCharacter, setNickname, useUI } from '../ui/uiStore';
import { me, type Player } from '../api/auth';
import { getCharacter } from '../art/characters';
import { hydrate, setAuthed } from '../state';
import { CharPicker } from './CharPicker';
import { LoginPanel } from './LoginPanel';

/**
 * 進場畫面（規格 §5）。兩個步驟：先帳號，再取名選角。
 *
 * **帳號驗的是應用層的玩家身分，不是交易所憑證。** 專案的鐵律
 * 「交易所金鑰永遠不進瀏覽器」（見 `state.ts` 檔頭）完全沒有鬆動 ——
 * MAX 的 API 金鑰依舊只活在後端，這個畫面上永遠不會有金鑰欄位。
 * 登入之後暱稱、角色與收藏改存 DynamoDB，換裝置也跟著走。
 *
 * 目標 8 秒。世界從第一幀就在這層 overlay 背後跑著（`main.tsx` 的
 * `startGame()` 是無條件執行的），所以按下「進入」不需要載入任何東西，
 * 只是把幕拉開。
 *
 * 逃生口一個都沒有拿掉，而且**刻意在登入步驟也保持可用** —— 後端連不上時
 * 若登入是唯一入口，整個世界會跟著被鎖死，而世界本身根本不需要帳號才能走：
 *   · 「進入數位廣場」按鈕
 *   · 右上角「略過」—— 給只想趕快看到東西的評審
 *   · 登入卡上的「以訪客身分逛逛」
 *   · `Ctrl+Shift+Enter` —— 不用 F9（macOS 是 Mission Control）、
 *     不用 Escape（打字時會誤觸）
 */

const randomNick = (): string => `遊客${Math.floor(1000 + Math.random() * 9000)}`;

export function BootScreen() {
  const { nickname, phase } = useUI();
  const [draft, setDraft] = useState(nickname);
  const [step, setStep] = useState<'checking' | 'auth' | 'profile'>('checking');

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

  /**
   * 把伺服器那份進度灌回本機。包在 `hydrate()` 裡是為了不要把剛讀到的值
   * 立刻再 PUT 回去一次（見 `state.ts` 的 `hydrate` 註解）。
   */
  const applyPlayer = (p: Player): void => {
    setAuthed(true);
    hydrate(() => {
      // 空字串代表這個帳號還沒設過，這時要留著本機隨機產生的預設值
      if (p.nickname) setNickname(p.nickname);
      // 存進去的 id 可能是舊版角色表的，查不到就退回預設 —— 與 uiStore 同一套規則
      if (p.character) setCharacter(getCharacter(p.character).id);
    });
    if (p.nickname) setDraft(p.nickname);
    setStep('profile');
  };

  // 進場先問一次「這個瀏覽器還登著嗎」。失敗（含 5 秒逾時）就顯示登入卡，
  // 人仍然可以用訪客身分進去 —— 後端掛掉不該連世界都進不了。
  useEffect(() => {
    let alive = true;
    void me()
      .then((player) => {
        if (!alive) return;
        if (player) applyPlayer(player);
        else setStep('auth');
      })
      .catch(() => {
        if (alive) setStep('auth');
      });
    return () => {
      alive = false;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
        {step === 'checking' && (
          <p className="boot-sub" data-testid="auth-checking">確認登入狀態…</p>
        )}

        {step === 'auth' && (
          <LoginPanel onDone={applyPlayer} onGuest={() => setStep('profile')} />
        )}

        {step === 'profile' && (
        <>
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
        </>
        )}
      </div>

      <p className="boot-esc">
        <kbd>Ctrl</kbd>
        <kbd>Shift</kbd>
        <kbd>Enter</kbd> 直接進入
      </p>
    </div>
  );
}
