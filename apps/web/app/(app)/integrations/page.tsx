"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, XCircle } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import type { Integration } from "@/lib/types";

const PROVIDER_FIELDS: Record<string, { key: string; label: string; type?: string }[]> = {
  threads: [
    { key: "access_token", label: "Access Token", type: "password" },
    { key: "user_id", label: "User ID" },
  ],
  maily: [{ key: "access_token", label: "Access Token", type: "password" }],
  honcho: [{ key: "api_key", label: "API Key", type: "password" }],
  anthropic: [{ key: "api_key", label: "API Key", type: "password" }],
};

export default function IntegrationsPage() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["integrations"],
    queryFn: () => api.get<Integration[]>("/integrations"),
  });

  return (
    <div>
      <PageHeader title="연동"
                  subtitle="외부 서비스 자격증명은 Fernet으로 암호화되어 저장됩니다" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {(data ?? []).map((it) => (
          <IntegrationCard key={it.provider} integration={it}
                           onChange={() => qc.invalidateQueries({ queryKey: ["integrations"] })} />
        ))}
      </div>
    </div>
  );
}

function IntegrationCard({ integration, onChange }:
  { integration: Integration; onChange: () => void }) {
  const fields = PROVIDER_FIELDS[integration.provider] ?? [];
  const [values, setValues] = useState<Record<string, string>>({});
  const [testResult, setTestResult] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => api.put(`/integrations/${integration.provider}`,
                              { credentials: values }),
    onSuccess: () => { setValues({}); onChange(); },
  });

  const test = useMutation({
    mutationFn: () => api.post<{ ok: boolean; message: string }>(
      `/integrations/${integration.provider}/test`, {}),
    onSuccess: (r) => setTestResult(r.ok ? `OK: ${r.message}` : `실패: ${r.message}`),
  });

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-medium capitalize">{integration.provider}</h2>
        <span className="flex items-center gap-1 text-xs">
          {integration.connected
            ? <><CheckCircle2 className="h-4 w-4 text-emerald-600" /> 연결됨</>
            : <><XCircle className="h-4 w-4 text-muted-foreground" /> 미연결</>}
        </span>
      </div>
      {fields.map((f) => (
        <div key={f.key}>
          <label className="label">{f.label}</label>
          <input className="input" type={f.type ?? "text"}
                 value={values[f.key] ?? ""}
                 onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
        </div>
      ))}
      <div className="flex gap-2">
        <button className="btn-primary"
                onClick={() => save.mutate()}
                disabled={save.isPending || fields.some((f) => !values[f.key])}>
          저장
        </button>
        <button className="btn-ghost border border-border"
                onClick={() => test.mutate()}
                disabled={test.isPending || !integration.connected}>
          연결 테스트
        </button>
      </div>
      {testResult && <p className="text-xs text-muted-foreground">{testResult}</p>}
    </div>
  );
}
