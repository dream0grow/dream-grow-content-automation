import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  useContent,
  useDeleteContent,
  useInvalidate,
  useJob,
  usePublishNow,
  useReviewFix,
  useRunReview,
  useSchedule,
  useStatusChange,
  useUpdateContent,
} from "../api/hooks";
import { CATEGORIES, TYPE_LABELS } from "../api/types";
import DeriveButtons from "../components/DeriveButtons";
import ReviewChecklist from "../components/ReviewChecklist";
import StatusBadge from "../components/StatusBadge";
import ThreadPostPreview from "../components/ThreadPostPreview";
import { formatDateTime } from "../lib/dates";

export default function EditorPage() {
  const { id } = useParams();
  const contentId = Number(id);
  const navigate = useNavigate();
  const { data: content, isLoading } = useContent(contentId);

  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [category, setCategory] = useState("학습");
  const [dirty, setDirty] = useState(false);
  const [actionError, setActionError] = useState("");
  const [publishJobId, setPublishJobId] = useState<number | null>(null);
  const [scheduleInput, setScheduleInput] = useState("");

  const update = useUpdateContent(contentId);
  const statusChange = useStatusChange(contentId);
  const runReview = useRunReview(contentId);
  const reviewFix = useReviewFix(contentId);
  const schedule = useSchedule(contentId);
  const publishNow = usePublishNow(contentId);
  const deleteContent = useDeleteContent();
  const invalidate = useInvalidate();
  const { data: publishJob } = useJob(publishJobId);

  useEffect(() => {
    if (content && !dirty) {
      setTitle(content.title);
      setBody(content.body);
      setCategory(content.category);
    }
  }, [content, dirty]);

  useEffect(() => {
    if (publishJob?.status === "done" || publishJob?.status === "failed") {
      setPublishJobId(null);
      invalidate();
      if (publishJob.status === "failed") {
        setActionError(publishJob.error ?? "발행 실패");
      }
    }
  }, [publishJob, invalidate]);

  if (isLoading || !content) {
    return <p className="text-sm text-gray-500">불러오는 중...</p>;
  }

  const editable = content.status === "리뷰대기" || content.status === "리뷰완료";
  const publishing = publishJobId !== null;

  const act = async (fn: () => Promise<unknown>) => {
    setActionError("");
    try {
      await fn();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };

  const save = () =>
    act(async () => {
      await update.mutateAsync({ title, body, category });
      setDirty(false);
    });

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <Link to="/" className="text-sm text-gray-500 hover:text-gray-900">
          ← 대시보드
        </Link>
        <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-white">
          {TYPE_LABELS[content.type]}
        </span>
        <StatusBadge status={content.status} />
        {content.scheduled_at && (
          <span className="text-xs text-gray-500">
            예약: {formatDateTime(content.scheduled_at)}
          </span>
        )}
        {content.external_id && (
          <span className="text-xs text-gray-500">
            Threads ID: {content.external_id}
          </span>
        )}
        {content.parent_content_id && (
          <Link
            to={`/contents/${content.parent_content_id}`}
            className="text-xs text-blue-600 hover:underline"
          >
            원본 스레드 보기
          </Link>
        )}
      </div>

      {actionError && (
        <p className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {actionError}
        </p>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* 좌측: 편집 */}
        <div className="space-y-3">
          <div className="flex gap-2">
            <input
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                setDirty(true);
              }}
              disabled={!editable}
              className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium disabled:bg-gray-100"
            />
            <select
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setDirty(true);
              }}
              disabled={!editable}
              className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm disabled:bg-gray-100"
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <textarea
            value={body}
            onChange={(e) => {
              setBody(e.target.value);
              setDirty(true);
            }}
            disabled={!editable}
            rows={24}
            className="w-full rounded-lg border border-gray-300 bg-white p-3 font-mono text-sm leading-relaxed disabled:bg-gray-100"
            placeholder={'각 글은 "---"로 구분합니다'}
          />
          <div className="flex items-center gap-2">
            <button
              onClick={save}
              disabled={!dirty || !editable || update.isPending}
              className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-40"
            >
              {update.isPending ? "저장 중..." : "저장"}
            </button>
            {dirty && (
              <span className="text-xs text-amber-600">
                저장되지 않은 변경사항이 있습니다
              </span>
            )}
          </div>
        </div>

        {/* 우측: 미리보기 + 액션 */}
        <div className="space-y-4">
          {content.type === "thread" ? (
            <ThreadPostPreview body={body} />
          ) : (
            <div className="rounded-lg border border-gray-200 bg-white p-3">
              <p className="mb-1 text-xs text-gray-500">
                총 {body.replace(/\s+/g, "").length}자
                {content.type === "newsletter" && " (목표 6000~7000자)"}
              </p>
              <p className="line-clamp-6 whitespace-pre-wrap text-sm text-gray-700">
                {body}
              </p>
            </div>
          )}

          <ReviewChecklist
            review={content.review_result}
            onRunReview={() => act(() => runReview.mutateAsync())}
            onFix={() =>
              act(async () => {
                await reviewFix.mutateAsync();
                setDirty(false);
              })
            }
            reviewing={runReview.isPending}
            fixing={reviewFix.isPending}
          />

          {/* 상태 액션 */}
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="mb-2 text-sm font-bold text-gray-700">상태 관리</h3>
            <div className="flex flex-wrap gap-2">
              {content.status === "리뷰대기" && (
                <button
                  onClick={() =>
                    act(() => statusChange.mutateAsync({ status: "리뷰완료" }))
                  }
                  className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500"
                >
                  리뷰완료 처리
                </button>
              )}
              {(content.status === "리뷰완료" ||
                content.status === "발행대기") && (
                <>
                  <button
                    onClick={() =>
                      act(() =>
                        statusChange.mutateAsync({ status: "리뷰대기" }),
                      )
                    }
                    className="rounded bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-200"
                  >
                    리뷰대기로 되돌리기
                  </button>
                  <button
                    onClick={() => act(async () => {
                      const r = await publishNow.mutateAsync();
                      setPublishJobId(r.job_id);
                    })}
                    disabled={publishing}
                    className="rounded bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-500 disabled:opacity-50"
                  >
                    {publishing ? "발행 중..." : "지금 발행"}
                  </button>
                </>
              )}
              {content.status === "실패" && (
                <button
                  onClick={() => act(async () => {
                    const r = await publishNow.mutateAsync();
                    setPublishJobId(r.job_id);
                  })}
                  disabled={publishing}
                  className="rounded bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-500 disabled:opacity-50"
                >
                  {publishing ? "발행 중..." : "재발행 시도"}
                </button>
              )}
              {content.status !== "발행완료" && (
                <button
                  onClick={() =>
                    act(async () => {
                      if (!confirm("이 콘텐츠를 삭제할까요?")) return;
                      await deleteContent.mutateAsync(contentId);
                      navigate("/");
                    })
                  }
                  className="rounded bg-red-50 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-100"
                >
                  삭제
                </button>
              )}
            </div>

            {/* 예약 설정 */}
            {(content.status === "리뷰완료" ||
              content.status === "발행대기") && (
              <div className="mt-3 flex items-center gap-2 border-t border-gray-100 pt-3">
                <input
                  type="datetime-local"
                  value={scheduleInput}
                  onChange={(e) => setScheduleInput(e.target.value)}
                  className="rounded border border-gray-300 px-2 py-1 text-xs"
                />
                <button
                  onClick={() =>
                    act(() => schedule.mutateAsync(scheduleInput))
                  }
                  disabled={!scheduleInput}
                  className="rounded bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-500 disabled:opacity-40"
                >
                  발행 예약
                </button>
                {content.scheduled_at && (
                  <button
                    onClick={() => act(() => schedule.mutateAsync(null))}
                    className="rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-200"
                  >
                    예약 해제
                  </button>
                )}
              </div>
            )}
          </div>

          {content.type === "thread" && (
            <DeriveButtons contentId={contentId} children={content.children} />
          )}
        </div>
      </div>
    </div>
  );
}
