import { useState } from "react";
import { useActiveJobs, useContents } from "../api/hooks";
import { CATEGORIES, STATUS_ORDER, TYPE_LABELS } from "../api/types";
import type { ContentStatus } from "../api/types";
import ContentCard from "../components/ContentCard";
import GenerateModal from "../components/GenerateModal";

export default function DashboardPage() {
  const [typeFilter, setTypeFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [search, setSearch] = useState("");
  const [showGenerate, setShowGenerate] = useState(false);

  const { data, isLoading, isError, error } = useContents({
    type: typeFilter || undefined,
    category: categoryFilter || undefined,
    q: search || undefined,
  });
  const { data: activeJobs } = useActiveJobs();

  const byStatus = (status: ContentStatus) =>
    (data?.items ?? []).filter((c) => c.status === status);
  const failed = (data?.items ?? []).filter((c) => c.status === "실패");
  const generating = (activeJobs ?? []).filter((j) => j.kind !== "publish");

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm"
        >
          <option value="">전체 유형</option>
          {Object.entries(TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm"
        >
          <option value="">전체 카테고리</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="검색..."
          className="w-48 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm"
        />
        <button
          onClick={() => setShowGenerate(true)}
          className="ml-auto rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700"
        >
          + 새 스레드 생성
        </button>
      </div>

      {isError && (
        <p className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          데이터를 불러오지 못했습니다: {error.message}
        </p>
      )}
      {isLoading && <p className="text-sm text-gray-500">불러오는 중...</p>}

      {failed.length > 0 && (
        <div className="mb-5">
          <h2 className="mb-2 text-sm font-bold text-red-600">
            발행 실패 ({failed.length})
          </h2>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            {failed.map((c) => (
              <ContentCard key={c.id} content={c} />
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        {STATUS_ORDER.map((status) => {
          const items = byStatus(status);
          return (
            <div key={status} className="rounded-xl bg-gray-100 p-3">
              <h2 className="mb-3 flex items-center justify-between text-sm font-bold text-gray-700">
                {status}
                <span className="rounded-full bg-white px-2 py-0.5 text-xs text-gray-500">
                  {items.length}
                </span>
              </h2>
              <div className="space-y-2">
                {status === "리뷰대기" &&
                  generating.map((job) => (
                    <div
                      key={job.id}
                      className="animate-pulse rounded-lg border border-dashed border-gray-300 bg-white p-3"
                    >
                      <p className="text-xs text-gray-400">
                        AI 생성 중... ({job.kind})
                      </p>
                    </div>
                  ))}
                {items.map((c) => (
                  <ContentCard key={c.id} content={c} />
                ))}
                {items.length === 0 && status !== "리뷰대기" && (
                  <p className="py-4 text-center text-xs text-gray-400">
                    비어 있음
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {showGenerate && <GenerateModal onClose={() => setShowGenerate(false)} />}
    </div>
  );
}
