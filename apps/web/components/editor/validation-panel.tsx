"use client";
import { AlertCircle, CheckCircle2, Info } from "lucide-react";

import type { Issue, ReviewResponse } from "@/lib/types";

const ICON: Record<Issue["severity"], JSX.Element> = {
  ERROR: <AlertCircle className="h-4 w-4 text-destructive" />,
  WARN:  <AlertCircle className="h-4 w-4 text-amber-500" />,
  INFO:  <Info className="h-4 w-4 text-blue-500" />,
};

const COLOR: Record<Issue["severity"], string> = {
  ERROR: "border-rose-200 bg-rose-50",
  WARN:  "border-amber-200 bg-amber-50",
  INFO:  "border-blue-200 bg-blue-50",
};

type Props = { review: ReviewResponse | null; loading: boolean };

export function ValidationPanel({ review, loading }: Props) {
  if (loading) return <p className="text-sm text-muted-foreground">검수 중...</p>;
  if (!review) return <p className="text-sm text-muted-foreground">검수 실행을 눌러주세요</p>;
  return (
    <div className="space-y-3">
      <div className={`p-3 rounded-md border flex items-center gap-2
                       ${review.passed ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
        {review.passed
          ? <CheckCircle2 className="h-5 w-5 text-emerald-600" />
          : <AlertCircle className="h-5 w-5 text-amber-600" />}
        <span className="font-medium">
          {review.passed ? "검수 통과" : `${review.issues.length}개 이슈 발견`}
        </span>
      </div>
      {review.issues.map((issue, idx) => (
        <div key={idx} className={`p-3 rounded-md border ${COLOR[issue.severity]}`}>
          <div className="flex items-center gap-2 mb-1">
            {ICON[issue.severity]}
            <span className="text-xs font-medium uppercase tracking-wide">
              {issue.severity}
            </span>
            <span className="text-xs text-muted-foreground">{issue.category}</span>
            {issue.line > 0 && (
              <span className="text-xs text-muted-foreground">L{issue.line}</span>
            )}
          </div>
          <p className="text-sm">{issue.message}</p>
        </div>
      ))}
    </div>
  );
}
