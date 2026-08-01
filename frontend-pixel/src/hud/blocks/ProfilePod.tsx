import { openPanel, useUI } from '../../ui/uiStore';
import { CharPreview } from '../../boot/CharPicker';

/**
 * 左下角的角色卡 —— 遊戲裡的「個人資訊」。
 *
 * 它常駐在世界上，而不是藏在一個要按 `I` 才會出現的彈窗裡。理由是這張卡
 * 回答的是評審在前三十秒就會問的兩個問題：「這是誰的帳戶」與「資料是真的
 * 還假的」。把它做成常駐，那兩個問題就不必用嘴巴回答。
 *
 * ⚠ 這裡只放**不會每幀變動**的東西：頭像、暱稱、連接狀態。
 *   持倉市值與未實現損益是每 5 秒跳一次的數值，它們屬於 HUD 的行情條
 *   （走 `LiveText` 命令式更新），不要為了排版方便塞進這張用 React 畫的卡 ——
 *   `#hud-root` 的 childList/attributes 變動必須維持 0。
 */
export function ProfilePod() {
  const { nickname, connected, character } = useUI();

  return (
    <button className="pod" onClick={() => openPanel('char')} data-testid="profile-pod">
      {/*
        頭像原本是四個 CSS 方塊拼的，寫死深棕髮 + 青色。可以換角色之後那份
        寫死的顏色就開始說謊 —— 選了兜帽，左下角還是短髮。改成直接畫世界裡
        那張圖的頭部，換角色時這裡自動跟著對。

        canvas 只在 mount 與換角色時畫一次，之後不再動 DOM，所以「走動期間
        #hud-root 變動為 0」那條斷言仍然成立。
      */}
      <span className="pod-face">
        <CharPreview id={character} scale={2} head />
      </span>
      <span className="pod-text">
        <span className="pod-name">{nickname}</span>
        <span className="pod-state" data-on={connected ? '1' : '0'}>
          {connected ? '● 已連接 MAX' : '○ 訪客模式'}
        </span>
      </span>
      <kbd>I</kbd>
    </button>
  );
}
