"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import type { ContentSummary } from "@/lib/types";
import { CHANNEL_LABEL, STATUS_BADGE_CLASS, STATUS_LABEL } from "@/lib/utils";

export default function ContentsPage() {
  const [q, setQ] = useState("");
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["contents", { q, channel, status }],
    queryFn: () => {
      const sp = new URLSearchParams();
      if (q) sp.set("q", q);
      if (channel) sp.set("channel", channel);
      if (status) sp.set("status", status);
      return api.get<ContentSummary[]>(`/contents?${sp.toString()}`);
    },
  });

  return (
    <div>
      <PageHeader
        title="콘텐츠"
        actions={<Link className="btn-accent" href="/contents/new">새 콘텐츠</Link>}
      />
      <div className="flex flex-wrap gap-2 mb-4">
        <input className="input max-w-xs" placeholder="제목 검색"
               value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input max-w-xs" value={channel}
                onChange={(e) => setChannel(e.target.value)}>
          <option value="">모든 채널</option>
          {Object.entries(CHANNEL_LABEL).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
        <select className="input max-w-xs" value={status}
                onChange={(e) => setStatus(e.target.value)}>
          <option value="">모든 상태</option>
          {Object.entries(STATUS_LABEL).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </div>

      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead className="bg-muted text-left">
            <tr>
              <th className="px-3 py-2">제목</th>
              <th className="px-3 py-2">채널</th>
              <th className="px-3 py-2">카테고리</th>
              <th className="px-3 py-2">상태</th>
              <th className="px-3 py-2">업데이트</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((c) => (
              <tr key={c.id} className="border-t border-border hover:bg-muted/40">
                <td className="px-3 py-2">
                  <Link href={`/contents/${c.id}`} className="font-medium">
                    {c.topic}
                  </Link>
                </td>
                <td className="px-3 py-2">{CHANNEL_LABEL[c.channel] ?? c.channel}</td>
                <td className="px-3 py-2">{c.category ?? "—"}</td>
                <td className="px-3 py-2">
                  <span className={STATUS_BADGE_CLASS[c.status]}>
                    {STATUS_LABEL[c.status] ?? c.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {new Date(c.updated_at).toLocaleString("ko-KR")}
                </td>
              </tr>
            ))}
            {isLoading && (
              <tr><td colSpan={5} className="text-center py-6 text-muted-foreground">
                불러오는 중...
              </td></tr>
            )}
            {!isLoading && (data?.length ?? 0) === 0 && (
              <tr><td colSpan={5} className="text-center py-6 text-muted-foreground">
                콘텐츠가 없습니다
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
