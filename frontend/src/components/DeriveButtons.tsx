import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useDerive, useInvalidate, useJob } from "../api/hooks";
import type { ContentSummary } from "../api/types";
import { TYPE_LABELS } from "../api/types";
import StatusBadge from "./StatusBadge";

function DeriveButton({
  contentId,
  kind,
  label,
}: {
  contentId: number;
  kind: "reels" | "newsletter";
  label: string;
}) {
  const derive = useDerive(kind);
  const [jobId, setJobId] = useState<number | null>(null);
  const { data: job } = useJob(jobId);
  const invalidate = useInvalidate();

  const running =
    jobId !== null && job?.status !== "done" && job?.status !== "failed";

  useEffect(() => {
    if (job?.status === "done" && jobId !== null) {
      setJobId(null);
      invalidate();
    }
  }, [job, jobId, invalidate]);

  return (
    <div>
      <button
        onClick={async () => {
          const r = await derive.mutateAsync(contentId);
          setJobId(r.job_id);
        }}
        disabled={running || derive.isPending}
        className="rounded bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50"
      >
        {running ? "생성 중..." : label}
      </button>
      {job?.status === "failed" && (
        <p className="mt-1 text-xs text-red-600">{job.error}</p>
      )}
    </div>
  );
}

export default function DeriveButtons({
  contentId,
  children,
}: {
  contentId: number;
  children: ContentSummary[];
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-2 text-sm font-bold text-gray-700">멀티채널 파생</h3>
      <div className="flex gap-2">
        <DeriveButton contentId={contentId} kind="reels" label="릴스 변환" />
        <DeriveButton
          contentId={contentId}
          kind="newsletter"
          label="뉴스레터 생성"
        />
      </div>
      {children.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-t border-gray-100 pt-3">
          {children.map((c) => (
            <li key={c.id} className="flex items-center gap-2 text-xs">
              <span className="rounded bg-gray-800 px-1.5 py-0.5 text-white">
                {TYPE_LABELS[c.type]}
              </span>
              <Link
                to={`/contents/${c.id}`}
                className="truncate text-blue-600 hover:underline"
              >
                {c.title}
              </Link>
              <StatusBadge status={c.status} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
