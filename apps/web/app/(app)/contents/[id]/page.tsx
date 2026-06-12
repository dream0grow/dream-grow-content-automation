"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { FrontmatterForm } from "@/components/editor/frontmatter-form";
import { MarkdownEditor } from "@/components/editor/markdown-editor";
import { ValidationPanel } from "@/components/editor/validation-panel";
import { PageHeader } from "@/components/page-header";
import { ApiError, api } from "@/lib/api";
import type { Content, ReviewResponse } from "@/lib/types";
import { CHANNEL_LABEL, STATUS_BADGE_CLASS, STATUS_LABEL } from "@/lib/utils";

type Tab = "preview" | "diff" | "validation";

export default function ContentDetailPage({ params }: { params: { id: string } }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["content", params.id],
    queryFn: () => api.get<Content>(`/contents/${params.id}`),
  });

  const [body, setBody] = useState("");
  const [topic, setTopic] = useState("");
  const [category, setCategory] = useState("");
  const [statusValue, setStatusValue] = useState("draft");
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState<Tab>("preview");
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [scheduleAt, setScheduleAt] = useState("");
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setBody(data.body_md);
    setTopic(data.topic);
    setCategory(data.category || "");
    setStatusValue(data.status);
    setDirty(false);
  }, [data]);

  const save = useMutation({
    mutationFn: () => api.patch<Content>(`/contents/${params.id}`, {
      body_md: body, topic, category: category || null, status: statusValue,
    }),
    onSuccess: (next) => {
      qc.setQueryData(["content", params.id], next);
      setDirty(false);
      setActionMsg("저장 완료");
      setTimeout(() => setActionMsg(null), 2000);
    },
    onError: (err) => {
      setActionMsg(err instanceof ApiError ? err.message : "저장 실패");
    },
  });

  async function runReview() {
    setReviewing(true);
    try {
      const r = await api.post<ReviewResponse>(`/contents/${params.id}/review`, {});
      setReview(r);
      setTab("validation");
    } finally { setReviewing(false); }
  }

  async function schedule() {
    if (!scheduleAt) return;
    try {
      await api.post(`/contents/${params.id}/schedule`,
        { scheduled_at: new Date(scheduleAt).toISOString(),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone });
      setActionMsg("예약 등록 완료");
    } catch (err) {
      setActionMsg(err instanceof ApiError ? err.message : "예약 실패");
    }
  }

  async function publish() {
    try {
      await api.post(`/contents/${params.id}/publish`, {});
      setActionMsg("즉시 발행 잡 제출");
    } catch (err) {
      setActionMsg(err instanceof ApiError ? err.message : "발행 실패");
    }
  }

  const diff = useMemo(() => {
    if (!data?.ai_original_md) return null;
    return computeLineDiff(data.ai_original_md, body);
  }, [data?.ai_original_md, body]);

  if (isLoading || !data) {
    return <p className="text-sm text-muted-foreground">불러오는 중...</p>;
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={topic || "(제목 없음)"}
        subtitle={`${CHANNEL_LABEL[data.channel]} · ${data.category ?? "—"}`}
        actions={
          <div className="flex items-center gap-2">
            <span className={STATUS_BADGE_CLASS[statusValue]}>
              {STATUS_LABEL[statusValue]}
            </span>
            <button onClick={() => save.mutate()} disabled={!dirty || save.isPending}
                    className="btn-primary">
              {save.isPending ? "저장 중..." : "저장"}
            </button>
            <button onClick={runReview} className="btn-ghost border border-border">
              {reviewing ? "검수 중..." : "검수 실행"}
            </button>
          </div>
        }
      />
      {actionMsg && (
        <div className="text-sm text-muted-foreground bg-muted rounded-md p-2">
          {actionMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6">
        <div className="space-y-3">
          <MarkdownEditor value={body}
                          onChange={(v) => { setBody(v); setDirty(true); }} />
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label className="label">예약 발행 일시</label>
              <input type="datetime-local" className="input"
                     value={scheduleAt}
                     onChange={(e) => setScheduleAt(e.target.value)} />
            </div>
            <button onClick={schedule} className="btn-primary">예약</button>
            {(data.channel === "thread" || data.channel === "newsletter") && (
              <button onClick={publish} className="btn-accent">즉시 발행</button>
            )}
          </div>
        </div>

        <aside className="space-y-3">
          <FrontmatterForm
            topic={topic} category={category} status={statusValue}
            channel={data.channel}
            onChange={(p) => {
              if (p.topic !== undefined) setTopic(p.topic);
              if (p.category !== undefined) setCategory(p.category);
              if (p.status !== undefined) setStatusValue(p.status);
              setDirty(true);
            }}
          />
          <div className="card">
            <div className="flex gap-1 mb-3 border-b border-border">
              {(["preview", "diff", "validation"] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-3 py-2 text-sm border-b-2 transition-colors
                              ${tab === t ? "border-accent text-accent" :
                                "border-transparent text-muted-foreground hover:text-foreground"}`}>
                  {t === "preview" ? "미리보기" : t === "diff" ? "AI원본 Diff" : "검수"}
                </button>
              ))}
            </div>
            {tab === "preview" && (
              <pre className="whitespace-pre-wrap text-sm leading-relaxed">{body}</pre>
            )}
            {tab === "diff" && (
              diff ? (
                <pre className="text-xs leading-relaxed overflow-x-auto">
                  {diff.map((d, i) => (
                    <div key={i} className={
                      d.type === "+" ? "text-emerald-700 bg-emerald-50"
                      : d.type === "-" ? "text-rose-700 bg-rose-50"
                      : "text-muted-foreground"}>
                      {d.type === "=" ? "  " : d.type + " "}{d.text}
                    </div>
                  ))}
                </pre>
              ) : <p className="text-sm text-muted-foreground">AI 원본 없음</p>
            )}
            {tab === "validation" && (
              <ValidationPanel review={review} loading={reviewing} />
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

type DiffLine = { type: "+" | "-" | "="; text: string };
function computeLineDiff(a: string, b: string): DiffLine[] {
  const aLines = a.split("\n");
  const bLines = b.split("\n");
  const setB = new Set(bLines);
  const setA = new Set(aLines);
  const out: DiffLine[] = [];
  let i = 0, j = 0;
  while (i < aLines.length || j < bLines.length) {
    if (i < aLines.length && j < bLines.length && aLines[i] === bLines[j]) {
      out.push({ type: "=", text: aLines[i] }); i++; j++;
    } else if (j < bLines.length && !setA.has(bLines[j])) {
      out.push({ type: "+", text: bLines[j] }); j++;
    } else if (i < aLines.length && !setB.has(aLines[i])) {
      out.push({ type: "-", text: aLines[i] }); i++;
    } else if (i < aLines.length) { out.push({ type: "-", text: aLines[i] }); i++; }
    else { out.push({ type: "+", text: bLines[j] }); j++; }
  }
  return out;
}
