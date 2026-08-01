import { FLAGS } from '../game/core';
import { getCreds } from '../state';
import * as mock from './mock';
import type {
  Balance,
  EventItem,
  Market,
  NewsItem,
  OrderReq,
  OrderResult,
  Post,
  Quote,
  Report,
  RoomInfo,
  Strategy,
} from './types';

/**
 * 可被 AbortSignal 打斷的延遲。沒傳 signal 時就是原本那一行 setTimeout。
 *
 * 有它，`engine/zone.ts` 的 `ZoneRuntime.signal`（「輪詢與 fetch 都要吃它，
 * 否則離開房間還在打 API」）才是一條做得到的契約 —— 在此之前 api 這一層
 * 沒有任何函式收 signal，唯一的參考實作也只能靠 `ifStillHere` 擋結果，
 * 於是每條軌都會各自發明一套。
 */
function delay(ms: number, signal?: AbortSignal): Promise<void> {
  if (!signal) return new Promise((r) => setTimeout(r, ms));
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason ?? new Error('已取消'));
      return;
    }
    const onAbort = (): void => {
      clearTimeout(timer);
      reject(signal.reason ?? new Error('已取消'));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

/**
 * 唯一的後端邊界。目前全部回假資料，但介面已經是 async 的。
 *
 * 兩個刻意加進來的東西：
 * - 每次呼叫延遲 120–300ms，逼每個面板從第一天就有真的 loading 狀態，
 *   而不是接後端時才發現整輪 UI 都要補
 * - ?failApi=1 讓所有呼叫失敗，逼 error 狀態被實際走過一遍
 *
 * 換成真後端時，把這裡的 settle() 換成 fetch()（`signal` 直接轉給它），
 * 其他檔案一行都不用改。
 */
async function settle<T>(
  produce: () => T,
  ms = 120 + Math.random() * 180,
  signal?: AbortSignal,
): Promise<T> {
  await delay(ms, signal);
  if (FLAGS.failApi) throw new Error('連線失敗，請稍後再試');
  return produce();
}

/** 需要金鑰的端點統一走這裡，未連接時的錯誤訊息才會一致。 */
async function authed<T>(produce: () => T, ms?: number): Promise<T> {
  if (!getCreds()) throw new Error('尚未連接 API');
  return settle(produce, ms);
}

type BridgePost = { id: string; author: string; text: string; source: 'platform' | 'threads'; source_author?: string; created_at?: string; permalink?: string | null; parent_post_id?: string | null };
const bridgeHeaders = (): HeadersInit => ({ 'Content-Type': 'application/json' });
async function throwBridgeError(response: Response, fallback: string): Promise<never> {
  const body = await response.json().catch(() => ({})) as { detail?: string };
  throw new Error(body.detail ?? fallback);
}
function asBridgePost(post: BridgePost): Post {
  return { id: post.id, author: post.author, color: post.source === 'threads' ? '#8b5cf6' : '#35b8cf', time: post.created_at ? new Date(post.created_at).toLocaleString() : 'now', text: post.text, likes: 0, self: post.source === 'platform', source: post.source, sourceAuthor: post.source_author, permalink: post.permalink, parentPostId: post.parent_post_id };
}

export function getRooms(): Promise<RoomInfo[]> {
  return fetch('/api/discussion-spaces').then(async (response) => {
    if (!response.ok) throw new Error('Discussion spaces API unavailable');
    const data = await response.json() as { spaces: Array<{ id: string; title: string; created_at: string }> };
    return data.spaces.map((space, index) => ({
      id: space.id, topic: space.title, tag: 'Threads', accent: 'cyan' as const,
      heat: data.spaces.length - index, online: 1, change: 0, sentiment: 0,
    }));
  });
}

export async function createDiscussionSpace(title: string, openingText: string): Promise<void> {
  const response = await fetch('/api/discussion-spaces', { method: 'POST', credentials: 'same-origin', headers: bridgeHeaders(), body: JSON.stringify({ title, opening_text: openingText }) });
  if (!response.ok) await throwBridgeError(response, '建立討論區失敗');
}

export async function archiveDiscussionSpace(roomId: string): Promise<void> {
  const response = await fetch(`/api/discussion-spaces/${encodeURIComponent(roomId)}`, { method: 'DELETE', credentials: 'same-origin', headers: bridgeHeaders() });
  if (!response.ok) await throwBridgeError(response, '封存討論區失敗');
}

/** 策略牆。公開資料，不需要金鑰。 */
export function getStrategies(): Promise<Strategy[]> {
  return settle(() => [...mock.STRATEGIES]);
}

export function getReport(roomId: string): Promise<Report> {
  return settle(() => mock.reportFor(roomId), 240 + Math.random() * 260);
}

/** zone 的 onEnter 要傳 `rt.signal`，換場時在途的請求才會真的被放棄。 */
export function getThread(roomId: string, signal?: AbortSignal): Promise<Post[]> {
  return fetch(`/api/discussions/${encodeURIComponent(roomId)}`, { signal }).then(async (response) => {
    if (!response.ok) throw new Error('Discussion API unavailable');
    return ((await response.json()) as { posts: BridgePost[] }).posts.map(asBridgePost);
  });
}

export function postMessage(roomId: string, text: string, parentPostId?: string): Promise<Post> {
  return (async () => {
    const response = await fetch(`/api/discussions/${encodeURIComponent(roomId)}`, { method: 'POST', credentials: 'same-origin', headers: bridgeHeaders(), body: JSON.stringify({ text, parent_post_id: parentPostId ?? null }) });
    if (!response.ok) await throwBridgeError(response, '留言發佈失敗');
    return asBridgePost(((await response.json()) as { post: BridgePost }).post);
  })();
  return settle(() => ({
    id: `${roomId}-self-${Date.now()}`,
    author: '',
    color: '#35b8cf',
    time: '剛剛',
    text,
    likes: 0,
    self: true,
  }));
}

/** 行情是公開資料，不需要金鑰。面板每 3 秒輪詢一次。 */
export type ThreadSyncResult = { mentions: number; replies: number; mention_errors: number; reply_errors: number };
export async function syncThread(roomId: string): Promise<ThreadSyncResult> {
  const response = await fetch(`/api/discussions/${encodeURIComponent(roomId)}/sync`, {
    method: 'POST', credentials: 'same-origin', headers: bridgeHeaders(),
  });
  if (!response.ok) await throwBridgeError(response, '同步 Threads 失敗');
  const data = await response.json() as { imported: ThreadSyncResult };
  return data.imported;
}

export type DiscussionSpace = {
  id: string; title: string; creator: string; created_at: string; archived: boolean;
  threads_root_id?: string; threads_deleted_at?: string;
  source_threads_id?: string; source_permalink?: string;
};
export async function listDiscussionSpaces(includeArchived = false): Promise<DiscussionSpace[]> {
  const response = await fetch(`/api/discussion-spaces?include_archived=${includeArchived}`);
  if (!response.ok) throw new Error('Unable to load discussion spaces');
  return ((await response.json()) as { spaces: DiscussionSpace[] }).spaces;
}
export async function deleteOfficialThreadsRoot(roomId: string): Promise<void> {
  const response = await fetch(`/api/admin/discussion-spaces/${encodeURIComponent(roomId)}/delete-threads-root`, {
    method: 'POST', credentials: 'same-origin', headers: bridgeHeaders(), body: JSON.stringify({ confirmation: 'DELETE' }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail ?? 'Unable to delete official Threads post');
  }
}
export async function syncThreadsMentions(): Promise<{ created: number; errors: number; busy: boolean }> {
  const response = await fetch('/api/threads/sync-mentions', { method: 'POST', credentials: 'same-origin', headers: bridgeHeaders() });
  if (!response.ok) await throwBridgeError(response, '同步 @MAIA 話題失敗');
  const data = await response.json() as { created: number; errors: number; busy?: number };
  return { created: data.created, errors: data.errors, busy: data.busy === 1 };
}

export function getMarkets(quote: Quote): Promise<Market[]> {
  return settle(
    () => mock.driftMarkets().filter((m) => m.quote === quote).sort((a, b) => b.volume - a.volume),
    80 + Math.random() * 90,
  );
}

export function getBalances(): Promise<Balance[]> {
  return authed(() =>
    mock.BALANCE_SEEDS.map((b) => ({ ...b, price: mock.priceOf(b.asset) })),
  );
}

export function placeOrder(o: OrderReq): Promise<OrderResult> {
  return authed(
    () => ({
      id: `mock-${Date.now().toString(36)}`,
      state: o.type === 'market' ? 'done' : 'wait',
      message:
        o.type === 'market'
          ? `已市價${o.side === 'buy' ? '買入' : '賣出'} ${o.volume}`
          : `限價單已掛出，等待成交`,
    }),
    300,
  );
}

export function getNews(): Promise<NewsItem[]> {
  return settle(() => mock.NEWS);
}

export function getEvents(): Promise<EventItem[]> {
  return settle(() => mock.EVENTS);
}

/**
 * 客服機器人。目前是關鍵字比對，未來接真的 bot 時只要把這一個
 * 函式的內容換成 fetch，對話面板完全不用動。
 */
export function askBot(text: string): Promise<string> {
  return settle(() => mock.botReply(text), 400 + Math.random() * 400);
}

export const BOT_GREETING = mock.BOT_GREETING;
export type * from './types';
