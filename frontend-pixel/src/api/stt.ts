/**
 * 語音轉文字客戶端。
 *
 * 前端只做一件事：把瀏覽器錄好的音檔 blob POST 到同源 /api/transcribe，後端用
 * Amazon Transcribe 轉成文字回傳。AWS 憑證全程留在後端，前端零 AWS 相依
 * （只用原生 fetch + MediaRecorder）。與下單相同的 X-Approval-Secret 守衛。
 */

async function approvalSecret(): Promise<string> {
  try {
    const res = await fetch('/api/config');
    if (!res.ok) return '';
    return ((await res.json()) as { approval_secret?: string }).approval_secret ?? '';
  } catch {
    return '';
  }
}

/** 把錄好的音檔送去後端轉文字。回傳辨識到的文字（可能為空字串）；失敗則 throw。 */
export async function transcribeAudio(blob: Blob, signal?: AbortSignal): Promise<string> {
  const secret = await approvalSecret();
  const res = await fetch('/api/transcribe', {
    method: 'POST',
    headers: { 'Content-Type': blob.type || 'audio/webm', 'X-Approval-Secret': secret },
    body: blob,
    signal: signal ?? null,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* 回應不是 JSON 就用狀態碼 */
    }
    throw new Error(detail);
  }
  return ((await res.json()) as { text?: string }).text ?? '';
}
