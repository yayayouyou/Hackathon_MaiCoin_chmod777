import { useState } from 'react';
import { login, register, type Player } from '../api/auth';

/**
 * 進場的第一步：帳號。
 *
 * **這裡驗的是應用層的玩家帳號，不是交易所憑證。** MAX 的 API 金鑰依舊只活在
 * 後端（見 `state.ts` 檔頭的鐵律），這個表單不會、也永遠不該出現金鑰欄位。
 *
 * 保留「以訪客身分逛逛」是刻意的：`BootScreen` 的三個逃生口存在的理由是
 * 「現場 demo 卡在第一個畫面是最不能出的事」。把登入做成唯一入口，等於在
 * 後端連不上時把整個世界一起鎖死 —— 而世界本身根本不需要帳號才能走。
 */

type Props = {
  onDone: (player: Player) => void;
  onGuest: () => void;
};

export function LoginPanel({ onDone, onGuest }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (): Promise<void> => {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const player = await (mode === 'login'
        ? login(username, password)
        : register(username, password));
      onDone(player);
    } catch (e) {
      setError(e instanceof Error ? e.message : '連線異常。');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="boot-auth" data-testid="login">
      <h1>數位廣場</h1>
      <p className="boot-sub">MAIA · 用走的，把虛擬貨幣的每一種看法走一遍</p>

      <div className="boot-tabs" role="tablist">
        {(['login', 'register'] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            className={`boot-tab${mode === m ? ' is-on' : ''}`}
            onClick={() => { setMode(m); setError(''); }}
          >
            {m === 'login' ? '登入' : '註冊'}
          </button>
        ))}
      </div>

      <label className="boot-nick">
        <span>帳號</span>
        <input
          type="text"
          value={username}
          maxLength={24}
          autoFocus
          autoComplete="username"
          placeholder="3–24 字元，小寫英數"
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void submit()}
        />
      </label>

      <label className="boot-nick">
        <span>密碼</span>
        <input
          type="password"
          value={password}
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          placeholder="至少 8 個字元"
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void submit()}
        />
      </label>

      {/* 錯誤訊息用後端寫好的中文，不是「HTTP 409」 */}
      {error && <p className="boot-err" role="alert">{error}</p>}

      <div className="boot-foot">
        <button type="button" className="boot-guest" onClick={onGuest}>
          以訪客身分逛逛 →
        </button>
        <button type="button" className="btn boot-go" disabled={busy} onClick={() => void submit()}>
          {busy ? '處理中…' : mode === 'login' ? '登入' : '註冊並進入'}
        </button>
      </div>

      <p className="boot-note">
        訪客的暱稱與收藏只存在這台瀏覽器；登入之後會跟著帳號走，換裝置也還在。
      </p>
    </div>
  );
}
