import { useMutation, useQuery, useQueryClient, useQueries } from "@tanstack/react-query";

import { api, toQuery } from "@/lib/api";
import type {
  AnalysisJob,
  AnalysisStats,
  Analytics,
  Application,
  ApplicationDetail,
  ApplicationInput,
  ApplicationStatus,
  ApplicationUpdate,
  Company,
  CompanyInput,
  CompanyOption,
  Dashboard,
  FollowUp,
  FollowUpInput,
  Interview,
  InterviewInput,
  JobDescription,
  JobDescriptionInput,
  JobDescriptionListItem,
  KanbanBoard,
  MetaResponse,
  Page,
  Resume,
  ResumeDetail,
  ResumeScore,
  ResumeUsage,
  ResumeVersion,
  SessionView,
  Task,
  TaskInput,
  TimeEntry,
  TimeEntryInput,
} from "@/lib/types";

export const keys = {
  dashboard: ["dashboard"] as const,
  applications: (params: unknown) => ["applications", params] as const,
  application: (id: string) => ["application", id] as const,
  board: (includeArchived: boolean) => ["applications", "board", includeArchived] as const,
  companies: (params: Record<string, unknown>) => ["companies", params] as const,
  companyOptions: ["companies", "options"] as const,
  jobDescriptions: (params: Record<string, unknown>) => ["job-descriptions", params] as const,
  jobDescription: (id: string) => ["job-description", id] as const,
  jobOptions: (companyId?: string) => ["job-descriptions", "options", companyId ?? "all"] as const,
  resumes: (params: Record<string, unknown>) => ["resumes", params] as const,
  resume: (id: string) => ["resume", id] as const,
  resumeUsage: (id: string) => ["resume", id, "usage"] as const,
  sessions: ["auth", "sessions"] as const,
  meta: ["auth", "meta"] as const,
  analyses: (params: object) => ["analyses", params] as const,
  analysis: (id: string) => ["analyses", "job", id] as const,
  analysisStats: ["analyses", "stats"] as const,
  resumeScores: ["analyses", "resume-scores"] as const,
  analytics: ["analytics"] as const,
  tasks: (params: object) => ["tasks", params] as const,
  followUps: (params: Record<string, unknown>) => ["follow-ups", params] as const,
  interviews: (params: Record<string, unknown>) => ["interviews", params] as const,
  timeEntries: (params: Record<string, unknown>) => ["time-entries", params] as const,
};

export interface ApplicationFilters {
  search?: string;
  status?: ApplicationStatus[];
  company_id?: string;
  work_mode?: string;
  date_from?: string;
  date_to?: string;
  include_archived?: boolean;
  sort?: string;
  page?: number;
  page_size?: number;
}

export function useDashboard() {
  return useQuery({
    queryKey: keys.dashboard,
    queryFn: () => api.get<Dashboard>("/dashboard"),
  });
}

export function useApplications(filters: ApplicationFilters) {
  return useQuery({
    queryKey: keys.applications(filters),
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(filters.page ?? 1));
      params.set("page_size", String(filters.page_size ?? 20));
      params.set("sort", filters.sort ?? "-created_at");
      if (filters.search) params.set("search", filters.search);
      if (filters.company_id) params.set("company_id", filters.company_id);
      if (filters.work_mode) params.set("work_mode", filters.work_mode);
      if (filters.date_from) params.set("date_from", filters.date_from);
      if (filters.date_to) params.set("date_to", filters.date_to);
      if (filters.include_archived) params.set("include_archived", "true");
      for (const status of filters.status ?? []) params.append("status", status);
      return api.get<Page<Application>>(`/applications?${params.toString()}`);
    },
  });
}

export function useApplicationBoard(includeArchived: boolean) {
  return useQuery({
    queryKey: keys.board(includeArchived),
    queryFn: () =>
      api.get<KanbanBoard>(`/applications/board${toQuery({ include_archived: includeArchived })}`),
  });
}

export function useApplication(id: string | null) {
  return useQuery({
    queryKey: keys.application(id ?? ""),
    queryFn: () => api.get<ApplicationDetail>(`/applications/${id}`),
    enabled: Boolean(id),
  });
}

function useInvalidateApplications() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["applications"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["companies"] });
    void queryClient.invalidateQueries({ queryKey: ["resumes"] });
  };
}

export function useCreateApplication() {
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: (payload: ApplicationInput) => api.post<Application>("/applications", payload),
    onSuccess: invalidate,
  });
}

export function useUpdateApplication(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: (payload: ApplicationUpdate) =>
      api.patch<Application>(`/applications/${id}`, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.application(id), (current: ApplicationDetail | undefined) =>
        current ? { ...current, ...data } : current,
      );
      invalidate();
    },
  });
}

export function useChangeStatus(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: ({ status, note }: { status: ApplicationStatus; note?: string }) =>
      api.post<Application>(`/applications/${id}/status`, { status, note }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.application(id) });
      invalidate();
    },
  });
}

export function useAddNote(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: (note: string) => api.post<Application>(`/applications/${id}/notes`, { note }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.application(id) });
      invalidate();
    },
  });
}

export function useArchiveApplication(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: (archived: boolean) =>
      api.post<Application>(`/applications/${id}/archive${toQuery({ archived })}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.application(id) });
      invalidate();
    },
  });
}

export function useDeleteApplication(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateApplications();
  return useMutation({
    mutationFn: () => api.delete<void>(`/applications/${id}`),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: keys.application(id) });
      invalidate();
    },
  });
}

export function useCompanies(filters: { search?: string; include_archived?: boolean; page?: number } = {}) {
  return useQuery({
    queryKey: keys.companies(filters),
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(filters.page ?? 1));
      params.set("page_size", "100");
      if (filters.search) params.set("search", filters.search);
      if (filters.include_archived) params.set("include_archived", "true");
      return api.get<Page<Company>>(`/companies?${params.toString()}`);
    },
  });
}

export function useCompanyOptions() {
  return useQuery({
    queryKey: keys.companyOptions,
    queryFn: () => api.get<CompanyOption[]>("/companies/options"),
    staleTime: 60_000,
  });
}

export function useCreateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CompanyInput) => api.post<Company>("/companies", payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
    },
  });
}

export function useJobDescriptions(filters: { search?: string; company_id?: string; include_archived?: boolean; page?: number }) {
  return useQuery({
    queryKey: keys.jobDescriptions(filters),
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(filters.page ?? 1));
      params.set("page_size", "50");
      params.set("sort", "-updated_at");
      if (filters.search) params.set("search", filters.search);
      if (filters.company_id) params.set("company_id", filters.company_id);
      if (filters.include_archived) params.set("include_archived", "true");
      return api.get<Page<JobDescriptionListItem>>(`/job-descriptions?${params.toString()}`);
    },
  });
}

export function useJobOptions(companyId?: string) {
  return useQuery({
    queryKey: keys.jobOptions(companyId),
    queryFn: () =>
      api.get<JobDescriptionListItem[]>(
        `/job-descriptions/options${toQuery({ company_id: companyId })}`,
      ),
    staleTime: 30_000,
  });
}

export function useJobDescription(id: string | null) {
  return useQuery({
    queryKey: keys.jobDescription(id ?? ""),
    queryFn: () => api.get<JobDescription>(`/job-descriptions/${id}`),
    enabled: Boolean(id),
  });
}

function useInvalidateJobDescriptions() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["job-descriptions"] });
    void queryClient.invalidateQueries({ queryKey: ["companies"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };
}

export function useCreateJobDescription() {
  const invalidate = useInvalidateJobDescriptions();
  return useMutation({
    mutationFn: (payload: JobDescriptionInput) =>
      api.post<JobDescription>("/job-descriptions", payload),
    onSuccess: invalidate,
  });
}

export function useCreateJobFromFile() {
  const invalidate = useInvalidateJobDescriptions();
  return useMutation({
    mutationFn: ({ companyId, title, file }: { companyId: string; title: string; file: File }) => {
      const form = new FormData();
      form.set("company_id", companyId);
      form.set("title", title);
      form.set("file", file);
      return api.post<JobDescription>("/job-descriptions/from-file", form);
    },
    onSuccess: invalidate,
  });
}

export function useUpdateJobDescription(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateJobDescriptions();
  return useMutation({
    mutationFn: (payload: Partial<JobDescriptionInput>) =>
      api.patch<JobDescription>(`/job-descriptions/${id}`, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.jobDescription(id), data);
      invalidate();
    },
  });
}

export function useArchiveJobDescription(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateJobDescriptions();
  return useMutation({
    mutationFn: (archived: boolean) =>
      api.post<JobDescription>(`/job-descriptions/${id}/archive${toQuery({ archived })}`),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.jobDescription(id), data);
      invalidate();
    },
  });
}

export function useDeleteJobDescription(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateJobDescriptions();
  return useMutation({
    mutationFn: () => api.delete<void>(`/job-descriptions/${id}`),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: keys.jobDescription(id) });
      invalidate();
    },
  });
}

export function useResumes(filters: { search?: string; include_archived?: boolean } = {}) {
  return useQuery({
    queryKey: keys.resumes(filters),
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page_size", "100");
      if (filters.search) params.set("search", filters.search);
      if (filters.include_archived) params.set("include_archived", "true");
      return api.get<Page<Resume>>(`/resumes?${params.toString()}`);
    },
  });
}

export function useResume(id: string | null) {
  return useQuery({
    queryKey: keys.resume(id ?? ""),
    queryFn: () => api.get<ResumeDetail>(`/resumes/${id}`),
    enabled: Boolean(id),
  });
}

export function useResumeUsage(id: string | null) {
  return useQuery({
    queryKey: keys.resumeUsage(id ?? ""),
    queryFn: () => api.get<ResumeUsage>(`/resumes/${id}/usage`),
    enabled: Boolean(id),
  });
}

function useInvalidateResumes() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["resumes"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["applications"] });
  };
}

export function useCreateResume() {
  const invalidate = useInvalidateResumes();
  return useMutation({
    mutationFn: ({
      name,
      file,
      headline,
      label,
      notes,
    }: {
      name: string;
      file: File;
      headline?: string;
      label?: string;
      notes?: string;
    }) => {
      const form = new FormData();
      form.set("name", name);
      form.set("file", file);
      if (headline) form.set("headline", headline);
      if (label) form.set("label", label);
      if (notes) form.set("notes", notes);
      return api.post<ResumeDetail>("/resumes", form);
    },
    onSuccess: invalidate,
  });
}

export function useAddResumeVersion(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateResumes();
  return useMutation({
    mutationFn: ({
      file,
      label,
      notes,
      makeCurrent,
    }: {
      file: File;
      label?: string;
      notes?: string;
      makeCurrent?: boolean;
    }) => {
      const form = new FormData();
      form.set("file", file);
      if (label) form.set("label", label);
      if (notes) form.set("notes", notes);
      form.set("make_current", String(makeCurrent ?? true));
      return api.post<ResumeDetail>(`/resumes/${id}/versions`, form);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(keys.resume(id), data);
      invalidate();
    },
  });
}

export function useUpdateResumeVersion(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      versionId,
      label,
      notes,
    }: {
      versionId: string;
      label?: string | null;
      notes?: string | null;
    }) => api.patch<ResumeVersion>(`/resumes/${id}/versions/${versionId}`, { label, notes }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.resume(id) });
    },
  });
}

export function useSetCurrentVersion(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateResumes();
  return useMutation({
    mutationFn: (versionId: string) =>
      api.post<ResumeDetail>(`/resumes/${id}/versions/${versionId}/current`),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.resume(id), data);
      invalidate();
    },
  });
}

export function useArchiveResume(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateResumes();
  return useMutation({
    mutationFn: (archived: boolean) =>
      api.post<ResumeDetail>(`/resumes/${id}/archive${toQuery({ archived })}`),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.resume(id), data);
      invalidate();
    },
  });
}

export function useDeleteResume(id: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateResumes();
  return useMutation({
    mutationFn: () => api.delete<void>(`/resumes/${id}`),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: keys.resume(id) });
      invalidate();
    },
  });
}

export interface FlatResumeVersion {
  id: string;
  resumeId: string;
  resumeName: string;
  versionNo: number;
  label: string | null;
  isCurrent: boolean;
}

export function useAllResumeVersions(enabled: boolean) {
  const resumesQuery = useResumes();
  const resumes = resumesQuery.data?.items ?? [];
  const detailQueries = useQueries({
    queries: resumes.map((resume) => ({
      queryKey: keys.resume(resume.id),
      queryFn: () => api.get<ResumeDetail>(`/resumes/${resume.id}`),
      staleTime: 30_000,
      enabled,
    })),
  });

  const versions: FlatResumeVersion[] = [];
  if (enabled) {
    detailQueries.forEach((query, index) => {
      const resume = resumes[index];
      if (!resume || !query.data) return;
      for (const version of query.data.versions) {
        versions.push({
          id: version.id,
          resumeId: resume.id,
          resumeName: resume.name,
          versionNo: version.version_no,
          label: version.label,
          isCurrent: version.is_current,
        });
      }
    });
  }

  const loading = resumesQuery.isLoading || detailQueries.some((query) => query.isLoading);
  return { versions, loading };
}

export function useSessions() {
  return useQuery({
    queryKey: keys.sessions,
    queryFn: () => api.get<SessionView[]>("/auth/sessions"),
  });
}

export function useRevokeSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => api.delete<void>(`/auth/sessions/${sessionId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.sessions });
    },
  });
}

export function useRevokeOtherSessions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ message: string }>("/auth/sessions/revoke-others"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.sessions });
    },
  });
}

export function useMeta() {
  return useQuery({
    queryKey: keys.meta,
    queryFn: () => api.get<MetaResponse>("/auth/meta"),
    staleTime: 5 * 60_000,
  });
}

// --- analyzer --------------------------------------------------------------

export interface AnalysisFilters {
  resumeId?: string;
  jdId?: string;
  applicationId?: string;
  status?: string;
  page?: number;
}

function useInvalidateAnalyses() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["analyses"] });
    void queryClient.invalidateQueries({ queryKey: ["analytics"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["application"] });
  };
}

export function useAnalyses(filters: AnalysisFilters = {}) {
  return useQuery({
    queryKey: keys.analyses(filters),
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(filters.page ?? 1));
      params.set("page_size", "20");
      if (filters.resumeId) params.set("resume_id", filters.resumeId);
      if (filters.jdId) params.set("jd_id", filters.jdId);
      if (filters.applicationId) params.set("application_id", filters.applicationId);
      if (filters.status) params.set("status", filters.status);
      return api.get<Page<AnalysisJob>>(`/analyses?${params.toString()}`);
    },
  });
}

export function useAnalysis(id: string | null) {
  return useQuery({
    queryKey: keys.analysis(id ?? ""),
    queryFn: () => api.get<AnalysisJob>(`/analyses/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });
}

export function useAnalysisStats() {
  return useQuery({
    queryKey: keys.analysisStats,
    queryFn: () => api.get<AnalysisStats>("/analyses/stats"),
  });
}

export function useResumeScores() {
  return useQuery({
    queryKey: keys.resumeScores,
    queryFn: () => api.get<ResumeScore[]>("/analyses/resume-scores"),
  });
}

export function useSubmitAnalysis() {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateAnalyses();
  return useMutation({
    mutationFn: (payload: {
      resume_version_id: string;
      jd_id?: string | null;
      jd_text?: string | null;
    }) => api.post<AnalysisJob>("/analyses", payload),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.analysis(data.id), data);
      invalidate();
    },
  });
}

export function useCancelAnalysis() {
  const invalidate = useInvalidateAnalyses();
  return useMutation({
    mutationFn: (id: string) => api.post<AnalysisJob>(`/analyses/${id}/cancel`),
    onSuccess: invalidate,
  });
}

export function useDeleteAnalysis() {
  const invalidate = useInvalidateAnalyses();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/analyses/${id}`),
    onSuccess: invalidate,
  });
}

// --- tasks -----------------------------------------------------------------

export interface TaskFilters {
  bucket?: "all" | "today" | "overdue" | "upcoming" | "open" | "completed";
  status?: string;
  priority?: string;
  application_id?: string;
  search?: string;
  page?: number;
}

function useInvalidateProductivity() {
  const queryClient = useQueryClient();
  return () => {
    for (const key of ["tasks", "follow-ups", "interviews", "time-entries", "dashboard", "analytics"]) {
      void queryClient.invalidateQueries({ queryKey: [key] });
    }
  };
}

export function useTasks(filters: TaskFilters = {}) {
  return useQuery({
    queryKey: keys.tasks(filters),
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(filters.page ?? 1));
      params.set("page_size", "100");
      params.set("bucket", filters.bucket ?? "open");
      if (filters.status) params.set("status", filters.status);
      if (filters.priority) params.set("priority", filters.priority);
      if (filters.application_id) params.set("application_id", filters.application_id);
      if (filters.search) params.set("search", filters.search);
      return api.get<Page<Task>>(`/tasks?${params.toString()}`);
    },
  });
}

export function useCreateTask() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: (payload: TaskInput) => api.post<Task>("/tasks", payload),
    onSuccess: invalidate,
  });
}

export function useUpdateTask() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<TaskInput> & { status?: string } }) =>
      api.patch<Task>(`/tasks/${id}`, payload),
    onSuccess: invalidate,
  });
}

export function useCompleteTask() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: ({ id, completed }: { id: string; completed: boolean }) =>
      api.post<Task>(`/tasks/${id}/complete`, { completed }),
    onSuccess: invalidate,
  });
}

export function useDeleteTask() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/tasks/${id}`),
    onSuccess: invalidate,
  });
}

// --- follow-ups ------------------------------------------------------------

export function useFollowUps(
  filters: {
    scope?: "all" | "overdue" | "today" | "upcoming" | "open" | "done";
    status?: string;
    application_id?: string;
    page?: number;
  } = {},
) {
  return useQuery({
    queryKey: keys.followUps(filters),
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(filters.page ?? 1));
      params.set("page_size", "100");
      params.set("scope", filters.scope ?? "open");
      if (filters.status) params.set("status", filters.status);
      if (filters.application_id) params.set("application_id", filters.application_id);
      return api.get<Page<FollowUp>>(`/follow-ups?${params.toString()}`);
    },
  });
}

export function useCreateFollowUp() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: (payload: FollowUpInput) => api.post<FollowUp>("/follow-ups", payload),
    onSuccess: invalidate,
  });
}

export function useUpdateFollowUp() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: { due_on?: string; channel?: string; status?: string; notes?: string | null };
    }) => api.patch<FollowUp>(`/follow-ups/${id}`, payload),
    onSuccess: invalidate,
  });
}

export function useDeleteFollowUp() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/follow-ups/${id}`),
    onSuccess: invalidate,
  });
}

// --- interviews ------------------------------------------------------------

export function useInterviews(
  filters: {
    scope?: "all" | "upcoming" | "past";
    application_id?: string;
    outcome?: string;
    page?: number;
  } = {},
) {
  return useQuery({
    queryKey: keys.interviews(filters),
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(filters.page ?? 1));
      params.set("page_size", "100");
      params.set("scope", filters.scope ?? "all");
      if (filters.application_id) params.set("application_id", filters.application_id);
      if (filters.outcome) params.set("outcome", filters.outcome);
      return api.get<Page<Interview>>(`/interviews?${params.toString()}`);
    },
  });
}

export function useCreateInterview() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: (payload: InterviewInput) => api.post<Interview>("/interviews", payload),
    onSuccess: invalidate,
  });
}

export function useUpdateInterview() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: Partial<Omit<InterviewInput, "application_id">> & {
        outcome?: string;
        feedback?: string | null;
      };
    }) => api.patch<Interview>(`/interviews/${id}`, payload),
    onSuccess: invalidate,
  });
}

export function useDeleteInterview() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/interviews/${id}`),
    onSuccess: invalidate,
  });
}

// --- time entries ----------------------------------------------------------

export function useTimeEntries(
  filters: { task_id?: string; date_from?: string; date_to?: string; page?: number } = {},
) {
  return useQuery({
    queryKey: keys.timeEntries(filters),
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(filters.page ?? 1));
      params.set("page_size", "50");
      if (filters.task_id) params.set("task_id", filters.task_id);
      if (filters.date_from) params.set("date_from", filters.date_from);
      if (filters.date_to) params.set("date_to", filters.date_to);
      return api.get<Page<TimeEntry>>(`/time-entries?${params.toString()}`);
    },
  });
}

export function useCreateTimeEntry() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: (payload: TimeEntryInput) => api.post<TimeEntry>("/time-entries", payload),
    onSuccess: invalidate,
  });
}

export function useUpdateTimeEntry() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<TimeEntryInput> }) =>
      api.patch<TimeEntry>(`/time-entries/${id}`, payload),
    onSuccess: invalidate,
  });
}

export function useDeleteTimeEntry() {
  const invalidate = useInvalidateProductivity();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/time-entries/${id}`),
    onSuccess: invalidate,
  });
}

// --- analytics -------------------------------------------------------------

export function useAnalytics() {
  return useQuery({
    queryKey: keys.analytics,
    queryFn: () => api.get<Analytics>("/analytics"),
  });
}
