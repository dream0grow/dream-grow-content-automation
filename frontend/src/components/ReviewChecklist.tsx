import type { ReviewResult } from "../api/types";

const SEVERITY_STYLES: Record<string, string> = {
  ERROR: "bg-red-100 text-red-700",
  WARN: "bg-amber-100 text-amber-700",
  INFO: "bg-gray-100 text-gray-600",
};

export default function ReviewChecklist({
  review,
  onRunReview,
  onFix,
  fixing,
  reviewing,
}: {
  review: ReviewResult | null;
  onRunReview: () => void;
  onFix: () => void;
  fixing: boolean;
  reviewing: boolean;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-bold text-gray-700">검수</h3>
        <div className="flex gap-2">
          <button
            onClick={onRunReview}
            disabled={reviewing}
            className="rounded bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50"
          >
            {reviewing ? "검수 중..." : "검수 실행"}
          </button>
          {review?.auto_fixable && (
            <button
              onClick={onFix}
              disabled={fixing}
              className="rounded bg-blue-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {fixing ? "수정 중..." : "자동 수정"}
            </button>
          )}
        </div>
      </div>

      {review === null ? (
        <p className="text-xs text-gray-400">아직 검수하지 않았습니다.</p>
      ) : review.issues.length === 0 ? (
        <p className="text-xs font-medium text-green-600">
          모든 검수 항목을 통과했습니다.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {review.issues.map((issue, i) => (
            <li key={i} className="flex items-start gap-2 text-xs">
              <span
                className={`shrink-0 rounded px-1.5 py-0.5 font-medium ${SEVERITY_STYLES[issue.severity]}`}
              >
                {issue.severity}
              </span>
              <span className="text-gray-700">
                [{issue.category}] {issue.message}
              </span>
            </li>
          ))}
        </ul>
      )}
      {review && !review.passed && (
        <p className="mt-2 text-xs text-red-600">
          ERROR 이슈가 있으면 리뷰완료 처리가 차단됩니다.
        </p>
      )}
    </div>
  );
}
