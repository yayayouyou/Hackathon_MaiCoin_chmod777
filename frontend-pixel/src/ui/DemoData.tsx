/**
 * 「這一塊是假資料」的統一標示。
 *
 * 存在的理由很單純：示範資料本身不是問題，**看起來像真的才是**。
 * 評審看到一份寫著 42.7% 報酬率的策略牆，沒有理由知道那是編的。
 *
 * 用在所有還沒有後端端點的面板。一旦某塊接上真後端，就把它拿掉 ——
 * 畫面上還留著這個標籤，等於自己說謊的反面：低估了已經做出來的東西。
 */
export function DemoData({ what }: { what: string }) {
  return (
    <p
      className="muted"
      role="note"
      style={{
        fontSize: 11,
        lineHeight: 1.5,
        margin: '0 0 12px',
        padding: '6px 10px',
        border: '1px dashed var(--line)',
        borderRadius: 4,
        color: 'var(--amber)',
      }}
    >
      ⚠ 目前是假資料 —— {what}尚未接上後端，以下內容為展示用的示範資料。
    </p>
  );
}
