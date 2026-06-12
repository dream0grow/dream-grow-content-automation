import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const CHANNEL_LABEL: Record<string, string> = {
  thread: "스레드",
  reels: "릴스",
  youtube: "유튜브",
  newsletter: "뉴스레터",
  magnet: "리드마그넷",
};

export const STATUS_LABEL: Record<string, string> = {
  draft: "초안",
  reviewing: "리뷰중",
  scheduled: "예약됨",
  published: "발행완료",
  failed: "실패",
};

export const STATUS_BADGE_CLASS: Record<string, string> = {
  draft: "badge-draft",
  reviewing: "badge-reviewing",
  scheduled: "badge-scheduled",
  published: "badge-published",
  failed: "badge-failed",
};
