import type { ContentStatus } from "../api/types";

const STYLES: Record<ContentStatus, string> = {
  리뷰대기: "bg-yellow-100 text-yellow-800",
  리뷰완료: "bg-blue-100 text-blue-800",
  발행대기: "bg-purple-100 text-purple-800",
  발행완료: "bg-green-100 text-green-800",
  실패: "bg-red-100 text-red-800",
};

export default function StatusBadge({ status }: { status: ContentStatus }) {
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${STYLES[status] ?? "bg-gray-100 text-gray-700"}`}
    >
      {status}
    </span>
  );
}
