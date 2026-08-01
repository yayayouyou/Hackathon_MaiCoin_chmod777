/**
 * 極簡 Markdown → 安全 HTML。
 *
 * 為什麼手寫：frontend-pixel 附錄 B 規則 1 禁止新增執行期相依，不能引 marked/
 * markdown-it。agent 的回答只用到一個小子集（粗體/斜體/行內碼/圍欄碼/標題/清單/
 * 連結），手寫足夠，也少一條供應鏈風險。
 *
 * 安全模型（重點）：**先把文字整段 escape 成實體，再套用白名單式的轉換**。
 * 於是輸出裡出現的每一個標籤都由本檔產生，模型吐什麼 `<script>`、onerror= 都只會
 * 變成看得見的純文字。連結額外限制成 http/https，擋掉 javascript: / data:。
 * 正因如此，回傳字串可以安全地餵給 dangerouslySetInnerHTML。
 *
 * 只在 final_answer 進歷史時渲染（見 hud/blocks/AgentDock）；串流中的半截 markdown
 * （`**bo`）維持 raw，避免每個 delta 都重新 parse 又閃爍。
 */

const esc = (s: string): string =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** 行內轉換：先 escape，再處理 `code` → 連結 → 粗體 → 斜體。順序有意義。 */
function inline(text: string): string {
  let s = esc(text);
  // 行內碼最先，內部的 * _ [ ] 不再被當格式
  s = s.replace(/`([^`]+)`/g, (_m, c: string) => `<code>${c}</code>`);
  // 連結 [text](url) —— 只放行 http/https，並加 noopener
  s = s.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    (_m, t: string, u: string) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`,
  );
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  s = s.replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>');
  return s;
}

const BLOCK_START = /^```|^#{1,6}\s|^\s*[-*]\s|^\s*\d+\.\s/;

/** GFM 表格的分隔列，例如 | --- | :--: |。只由 | - : 與空白組成，且至少含一個 -。 */
const isTableSep = (s: string): boolean => /^[\s|:-]+$/.test(s) && s.includes('-') && s.includes('|');

/** 切一列表格的儲存格：去掉頭尾的 | 再以 | 分欄。 */
const tableCells = (row: string): string[] =>
  row.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map((c) => c.trim());

export function renderMarkdown(md: string): string {
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const out: string[] = [];
  let i = 0;
  let listType: 'ul' | 'ol' | null = null;
  const closeList = (): void => {
    if (listType) {
      out.push(`</${listType}>`);
      listType = null;
    }
  };

  while (i < lines.length) {
    const line = lines[i]!;

    // 圍欄碼 ``` ... ```
    if (/^```/.test(line)) {
      closeList();
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i]!)) {
        body.push(lines[i]!);
        i++;
      }
      i++; // 跳過結尾的 ```
      out.push(`<pre><code>${esc(body.join('\n'))}</code></pre>`);
      continue;
    }

    // 表格： | 表頭 | 表頭 | 後接分隔列 | --- | --- |。crypto 答案很常用。
    if (line.includes('|') && i + 1 < lines.length && isTableSep(lines[i + 1]!)) {
      closeList();
      const head = tableCells(line);
      i += 2; // 跳過表頭列與分隔列
      const rows: string[][] = [];
      while (i < lines.length && lines[i]!.includes('|') && lines[i]!.trim() !== '') {
        rows.push(tableCells(lines[i]!));
        i++;
      }
      const thead = `<thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead>`;
      const tbody = `<tbody>${rows
        .map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`)
        .join('')}</tbody>`;
      // 外層 wrap 負責水平捲動，長表格才不會撐爆 340px 的 dock
      out.push(`<div class="md-tablewrap"><table>${thead}${tbody}</table></div>`);
      continue;
    }

    // 標題 # ~ ###### → dock 內縮到 h3~h6，避免比訊息本身還大
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      closeList();
      const level = Math.min(6, h[1]!.length + 2);
      out.push(`<h${level}>${inline(h[2]!)}</h${level}>`);
      i++;
      continue;
    }

    // 無序清單 - 或 *
    const ul = line.match(/^\s*[-*]\s+(.*)$/);
    if (ul) {
      if (listType !== 'ul') {
        closeList();
        out.push('<ul>');
        listType = 'ul';
      }
      out.push(`<li>${inline(ul[1]!)}</li>`);
      i++;
      continue;
    }

    // 有序清單 1. 2. 3.
    const ol = line.match(/^\s*\d+\.\s+(.*)$/);
    if (ol) {
      if (listType !== 'ol') {
        closeList();
        out.push('<ol>');
        listType = 'ol';
      }
      out.push(`<li>${inline(ol[1]!)}</li>`);
      i++;
      continue;
    }

    // 空行 → 段落分界
    if (line.trim() === '') {
      closeList();
      i++;
      continue;
    }

    // 一般段落：連續非空、非區塊起始的行合併，行內換行以 <br> 呈現
    closeList();
    const para: string[] = [line];
    i++;
    while (i < lines.length && lines[i]!.trim() !== '' && !BLOCK_START.test(lines[i]!)) {
      para.push(lines[i]!);
      i++;
    }
    out.push(`<p>${para.map(inline).join('<br>')}</p>`);
  }

  closeList();
  return out.join('');
}
