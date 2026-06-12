"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import type { ScheduleItem } from "@/lib/types";
import { CHANNEL_LABEL } from "@/lib/utils";

function startOfMonth(d: Date) { return new Date(d.getFullYear(), d.getMonth(), 1); }
function endOfMonth(d: Date) { return new Date(d.getFullYear(), d.getMonth() + 1, 0); }
function addMonths(d: Date, n: number) {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

export default function CalendarPage() {
  const [cursor, setCursor] = useState(startOfMonth(new Date()));
  const from = startOfMonth(cursor).toISOString();
  const to = endOfMonth(cursor).toISOString();

  const { data } = useQuery({
    queryKey: ["schedule", from, to],
    queryFn: () => api.get<ScheduleItem[]>(`/schedule?from=${from}&to=${to}`),
  });

  const byDay = useMemo(() => {
    const m = new Map<string, ScheduleItem[]>();
    (data ?? []).forEach((s) => {
      const key = s.scheduled_at.slice(0, 10);
      if (!m.has(key)) m.set(key, []);
      m.get(key)!.push(s);
    });
    return m;
  }, [data]);

  const monthStart = startOfMonth(cursor);
  const firstDow = monthStart.getDay();
  const daysInMonth = endOfMonth(cursor).getDate();
  const cells: (Date | null)[] = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push(new Date(cursor.getFullYear(), cursor.getMonth(), d));
  }

  return (
    <div>
      <PageHeader
        title="발행 캘린더"
        subtitle="예약된 콘텐츠를 한눈에 확인하세요"
        actions={
          <div className="flex items-center gap-2">
            <button className="btn-ghost border border-border"
                    onClick={() => setCursor(addMonths(cursor, -1))}>이전</button>
            <span className="font-medium text-sm w-24 text-center">
              {cursor.getFullYear()}년 {cursor.getMonth() + 1}월
            </span>
            <button className="btn-ghost border border-border"
                    onClick={() => setCursor(addMonths(cursor, 1))}>다음</button>
          </div>
        }
      />
      <div className="grid grid-cols-7 gap-px bg-border rounded-lg overflow-hidden">
        {["일", "월", "화", "수", "목", "금", "토"].map((d) => (
          <div key={d} className="bg-muted px-2 py-1 text-xs font-medium text-center">{d}</div>
        ))}
        {cells.map((d, idx) => {
          if (!d) return <div key={idx} className="bg-background min-h-[120px]" />;
          const key = d.toISOString().slice(0, 10);
          const items = byDay.get(key) ?? [];
          return (
            <div key={idx} className="bg-background min-h-[120px] p-2">
              <div className="text-xs text-muted-foreground mb-1">{d.getDate()}</div>
              <div className="space-y-1">
                {items.map((s) => (
                  <Link key={s.id} href={`/contents/${s.content_id}`}
                        className="block text-xs rounded px-1 py-0.5 bg-accent/10
                                   border border-accent/30 hover:bg-accent/20">
                    <div className="font-medium truncate">{s.topic}</div>
                    <div className="text-[10px] text-muted-foreground">
                      {new Date(s.scheduled_at).toLocaleTimeString("ko-KR",
                        { hour: "2-digit", minute: "2-digit" })}
                      {" · "}{CHANNEL_LABEL[s.channel]}
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
