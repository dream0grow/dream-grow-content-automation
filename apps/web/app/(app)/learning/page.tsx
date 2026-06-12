"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import { CHANNEL_LABEL } from "@/lib/utils";

type Pattern = {
  id: string; channel: string; pattern_type: string | null;
  summary: string | null; source: string | null; created_at: string;
};

export default function LearningPage() {
  const qc = useQueryClient();
  const [channel, setChannel] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["learning", channel],
    queryFn: () => api.get<Pattern[]>(`/learning${channel ? `?channel=${channel}` : ""}`),
  });
  const run = useMutation({
    mutationFn: () => api.post("/learning/run", {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["learning"] }),
  });

  return (
    <div>
      <PageHeader
        title="학습 패턴"
        subtitle="AI 초안과 사용자 편집의 차이에서 학습한 패턴"
        actions={
          <div className="flex gap-2">
            <select className="input max-w-[160px]" value={channel}
                    onChange={(e) => setChannel(e.target.value)}>
              <option value="">모든 채널</option>
              {Object.entries(CHANNEL_LABEL).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
            <button className="btn-primary"
                    onClick={() => run.mutate()} disabled={run.isPending}>
              {run.isPending ? "실행 중..." : "학습 실행"}
            </button>
          </div>
        }
      />
      {isLoading && <p className="text-sm text-muted-foreground">불러오는 중...</p>}
      <div className="space-y-3">
        {(data ?? []).map((p) => (
          <article key={p.id} className="card">
            <div className="flex items-center justify-between mb-2">
              <span className="badge bg-muted text-foreground">
                {CHANNEL_LABEL[p.channel] ?? p.channel} · {p.pattern_type ?? "—"}
              </span>
              <span className="text-xs text-muted-foreground">
                {new Date(p.created_at).toLocaleString("ko-KR")}
              </span>
            </div>
            <p className="text-sm whitespace-pre-wrap">{p.summary}</p>
            {p.source && (
              <p className="text-xs text-muted-foreground mt-2">출처: {p.source}</p>
            )}
          </article>
        ))}
        {!isLoading && (data?.length ?? 0) === 0 && (
          <p className="text-sm text-muted-foreground">학습된 패턴이 없습니다</p>
        )}
      </div>
    </div>
  );
}
