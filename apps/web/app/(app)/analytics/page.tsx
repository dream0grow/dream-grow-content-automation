"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import type { AnalyticsSummary } from "@/lib/types";
import { CHANNEL_LABEL } from "@/lib/utils";

const STAT_CARDS = [
  { key: "total_content", label: "전체 콘텐츠" },
  { key: "total_published", label: "발행 완료" },
  { key: "total_views", label: "총 조회" },
  { key: "total_likes", label: "총 좋아요" },
  { key: "total_comments", label: "총 댓글" },
] as const;

export default function AnalyticsPage() {
  const [period, setPeriod] = useState("7d");
  const { data } = useQuery({
    queryKey: ["analytics", period],
    queryFn: () => api.get<AnalyticsSummary>(`/analytics/summary?period=${period}`),
  });

  return (
    <div>
      <PageHeader
        title="분석"
        actions={
          <select className="input max-w-[140px]" value={period}
                  onChange={(e) => setPeriod(e.target.value)}>
            <option value="7d">최근 7일</option>
            <option value="30d">최근 30일</option>
            <option value="90d">최근 90일</option>
          </select>
        }
      />
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        {STAT_CARDS.map((c) => (
          <div key={c.key} className="card">
            <div className="text-xs text-muted-foreground">{c.label}</div>
            <div className="text-2xl font-semibold mt-1">
              {data ? (data as unknown as Record<string, number>)[c.key].toLocaleString() : "—"}
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <h2 className="font-medium mb-3">조회수 상위 콘텐츠</h2>
        {data && data.top_by_views.length > 0 ? (
          <>
            <div style={{ width: "100%", height: 240 }}>
              <ResponsiveContainer>
                <BarChart data={data.top_by_views.map((t) => ({ ...t, topic: t.topic.slice(0, 16) }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="topic" fontSize={11} />
                  <YAxis fontSize={11} />
                  <Tooltip />
                  <Bar dataKey="views" fill="#2563eb" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="w-full text-sm mt-4">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th>제목</th><th>채널</th><th className="text-right">조회</th>
                </tr>
              </thead>
              <tbody>
                {data.top_by_views.map((t) => (
                  <tr key={t.id} className="border-t border-border">
                    <td className="py-2">
                      <Link href={`/contents/${t.id}`} className="font-medium">
                        {t.topic}
                      </Link>
                    </td>
                    <td>{CHANNEL_LABEL[t.channel] ?? t.channel}</td>
                    <td className="text-right">{t.views.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            발행된 콘텐츠가 있어야 분석을 볼 수 있습니다
          </p>
        )}
      </div>
    </div>
  );
}
