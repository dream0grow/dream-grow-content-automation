"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import type { BrandProfile } from "@/lib/types";

export default function BrandPage() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["brand"],
    queryFn: () => api.get<BrandProfile>("/brand"),
  });

  const [form, setForm] = useState<BrandProfile>({
    brand_name: "Dream_Grow",
    target_audience: "",
    tone_notes: "",
    banned_phrases: [],
    required_ending: "",
    brand_signature: "",
    categories: [],
  });
  const [bannedInput, setBannedInput] = useState("");
  const [categoryInput, setCategoryInput] = useState("");

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  const save = useMutation({
    mutationFn: (payload: BrandProfile) => api.put("/brand", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["brand"] }),
  });

  return (
    <div className="max-w-2xl">
      <PageHeader title="브랜드 프로필"
                  subtitle="콘텐츠 생성 시 자동 반영되는 브랜드 규칙을 설정하세요" />
      <div className="card space-y-4">
        <div>
          <label className="label">브랜드명</label>
          <input className="input" value={form.brand_name}
                 onChange={(e) => setForm({ ...form, brand_name: e.target.value })} />
        </div>
        <div>
          <label className="label">타겟 독자</label>
          <input className="input" value={form.target_audience ?? ""}
                 onChange={(e) => setForm({ ...form, target_audience: e.target.value })} />
        </div>
        <div>
          <label className="label">톤 메모</label>
          <textarea className="input min-h-[80px]" value={form.tone_notes ?? ""}
                    onChange={(e) => setForm({ ...form, tone_notes: e.target.value })} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">필수 마무리</label>
            <input className="input" value={form.required_ending ?? ""}
                   onChange={(e) => setForm({ ...form, required_ending: e.target.value })} />
          </div>
          <div>
            <label className="label">브랜드 서명</label>
            <input className="input" value={form.brand_signature ?? ""}
                   onChange={(e) => setForm({ ...form, brand_signature: e.target.value })} />
          </div>
        </div>

        <Chips
          label="금지 문구"
          values={form.banned_phrases}
          input={bannedInput}
          onInput={setBannedInput}
          onAdd={(v) => setForm({ ...form, banned_phrases: [...form.banned_phrases, v] })}
          onRemove={(v) => setForm({ ...form,
            banned_phrases: form.banned_phrases.filter((x) => x !== v) })}
        />
        <Chips
          label="카테고리"
          values={form.categories}
          input={categoryInput}
          onInput={setCategoryInput}
          onAdd={(v) => setForm({ ...form, categories: [...form.categories, v] })}
          onRemove={(v) => setForm({ ...form,
            categories: form.categories.filter((x) => x !== v) })}
        />

        <button className="btn-primary"
                disabled={save.isPending}
                onClick={() => save.mutate(form)}>
          {save.isPending ? "저장 중..." : "저장"}
        </button>
      </div>
    </div>
  );
}

function Chips({ label, values, input, onInput, onAdd, onRemove }: {
  label: string;
  values: string[];
  input: string;
  onInput: (v: string) => void;
  onAdd: (v: string) => void;
  onRemove: (v: string) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <div className="flex flex-wrap gap-1 mb-2">
        {values.map((v) => (
          <span key={v} className="badge bg-muted text-foreground inline-flex items-center gap-1">
            {v}
            <button onClick={() => onRemove(v)}><X className="h-3 w-3" /></button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input className="input" value={input}
               onChange={(e) => onInput(e.target.value)}
               onKeyDown={(e) => {
                 if (e.key === "Enter" && input.trim()) {
                   e.preventDefault();
                   onAdd(input.trim()); onInput("");
                 }
               }} placeholder="입력 후 Enter" />
        <button type="button" className="btn-ghost border border-border"
                onClick={() => { if (input.trim()) { onAdd(input.trim()); onInput(""); } }}>
          추가
        </button>
      </div>
    </div>
  );
}
