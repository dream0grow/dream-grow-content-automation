export type Channel = "thread" | "reels" | "youtube" | "newsletter" | "magnet";
export type ContentStatus =
  | "draft" | "reviewing" | "scheduled" | "published" | "failed";

export type ContentSummary = {
  id: string;
  channel: Channel;
  category: string | null;
  topic: string;
  status: ContentStatus;
  created_at: string;
  updated_at: string;
};

export type Content = ContentSummary & {
  body_md: string;
  ai_original_md: string | null;
  frontmatter: Record<string, unknown>;
  generated_by_model: string | null;
};

export type Issue = {
  severity: "INFO" | "WARN" | "ERROR";
  category: string;
  message: string;
  line: number;
};

export type ReviewResponse = { passed: boolean; issues: Issue[] };

export type Job = {
  id: string;
  type: string;
  status: "queued" | "running" | "done" | "failed";
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ScheduleItem = {
  id: string;
  content_id: string;
  scheduled_at: string;
  timezone: string;
  status: "pending" | "firing" | "done" | "failed" | "cancelled";
  channel: Channel;
  topic: string;
};

export type BrandProfile = {
  id?: string;
  brand_name: string;
  target_audience: string | null;
  tone_notes: string | null;
  banned_phrases: string[];
  required_ending: string | null;
  brand_signature: string | null;
  categories: string[];
};

export type AnalyticsSummary = {
  period: string;
  total_content: number;
  total_published: number;
  total_views: number;
  total_likes: number;
  total_comments: number;
  top_by_views: { id: string; topic: string; channel: string; views: number }[];
};

export type Integration = {
  provider: string;
  status: string;
  connected: boolean;
  meta: Record<string, unknown>;
};
