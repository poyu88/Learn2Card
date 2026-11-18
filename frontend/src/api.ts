import { Deck } from "./types";

export const API_BASE_URL = "http://127.0.0.1:8000";
export const PROCESS_ENDPOINT = `${API_BASE_URL}/api/process`;
export const DECK_JSON_PATH = "/deck.json";

export const DEFAULT_TOPIC_THRESHOLD = 0.75;
export const DEFAULT_MAX_TOPICS = 5;
export const DEFAULT_MAX_BULLETS = 5;
export const DEFAULT_DEBUG = false;

export const REQUEST_TIMEOUT_MS = 120_000;

export interface ProcessParams {
  text: string;
  topic_threshold: number;
  max_topics: number;
  max_bullets: number;
  debug: boolean;
}

export interface ProcessSuccessResponse {
  message?: string;
  stats?: Deck["stats"];
  deck?: Deck;
  cardCount?: number;
}

export type LoadDeckResult =
  | { ok: true; deck: Deck }
  | { ok: false; error: string };

export type ProcessResult =
  | { ok: true; message: string; deck?: Deck }
  | { ok: false; error: string; canRetry: boolean };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function validateDeck(data: unknown): data is Deck {
  if (!isRecord(data)) return false;
  if (!Array.isArray(data.paragraphs) || !Array.isArray(data.topics) || !Array.isArray(data.cards)) {
    return false;
  }
  if (!isRecord(data.stats)) return false;

  const { paragraphCount, topicCount, cardCount } = data.stats;
  if (
    typeof paragraphCount !== "number" ||
    typeof topicCount !== "number" ||
    typeof cardCount !== "number"
  ) {
    return false;
  }

  for (const paragraph of data.paragraphs) {
    if (!isRecord(paragraph)) return false;
    if (
      typeof paragraph.id !== "string" ||
      typeof paragraph.text !== "string" ||
      typeof paragraph.summary !== "string" ||
      !isStringArray(paragraph.keywords) ||
      typeof paragraph.sourceIndex !== "number"
    ) {
      return false;
    }
  }

  for (const topic of data.topics) {
    if (!isRecord(topic)) return false;
    if (
      typeof topic.id !== "string" ||
      typeof topic.title !== "string" ||
      !isStringArray(topic.memberIds)
    ) {
      return false;
    }
  }

  for (const card of data.cards) {
    if (!isRecord(card)) return false;
    if (
      typeof card.id !== "string" ||
      typeof card.topicId !== "string" ||
      typeof card.title !== "string" ||
      !isStringArray(card.bullets)
    ) {
      return false;
    }
  }

  return true;
}

export async function loadDeckFromPublic(): Promise<LoadDeckResult> {
  try {
    const response = await fetch(DECK_JSON_PATH);
    if (!response.ok) {
      return {
        ok: false,
        error: `無法載入卡片資料（HTTP ${response.status}）。請確認 public/deck.json 存在。`,
      };
    }

    let data: unknown;
    try {
      data = await response.json();
    } catch {
      return {
        ok: false,
        error: "卡片資料 JSON 解析失敗，請確認 deck.json 格式正確。",
      };
    }

    if (!validateDeck(data)) {
      return {
        ok: false,
        error: "卡片資料格式不符合預期 schema（需包含 paragraphs、topics、cards、stats）。",
      };
    }

    return { ok: true, deck: data };
  } catch {
    return {
      ok: false,
      error: "載入卡片資料失敗，請檢查網路狀態或重新整理頁面。",
    };
  }
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) return fallback;
  // Prefer user-facing `message` over raw `detail` (Backend 500 puts exception text in detail).
  if (typeof payload.message === "string" && payload.message.trim()) {
    return payload.message;
  }
  if (typeof payload.error === "string" && payload.error.trim()) {
    return payload.error;
  }
  if (typeof payload.detail === "string" && payload.detail.trim()) {
    return payload.detail;
  }
  if (Array.isArray(payload.detail)) {
    const parts = payload.detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (isRecord(item) && typeof item.msg === "string") return item.msg;
        return null;
      })
      .filter((item): item is string => Boolean(item));
    if (parts.length > 0) return parts.join("；");
  }
  return fallback;
}

export async function processText(params: ProcessParams): Promise<ProcessResult> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(PROCESS_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(params),
      signal: controller.signal,
    });

    let payload: unknown = null;
    const rawText = await response.text();
    if (rawText) {
      try {
        payload = JSON.parse(rawText);
      } catch {
        payload = null;
      }
    }

    if (!response.ok) {
      if (response.status >= 500) {
        return {
          ok: false,
          error: extractErrorMessage(payload, `Backend 處理失敗（HTTP ${response.status}）`),
          canRetry: true,
        };
      }
      return {
        ok: false,
        error: extractErrorMessage(payload, `請求失敗（HTTP ${response.status}）`),
        canRetry: response.status >= 500,
      };
    }

    const deck =
      isRecord(payload) && validateDeck(payload.deck)
        ? (payload.deck as Deck)
        : isRecord(payload) && validateDeck(payload)
          ? (payload as Deck)
          : undefined;

    const stats =
      isRecord(payload) && isRecord(payload.stats)
        ? (payload.stats as unknown as Deck["stats"])
        : deck?.stats;

    const cardCount =
      typeof stats?.cardCount === "number"
        ? stats.cardCount
        : typeof (payload as { cardCount?: number } | null)?.cardCount === "number"
          ? (payload as { cardCount: number }).cardCount
          : deck?.cards.length;

    const message =
      (isRecord(payload) && typeof payload.message === "string" && payload.message) ||
      (typeof cardCount === "number"
        ? `已成功產生 ${cardCount} 張卡片`
        : "已成功產生卡片");

    return { ok: true, message, deck };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return {
        ok: false,
        error: "網路逾時：Backend 處理時間過長，請稍後重試。",
        canRetry: true,
      };
    }

    const message = error instanceof Error ? error.message : "";
    if (
      message.includes("Failed to fetch") ||
      message.includes("NetworkError") ||
      message.includes("fetch")
    ) {
      return {
        ok: false,
        error: "無法連接到 Backend，請確認 Backend 服務已啟動",
        canRetry: true,
      };
    }

    return {
      ok: false,
      error: "網路連接失敗，請檢查網路狀態",
      canRetry: true,
    };
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export function clampTopicThreshold(value: number): number {
  if (Number.isNaN(value)) return DEFAULT_TOPIC_THRESHOLD;
  return Math.min(1, Math.max(0, value));
}

export function clampMaxTopics(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_MAX_TOPICS;
  return Math.min(10, Math.max(1, Math.round(value)));
}

export function clampMaxBullets(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_MAX_BULLETS;
  return Math.min(5, Math.max(1, Math.round(value)));
}

export function isAllowedTextFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return name.endsWith(".txt") || name.endsWith(".md");
}

export function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(typeof reader.result === "string" ? reader.result : "");
    };
    reader.onerror = () => {
      reject(new Error("讀取檔案失敗，請再試一次。"));
    };
    reader.readAsText(file, "UTF-8");
  });
}
