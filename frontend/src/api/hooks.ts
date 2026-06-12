import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "./client";
import type {
  AutoScheduleItem,
  CalendarDay,
  ContentDetail,
  ContentList,
  Job,
  PublishLog,
  ReviewResult,
  SystemStatus,
} from "./types";

export function useContents(filters: {
  status?: string;
  type?: string;
  category?: string;
  q?: string;
}) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v) params.set(k, v);
  }
  const qs = params.toString();
  return useQuery({
    queryKey: ["contents", filters],
    queryFn: () => api.get<ContentList>(`/contents${qs ? `?${qs}` : ""}`),
  });
}

export function useContent(id: number | null) {
  return useQuery({
    queryKey: ["content", id],
    queryFn: () => api.get<ContentDetail>(`/contents/${id}`),
    enabled: id !== null,
  });
}

export function useJob(jobId: number | null) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.get<Job>(`/generate/jobs/${jobId}`),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "done" || status === "failed" ? false : 2000;
    },
  });
}

export function useActiveJobs() {
  return useQuery({
    queryKey: ["jobs", "active"],
    queryFn: () => api.get<Job[]>("/generate/jobs?active=true"),
    refetchInterval: (query) =>
      (query.state.data?.length ?? 0) > 0 ? 3000 : 15000,
  });
}

export function useSystemStatus() {
  return useQuery({
    queryKey: ["system"],
    queryFn: () => api.get<SystemStatus>("/system/status"),
    refetchInterval: 60000,
  });
}

export function useCalendar(start: string, end: string) {
  return useQuery({
    queryKey: ["calendar", start, end],
    queryFn: () =>
      api.get<{ days: CalendarDay[] }>(`/calendar?start=${start}&end=${end}`),
  });
}

export function usePublishLogs(contentId: number) {
  return useQuery({
    queryKey: ["publish-logs", contentId],
    queryFn: () => api.get<PublishLog[]>(`/contents/${contentId}/publish-logs`),
  });
}

export function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["contents"] });
    qc.invalidateQueries({ queryKey: ["content"] });
    qc.invalidateQueries({ queryKey: ["calendar"] });
  };
}

export function useGenerateThread() {
  return useMutation({
    mutationFn: (payload: { topic: string; tone?: string; category: string }) =>
      api.post<{ job_id: number }>("/generate/thread", payload),
  });
}

export function useDerive(kind: "reels" | "newsletter") {
  return useMutation({
    mutationFn: (contentId: number) =>
      api.post<{ job_id: number }>(
        `/contents/${contentId}/derive/${kind}`,
        kind === "newsletter" ? {} : undefined,
      ),
  });
}

export function useUpdateContent(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (payload: { title?: string; body?: string; category?: string }) =>
      api.put<ContentDetail>(`/contents/${id}`, payload),
    onSuccess: invalidate,
  });
}

export function useStatusChange(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (payload: { status: string; force?: boolean }) =>
      api.post<ContentDetail>(`/contents/${id}/status`, payload),
    onSuccess: invalidate,
  });
}

export function useRunReview(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => api.post<ReviewResult>(`/contents/${id}/review`),
    onSuccess: invalidate,
  });
}

export function useReviewFix(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () =>
      api.post<{ body: string; fixes: string[]; review: ReviewResult }>(
        `/contents/${id}/review/fix`,
      ),
    onSuccess: invalidate,
  });
}

export function useSchedule(id: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (scheduledAt: string | null) =>
      api.post<ContentDetail>(`/contents/${id}/schedule`, {
        scheduled_at: scheduledAt,
      }),
    onSuccess: invalidate,
  });
}

export function usePublishNow(id: number) {
  return useMutation({
    mutationFn: () => api.post<{ job_id: number }>(`/contents/${id}/publish`),
  });
}

export function useAutoSchedule() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (payload: { days?: number; preview: boolean }) =>
      api.post<{ committed: boolean; assignments: AutoScheduleItem[] }>(
        "/calendar/auto-schedule",
        payload,
      ),
    onSuccess: invalidate,
  });
}

export function useDeleteContent() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => api.delete(`/contents/${id}`),
    onSuccess: invalidate,
  });
}
