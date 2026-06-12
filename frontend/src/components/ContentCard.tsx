import { Link } from "react-router-dom";
import type { ContentSummary } from "../api/types";
import { TYPE_LABELS } from "../api/types";
import { formatDateTime } from "../lib/dates";

export default function ContentCard({ content }: { content: ContentSummary }) {
  const review = content.review_result;
  return (
    <Link
      to={`/contents/${content.id}`}
      className="block rounded-lg border border-gray-200 bg-white p-3 shadow-sm transition hover:border-gray-400"
    >
      <div className="mb-1.5 flex items-center gap-1.5">
        <span className="rounded bg-gray-800 px-1.5 py-0.5 text-xs text-white">
          {TYPE_LABELS[content.type]}
        </span>
        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
          {content.category}
        </span>
        {review && (
          <span
            title={review.passed ? "검수 통과" : "검수 이슈 있음"}
            className={`ml-auto inline-block h-2 w-2 rounded-full ${review.passed ? "bg-green-500" : "bg-red-500"}`}
          />
        )}
      </div>
      <p className="line-clamp-2 text-sm font-medium text-gray-900">
        {content.title}
      </p>
      {content.scheduled_at && (
        <p className="mt-1 text-xs text-gray-500">
          예약: {formatDateTime(content.scheduled_at)}
        </p>
      )}
      {content.published_at && (
        <p className="mt-1 text-xs text-gray-500">
          발행: {formatDateTime(content.published_at)}
        </p>
      )}
    </Link>
  );
}
