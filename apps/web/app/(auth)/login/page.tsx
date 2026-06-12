"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { ApiError, api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const search = useSearchParams();
  const [email, setEmail] = useState("admin@dreamgrow.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.post("/auth/login", { email, password });
      router.push(search.get("next") || "/dashboard");
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("로그인에 실패했습니다");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted">
      <form
        onSubmit={onSubmit}
        className="card w-full max-w-sm space-y-4 bg-white"
      >
        <div>
          <h1 className="text-xl font-semibold">Dream Grow Content Studio</h1>
          <p className="text-sm text-muted-foreground mt-1">관리자 로그인</p>
        </div>
        <div>
          <label className="label">이메일</label>
          <input className="input" type="email" value={email}
                 onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div>
          <label className="label">비밀번호</label>
          <input className="input" type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {error && (
          <div className="text-sm text-destructive bg-rose-50 border border-rose-200
                          rounded-md p-2">
            {error}
          </div>
        )}
        <button type="submit" disabled={submitting} className="btn-primary w-full">
          {submitting ? "로그인 중..." : "로그인"}
        </button>
      </form>
    </div>
  );
}
