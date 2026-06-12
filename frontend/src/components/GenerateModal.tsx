import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useGenerateThread, useInvalidate, useJob } from "../api/hooks";
import { CATEGORIES } from "../api/types";

export default function GenerateModal({ onClose }: { onClose: () => void }) {
  const [topic, setTopic] = useState("");
  const [category, setCategory] = useState<string>("학습");
  const [tone, setTone] = useState("전문적이면서 친근한");
  const [jobId, setJobId] = useState<number | null>(null);

  const generate = useGenerateThread();
  const { data: job } = useJob(jobId);
  const navigate = useNavigate();
  const invalidate = useInvalidate();

  useEffect(() => {
    if (job?.status === "done" && job.content_id) {
      invalidate();
      navigate(`/contents/${job.content_id}`);
    }
  }, [job, invalidate, navigate]);

  const submit = async () => {
    if (!topic.trim()) return;
    const result = await generate.mutateAsync({ topic, tone, category });
    setJobId(result.job_id);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-bold">새 스레드 생성</h2>

        {jobId === null ? (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                주제
              </label>
              <input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="예: 초등 수학 분수 개념"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
                autoFocus
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                카테고리
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                톤
              </label>
              <input
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={onClose}
                className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
              >
                취소
              </button>
              <button
                onClick={submit}
                disabled={!topic.trim() || generate.isPending}
                className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
              >
                생성 시작
              </button>
            </div>
            {generate.isError && (
              <p className="text-sm text-red-600">{generate.error.message}</p>
            )}
          </div>
        ) : (
          <div className="py-6 text-center">
            {job?.status === "failed" ? (
              <>
                <p className="mb-2 text-sm font-medium text-red-600">
                  생성 실패
                </p>
                <p className="mb-4 text-xs text-gray-500">{job.error}</p>
                <button
                  onClick={() => setJobId(null)}
                  className="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white"
                >
                  다시 시도
                </button>
              </>
            ) : (
              <>
                <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-gray-900" />
                <p className="text-sm text-gray-600">
                  AI가 스레드를 작성하고 있습니다...
                </p>
                <p className="mt-1 text-xs text-gray-400">
                  {job?.status === "running" ? "생성 중" : "대기 중"}
                </p>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
