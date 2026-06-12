export type ContentType = "thread" | "reels" | "newsletter";
export type ContentStatus = "리뷰대기" | "리뷰완료" | "발행대기" | "발행완료" | "실패";
export type JobStatus = "pending" | "running" | "done" | "failed";

export interface ReviewIssue {
  severity: "ERROR" | "WARN" | "INFO";
  category: string;
  message: string;
  post_index?: number | null;
}

export interface ReviewResult {
  passed: boolean;
  issues: ReviewIssue[];
  auto_fixable: boolean;
}

export interface ContentSummary {
  id: number;
  type: ContentType;
  title: string;
  category: string;
  status: ContentStatus;
  scheduled_at: string | null;
  published_at: string | null;
  parent_content_id: number | null;
  review_result: ReviewResult | null;
  created_at: string;
  updated_at: string;
}

export interface PostPreview {
  text: string;
  length: number;
  over_limit: boolean;
  over_style: boolean;
}

export interface ContentDetail extends ContentSummary {
  body: string;
  tone: string | null;
  external_id: string | null;
  external_ids: { id: string }[] | null;
  posts: PostPreview[];
  children: ContentSummary[];
}

export interface ContentList {
  items: ContentSummary[];
  total: number;
}

export interface Job {
  id: number;
  kind: string;
  status: JobStatus;
  content_id: number | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface CalendarItem {
  content_id: number;
  time: string;
  title: string;
  category: string;
  type: ContentType;
  status: ContentStatus;
}

export interface CalendarDay {
  date: string;
  items: CalendarItem[];
}

export interface AutoScheduleItem {
  content_id: number;
  title: string;
  category: string;
  scheduled_at: string;
}

export interface PublishLog {
  id: number;
  content_id: number;
  success: boolean;
  dry_run: boolean;
  posts_count: number;
  external_ids: { id: string }[] | null;
  error: string | null;
  created_at: string;
}

export interface SystemStatus {
  scheduler_running: boolean;
  next_run_at: string | null;
  threads_configured: boolean;
  llm_configured: boolean;
  mock_llm: boolean;
  dry_run: boolean;
  db: string;
}

export const CATEGORIES = [
  "훈육", "수학", "독서", "미디어", "놀이", "감정", "학습", "학교", "크리에이터",
] as const;

export const STATUS_ORDER: ContentStatus[] = ["리뷰대기", "리뷰완료", "발행대기", "발행완료"];

export const TYPE_LABELS: Record<ContentType, string> = {
  thread: "스레드",
  reels: "릴스",
  newsletter: "뉴스레터",
};
