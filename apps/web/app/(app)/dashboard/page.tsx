"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import type { ContentSummary } from "@/lib/types";
import { CHANNEL_LABEL } from "@/lib/utils";

const COLUMNS: { status: ContentSummary["status"]; label: string }[] = [
  { status: "draft", label: "초안" },
  { status: "reviewing", label: "리뷰중" },
  { status: "scheduled", label: "예약됨" },
  { status: "published", label: "발행완료" },
];

export default function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["contents", "all"],
    queryFn: () => api.get<ContentSummary[]>("/contents?limit=200"),
  });

  const grouped = new Map<string, ContentSummary[]>();
  for (const col of COLUMNS) grouped.set(col.status, []);
  (data ?? []).forEach((c) => grouped.get(c.status)?.push(c));

  return (
    <div>
      <PageHeader
        title="대시보드"
        subtitle="콘텐츠 파이프라인 현황을 한눈에 확인하세요"
        actions={
          <Link href="/contents/new" className="btn-accent">새 콘텐츠</Link>
        }
      />
      {isLoading && <p className="text-sm text-muted-foreground">불러오는 중...</p>}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {COLUMNS.map((col) => {
          const items = grouped.get(col.status) || [];
          return (
            <section key={col.status} className="card min-h-[300px] bg-muted/40">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-medium">{col.label}</h2>
                <span className="text-xs text-muted-foreground">{items.length}</span>
              </div>
              <div className="space-y-2">
                {items.slice(0, 12).map((c) => (
                  <Link
                    href={`/contents/${c.id}`}
                    key={c.id}
                    className="block rounded-md bg-background p-3 border border-border
                               hover:border-accent transition-colors"
                  >
                    <div className="text-xs text-muted-foreground mb-1">
                      {CHANNEL_LABEL[c.channel]} · {c.category ?? "—"}
                    </div>
                    <div className="text-sm font-medium line-clamp-2">{c.topic}</div>
                  </Link>
                ))}
                {items.length === 0 && (
                  <p className="text-xs text-muted-foreground text-center py-6">
                    아직 없습니다
                  </p>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
