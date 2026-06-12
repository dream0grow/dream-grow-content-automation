"use client";
type Props = {
  topic: string;
  category: string;
  status: string;
  channel: string;
  onChange: (patch: Partial<{ topic: string; category: string; status: string }>) => void;
};

import { CHANNEL_LABEL, STATUS_LABEL } from "@/lib/utils";

const CATEGORIES = [
  "훈육", "수학", "독서", "미디어", "놀이", "감정", "학습", "학교", "크리에이터",
];

export function FrontmatterForm({ topic, category, status, channel, onChange }: Props) {
  return (
    <div className="card space-y-3">
      <div>
        <label className="label">주제</label>
        <input className="input" value={topic}
               onChange={(e) => onChange({ topic: e.target.value })} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">카테고리</label>
          <select className="input" value={category || ""}
                  onChange={(e) => onChange({ category: e.target.value })}>
            <option value="">선택 안함</option>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className="label">상태</label>
          <select className="input" value={status}
                  onChange={(e) => onChange({ status: e.target.value })}>
            {Object.entries(STATUS_LABEL).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="text-xs text-muted-foreground">
        채널: <strong>{CHANNEL_LABEL[channel] ?? channel}</strong>
      </div>
    </div>
  );
}
