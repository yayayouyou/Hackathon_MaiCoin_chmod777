/**
 * 分析取向（規格 §5.3）。**這一輪只有型別。**
 *
 * 刻意叫「分析取向」不叫「投資人格」：對做合規／信託／ISO 27001 的公司，
 * 後者在形式上接近受規範的投資屬性／適合度評估（§2）。
 *
 * 前端送給後端的永遠只有這三個 enum，不送 prompt 文字（prompt injection）。
 * 後端收到未知值一律當作沒有。
 *
 * C 軌落地時在這裡補 `STANCES`（name / hint / accent / recolor）與
 * `BootScreen`，UI 上必須有一行小字：
 * 「這只是分析呈現偏好，不構成投資屬性評估，也不構成投資建議。」
 */
export type StanceId = 'risk' | 'discipline' | 'opportunity';

/** 逃生口（Ctrl+Shift+Enter / ?fast=1）與尚未選擇時都用這個。 */
export const DEFAULT_STANCE: StanceId = 'discipline';
