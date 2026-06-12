"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { ApiError, api } from "@/lib/api";
import type { Job } from "@/lib/types";
import { CHANNEL_LABEL } from "@/lib/utils";

const CHANNEL_HINT: Record<string, string> = {
  thread: "Threads 자동 발행 + 분석",
  newsletter: "Maily 뉴스레터 발행",
  reels: "스크립트 + B-roll 가이드 (발행은 수동)",
  youtube: "스크립트 + 썸네일 카피 (발행은 수동)",
  magnet: "리드마그넷 PDF 자동 렌더",
};

const CATEGORIES = [
  "훈육", "수학", "독서", "미디어", "놀이",
  "감정", "학습", "학교", "크리에이터",
];

export default function NewContentPage() {
  const router = useRouter();
  const [channel, setChannel] = useState("thread");
  const [topic, setTopic] = useState("");
  const [category, setCategory] = useState("");
  const [tone, setTone] = useState("");
  const [magnetType, setMagnetType] = useState("action_guide");
  const [jobId, setJobId] = useState<string | null>(null);
  const [contentId, setContentId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await api.post<{ content_id: string; job_id: string }>(
        "/contents/generate",
        { channel, topic, category, tone,
          magnet_type: channel === "magnet" ? magnetType : null },
      );
      setJobId(res.job_id);
      setContentId(res.content_id);
      setJobStatus("queued");
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("요청에 실패했습니다");
    }
  }

  useEffect(() => {
    if (!jobId) return;
    const source = new EventSource(`/api/v1/events/stream?job_id=${jobId}`);
    source.addEventListener("job", (e) => {
      try {
        const payload = JSON.parse((e as MessageEvent).data);
        setJobStatus(payload.status);
        if (payload.status === "done" && contentId) {
          setTimeout(() => router.push(`/contents/${contentId}`), 800);
          source.close();
        }
      } catch {/* ignore */}
    });
    const poll = setInterval(async () => {
      try {
        const job = await api.get<Job>(`/jobs/${jobId}`);
        setJobStatus(job.status);
        if (job.status === "done" && contentId) {
          router.push(`/contents/${contentId}`);
          source.close();
          clearInterval(poll);
        }
        if (job.status === "failed") {
          setError(job.error || "생성 실패");
          source.close();
          clearInterval(poll);
        }
      } catch {/* ignore */}
    }, 3000);
    return () => { source.close(); clearInterval(poll); };
  }, [jobId, contentId, router]);

  return (
    <div className="max-w-2xl">
      <PageHeader title="새 콘텐츠 생성" subtitle="채널과 주제를 선택하면 AI가 초안을 작성합니다" />
      <form onSubmit={submit} className="card space-y-4">
        <div>
          <label className="label">채널</label>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {Object.entries(CHANNEL_LABEL).map(([v, l]) => (
              <button type="button" key={v}
                onClick={() => setChannel(v)}
                className={`btn ${channel === v ? "btn-primary" : "btn-ghost border border-border"}`}>
                {l}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground mt-2">{CHANNEL_HINT[channel]}</p>
        </div>
        <div>
          <label className="label">주제</label>
          <input className="input" value={topic} required
                 onChange={(e) => setTopic(e.target.value)}
                 placeholder="예: 초등 2학년 수학 자존감 회복하는 법" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">카테고리</label>
            <select className="input" value={category}
                    onChange={(e) => setCategory(e.target.value)}>
              <option value="">선택 안함</option>
              {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="label">톤 (선택)</label>
            <input className="input" value={tone}
                   onChange={(e) => setTone(e.target.value)}
                   placeholder="예: 차분하고 단단한" />
          </div>
        </div>
        {channel === "magnet" && (
          <div>
            <label className="label">리드마그넷 유형</label>
            <select className="input" value={magnetType}
                    onChange={(e) => setMagnetType(e.target.value)}>
              <option value="checklist">체크리스트</option>
              <option value="concept_map">개념 지도</option>
              <option value="action_guide">실천 가이드</option>
              <option value="worksheet">워크시트</option>
              <option value="roadmap">로드맵</option>
            </select>
          </div>
        )}
        {error && <div className="text-sm text-destructive">{error}</div>}
        <button type="submit" disabled={!!jobId} className="btn-accent w-full">
          {jobId ? `생성 중 (${jobStatus})...` : "AI 초안 생성"}
        </button>
        {jobId && (
          <p className="text-xs text-muted-foreground text-center">
            완료되면 에디터로 이동합니다
          </p>
        )}
      </form>
    </div>
  );
}
