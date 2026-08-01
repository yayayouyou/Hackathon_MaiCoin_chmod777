/**
 * 執行期設定。**不進 bundle** —— 它是 public/ 底下的靜態檔，
 * 改一個 S3 物件 + CloudFront invalidate，30 秒就換掉後端位址，不用重 build。
 *
 * 現場最怕的情境：App Runner 換了網址、或臨時要把 demo 切回本機後端，
 * 而 bundle 裡的 base URL 是 build 時寫死的。這個檔就是那個逃生口。
 *
 * 讀取端是 A 軌的 `src/api/config.ts`（尚未落地）：
 *   apiBase() = window.MAIA_CONFIG?.apiBase || import.meta.env.VITE_API_BASE || ''
 * 空字串 = 走同源相對路徑。
 *
 * ⚠ 絕不放金鑰。這個檔是公開的（附錄 B 規則 6：HMAC 在後端）。
 */
window.MAIA_CONFIG = {
  /** 後端位址，空字串 = 同源。例：'https://api.example.com' */
  apiBase: '',
  /** 'live' | 'sample' | 'mock'。空 = 由前端自己判斷 */
  dataMode: '',
};
