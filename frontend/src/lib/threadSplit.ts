// 백엔드 app/services/splitter.py와 동일한 분할 로직 (라이브 글자 수 표시용)
const PREFIX_RE = /^\[?\d+\/\d*\]?\s*/;

export const THREADS_HARD_LIMIT = 500;
export const THREADS_STYLE_LIMIT = 280;

export function splitPosts(body: string): string[] {
  const trimmed = body.trim();
  if (!trimmed) return [];
  const parts = trimmed.includes("\n---\n") || trimmed.startsWith("---\n")
    ? trimmed.split(/\n---\n|^---\n/)
    : [trimmed];
  return parts
    .map((p) => p.trim().replace(PREFIX_RE, ""))
    .filter((p) => p.length > 0);
}
