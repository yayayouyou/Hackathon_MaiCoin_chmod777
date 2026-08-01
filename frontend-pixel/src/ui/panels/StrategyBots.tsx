import { useEffect, useState } from 'react';
import { Panel, AsyncState } from '../Panel';
import { useAsync } from '../useAsync';
import {
  listBots,
  createBot,
  startBot,
  stopBot,
  deleteBot,
  type StrategyBot,
  type BotCreate,
} from '../../api/bots';

/**
 * 策略機器人面板（Paper 模擬盤）。
 *
 * 願景的落地：對話中回測驗證過的策略 → 打包成 bot → 在這裡選擇是否運行 →
 * 看它自動模擬成交與即時推理。全程 paper，不碰真錢。後端 runner 每 15 秒
 * 評估一次，這裡每 6 秒重載一次呈現最新狀態。
 */

const STRAT_LABEL: Record<string, string> = {
  ma_crossover: '雙均線交叉',
  rsi_reversal: 'RSI 反轉',
};

const fmt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 0 });
const signed = (n: number) => `${n >= 0 ? '+' : ''}${fmt(n)}`;
const pnlColor = (n: number) => (n > 0 ? 'var(--green)' : n < 0 ? 'var(--rose)' : 'var(--dim)');

function BotCard({ bot, onChange }: { bot: StrategyBot; onChange: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const running = bot.status === 'running';

  const toggle = async () => {
    setBusy(true);
    try {
      if (running) await stopBot(bot.id);
      else await startBot(bot.id);
      onChange();
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    setBusy(true);
    try {
      await deleteBot(bot.id);
      onChange();
    } finally {
      setBusy(false);
    }
  };

  const ev = bot.last_eval;
  return (
    <div className="bot-card">
      <div className="bot-row">
        <span className={`bot-dot ${running ? 'on' : ''}`} aria-hidden="true" />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="bot-name">{bot.name}</div>
          <div className="bot-meta">
            {STRAT_LABEL[bot.strategy_type] ?? bot.strategy_type} · {bot.market.toUpperCase()} ·{' '}
            {bot.period_minutes}m · <span className="bot-mode">Paper</span>
          </div>
        </div>
        <div className="bot-pnl">
          <b style={{ color: pnlColor(bot.total_pnl) }}>
            {signed(bot.total_pnl)} <small>TWD</small>
          </b>
          <span style={{ color: pnlColor(bot.return_pct) }}>{bot.return_pct >= 0 ? '+' : ''}{bot.return_pct}%</span>
        </div>
      </div>

      <div className="bot-actions">
        <span className="bot-tag">{bot.position}</span>
        <span className="bot-tag dim">{bot.trade_count} 筆成交</span>
        <div style={{ flex: 1 }} />
        <button className="bot-btn" disabled={busy} onClick={() => setOpen((v) => !v)}>
          {open ? '收合' : '明細'}
        </button>
        <button className={`bot-btn ${running ? 'stop' : 'start'}`} disabled={busy} onClick={toggle}>
          {running ? '停止' : '啟動'}
        </button>
      </div>

      {open && (
        <div className="bot-detail">
          {ev && (
            <div className="bot-eval">
              <span className="k">即時判斷</span>
              {ev.error ? (
                <span style={{ color: 'var(--rose)' }}>資料讀取失敗：{ev.error}</span>
              ) : (
                <span>
                  {ev.note}
                  {typeof ev.price === 'number' && <em> · 現價 {fmt(ev.price)}</em>}
                  {' → '}
                  <b style={{ color: ev.target ? 'var(--green)' : 'var(--dim)' }}>
                    {ev.target ? '應持有' : '應空手'}
                  </b>
                </span>
              )}
            </div>
          )}
          <div className="bot-trades">
            <span className="k">成交紀錄</span>
            {bot.trades && bot.trades.length > 0 ? (
              bot.trades.map((t, i) => (
                <div key={i} className="bot-trade">
                  <b style={{ color: t.side === 'buy' ? 'var(--green)' : 'var(--rose)' }}>
                    {t.side === 'buy' ? '買入' : '賣出'}
                  </b>
                  <span>{fmt(t.price)}</span>
                  <span className="dim">{t.base.toFixed(6)} · {fmt(t.quote)} TWD</span>
                  <span className="dim reason">{t.reason}</span>
                </div>
              ))
            ) : (
              <div className="muted" style={{ fontSize: 11 }}>
                尚無成交 —— 機器人正在等待訊號觸發（{running ? '運行中' : '已停止'}）。
              </div>
            )}
          </div>
          <button className="bot-btn danger" disabled={busy} onClick={remove}>
            刪除機器人
          </button>
        </div>
      )}
    </div>
  );
}

function CreateForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('BTC 雙均線 5/20');
  const [strat, setStrat] = useState<BotCreate['strategy_type']>('ma_crossover');
  const [market, setMarket] = useState('btctwd');
  const [period, setPeriod] = useState(5);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      const params: Record<string, number> =
        strat === 'ma_crossover'
          ? { fast_period: 5, slow_period: 20 }
          : { rsi_period: 14, oversold: 30, overbought: 70 };
      await createBot({ name, strategy_type: strat, params, market, period_minutes: period });
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : '建立失敗');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bot-create">
      <div className="bot-create-row">
        <input className="bot-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="機器人名稱" />
        <select className="bot-input" value={strat} onChange={(e) => setStrat(e.target.value as BotCreate['strategy_type'])}>
          <option value="ma_crossover">雙均線交叉</option>
          <option value="rsi_reversal">RSI 反轉</option>
        </select>
      </div>
      <div className="bot-create-row">
        <input className="bot-input" value={market} onChange={(e) => setMarket(e.target.value)} placeholder="交易對 (btctwd)" />
        <select className="bot-input" value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
          <option value={1}>1 分 K</option>
          <option value={5}>5 分 K</option>
          <option value={15}>15 分 K</option>
          <option value={60}>1 小時 K</option>
        </select>
        <button className="bot-btn start" disabled={busy || !name.trim()} onClick={submit}>
          打包成機器人
        </button>
      </div>
      {err && <div style={{ color: 'var(--rose)', fontSize: 11 }}>{err}</div>}
    </div>
  );
}

export function StrategyBots() {
  const { data, loading, error, reload } = useAsync(() => listBots(), []);

  // runner 每 15s 動一次，這裡每 6s 重載呈現最新狀態（面板在 #ui-root，非 HUD 骨架，可自由重繪）
  useEffect(() => {
    const id = setInterval(reload, 6000);
    return () => clearInterval(id);
  }, [reload]);

  return (
    <Panel title="策略機器人" accent="max" size="lg">
      <p className="muted" style={{ fontSize: 11, marginBottom: 10 }}>
        把回測驗證過的策略打包成自動化機器人 · 全程 Paper 模擬盤（不下真單）· 後端每 15 秒自動評估
      </p>
      <CreateForm onCreated={reload} />
      <AsyncState loading={loading} error={error} onRetry={reload} />
      {data && (
        <div className="bot-list">
          {data.length === 0 ? (
            <div className="empty">還沒有機器人 —— 在上方打包一支，或請 MAIA 在對話中幫你打包。</div>
          ) : (
            data.map((b) => <BotCard key={b.id} bot={b} onChange={reload} />)
          )}
        </div>
      )}
    </Panel>
  );
}
