import clsx from "clsx";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileSearch,
  History,
  Info,
  Lightbulb,
  Loader2,
  Sparkles,
  Target,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, InlineAlert, LoadingBlock } from "@/components/ui/Feedback";
import { Field, Select, Textarea } from "@/components/ui/Form";
import { Card, PageHeader, SectionTitle } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { errorMessage } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import {
  useAnalyses,
  useAnalysis,
  useAnalysisStats,
  useAllResumeVersions,
  useDeleteAnalysis,
  useJobOptions,
  useResumeScores,
  useSubmitAnalysis,
} from "@/lib/queries";
import type { AnalysisJob, AnalysisStatus, Finding, FindingKind } from "@/lib/types";
import { useQueryClient } from "@tanstack/react-query";

const STATUS_LABEL: Record<AnalysisStatus, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
  stale: "Superseded",
};

const STATUS_TONE: Record<AnalysisStatus, "neutral" | "accent" | "teal" | "success" | "danger" | "warning"> = {
  queued: "neutral",
  running: "accent",
  succeeded: "success",
  failed: "danger",
  cancelled: "neutral",
  stale: "warning",
};

const KIND_LABEL: Record<FindingKind, string> = {
  resume_evidence: "Resume evidence",
  jd_requirement: "JD requirement",
  inferred_recommendation: "Inferred recommendation",
};

const KIND_TONE: Record<FindingKind, "teal" | "accent" | "warning"> = {
  resume_evidence: "teal",
  jd_requirement: "accent",
  inferred_recommendation: "warning",
};

const KIND_ORDER: FindingKind[] = ["resume_evidence", "jd_requirement", "inferred_recommendation"];

const CATEGORY_LABEL: Record<string, string> = {
  matched_skill: "Matched skill",
  missing_skill: "Missing skill",
  weak_skill: "Weak evidence",
  experience: "Experience",
  keyword_gap: "Keyword gap",
  suggestion: "Suggestion",
};

function AnalysisStatusBadge({ status }: { status: AnalysisStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>;
}

function ScoreDial({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <div className="flex items-center gap-4">
      <div
        className="relative flex h-24 w-24 shrink-0 items-center justify-center rounded-full"
        style={{
          background: `conic-gradient(var(--color-accent) ${clamped * 3.6}deg, var(--color-surface-2) 0deg)`,
        }}
        role="img"
        aria-label={`Alignment score ${score} out of 100`}
      >
        <div className="flex h-[76px] w-[76px] flex-col items-center justify-center rounded-full bg-surface">
          <span className="text-2xl font-semibold tracking-tight text-fg tabular-nums">{score}</span>
          <span className="text-[10px] font-medium uppercase tracking-wide text-subdued">/ 100</span>
        </div>
      </div>
      <div>
        <p className="text-[13px] font-medium text-muted">Resume–JD alignment</p>
        <p className="mt-1 max-w-xs text-xs leading-relaxed text-subdued">
          An alignment indicator between 0 and 100. It measures overlap with this job description
          only — it is never a hiring probability or prediction.
        </p>
      </div>
    </div>
  );
}

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <li className="rounded-xl border border-line bg-surface-2/40 p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={KIND_TONE[finding.kind]}>{KIND_LABEL[finding.kind]}</Badge>
        <span className="text-[11px] uppercase tracking-wide text-subdued">
          {CATEGORY_LABEL[finding.category] ?? finding.category}
        </span>
      </div>
      <p className="mt-2 text-sm font-medium text-fg">{finding.label}</p>
      <p className="mt-1 text-[13px] leading-relaxed text-muted">{finding.detail}</p>
      {finding.evidence && (
        <blockquote className="mt-2 border-l-2 border-line-strong pl-2.5 text-[12px] leading-relaxed text-subdued italic">
          “{finding.evidence}”
        </blockquote>
      )}
    </li>
  );
}

function ResultPanel({ job }: { job: AnalysisJob }) {
  if (job.status === "queued" || job.status === "running") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <Loader2 className="h-6 w-6 animate-spin text-accent" aria-hidden />
        <div>
          <p className="text-sm font-medium text-fg">
            {job.status === "queued" ? "Analysis queued" : "Comparing your resume…"}
          </p>
          <p className="mt-1 max-w-sm text-sm text-muted">
            This page refreshes every couple of seconds. You can leave and come back — the job keeps
            its place in the history list.
          </p>
        </div>
      </div>
    );
  }

  if (job.status === "failed" || job.status === "cancelled" || job.status === "stale") {
    const notConfigured = job.error_code === "ai_not_configured";
    return (
      <InlineAlert
        tone={job.status === "stale" ? "warning" : "danger"}
        title={
          notConfigured
            ? "AI provider not configured"
            : job.status === "stale"
              ? "This analysis was superseded"
              : job.status === "cancelled"
                ? "Analysis cancelled"
                : "Analysis failed"
        }
      >
        <p className="leading-relaxed">
          {job.error_message ??
            (job.status === "stale"
              ? "A newer submission replaced this job. Open the newer analysis from the history."
              : "The provider did not return a usable result.")}
        </p>
        {notConfigured && (
          <p className="mt-2 leading-relaxed">
            Set <code className="rounded bg-danger-soft px-1 py-0.5 text-[12px]">GEMINI_API_KEY</code>{" "}
            in the backend <code className="rounded bg-danger-soft px-1 py-0.5 text-[12px]">.env</code>{" "}
            file and restart the API. The analysis is stored, so you can submit it again once the key
            is present.
          </p>
        )}
      </InlineAlert>
    );
  }

  if (!job.result) {
    return <ErrorState message="The job has no result stored." />;
  }

  const grouped = KIND_ORDER.map((kind) => ({
    kind,
    findings: job.result!.findings.filter((finding) => finding.kind === kind),
  })).filter((group) => group.findings.length > 0);

  return (
    <div className="space-y-5">
      <ScoreDial score={job.result.score} />
      <div className="rounded-xl border border-line bg-surface-2/40 p-4">
        <p className="text-[13px] font-medium text-fg">{job.result.summary}</p>
        <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{job.result.alignment_explanation}</p>
      </div>
      <div className="space-y-4">
        {grouped.map((group) => (
          <div key={group.kind}>
            <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-subdued">
              {group.kind === "resume_evidence" ? (
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
              ) : group.kind === "jd_requirement" ? (
                <Target className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <Lightbulb className="h-3.5 w-3.5" aria-hidden />
              )}
              {KIND_LABEL[group.kind]}
            </p>
            <ul className="space-y-2.5">
              {group.findings.map((finding, index) => (
                <FindingCard key={`${group.kind}-${index}`} finding={finding} />
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="text-[11px] leading-relaxed text-subdued">
        Provider {job.provider} · model {job.model} · prompt {job.prompt_version}
        {job.finished_at ? ` · finished ${formatRelative(job.finished_at)}` : ""}
      </p>
    </div>
  );
}

function HistoryRow({
  job,
  active,
  onSelect,
  onDelete,
}: {
  job: AnalysisJob;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const target = job.job_description
    ? `${job.job_description.title}${job.job_description.company_name ? ` · ${job.job_description.company_name}` : ""}`
    : "Pasted job description";
  return (
    <li>
      <div
        className={clsx(
          "flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors",
          active ? "border-accent/40 bg-accent-soft/40" : "border-line bg-surface hover:bg-surface-2",
        )}
      >
        <button
          type="button"
          onClick={onSelect}
          className="flex min-w-0 flex-1 items-center gap-3 text-left focus-visible:outline-none"
        >
          <span
            className={clsx(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-xs font-semibold tabular-nums",
              job.result ? "bg-teal-soft text-teal" : "bg-surface-2 text-subdued",
            )}
          >
            {job.result ? job.result.score : <FileSearch className="h-4 w-4" aria-hidden />}
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2">
              <span className="truncate text-sm font-medium text-fg">
                {job.resume_version.resume_name}
              </span>
              <span className="shrink-0 text-[11px] text-subdued">v{job.resume_version.version_no}</span>
              <AnalysisStatusBadge status={job.status} />
            </span>
            <span className="mt-0.5 block truncate text-xs text-muted">{target}</span>
          </span>
          <span className="shrink-0 text-[11px] text-subdued">{formatRelative(job.created_at)}</span>
        </button>
        <button
          type="button"
          onClick={onDelete}
          aria-label="Delete analysis"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-subdued hover:bg-danger-soft hover:text-danger"
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden />
        </button>
      </div>
    </li>
  );
}

type JdMode = "saved" | "pasted";

export function AnalyzerPage() {
  const queryClient = useQueryClient();
  const [resumeVersionId, setResumeVersionId] = useState("");
  const [jdMode, setJdMode] = useState<JdMode>("saved");
  const [jdId, setJdId] = useState("");
  const [jdText, setJdText] = useState("");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AnalysisJob | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { versions, loading: versionsLoading } = useAllResumeVersions(true);
  const jobsQuery = useJobOptions();
  const history = useAnalyses();
  const stats = useAnalysisStats();
  const scores = useResumeScores();
  const activeJob = useAnalysis(activeJobId);
  const submit = useSubmitAnalysis();
  const remove = useDeleteAnalysis();

  const resumeGroups = useMemo(() => {
    const groups = new Map<string, { name: string; versions: typeof versions }>();
    for (const version of versions) {
      const entry = groups.get(version.resumeId);
      if (entry) entry.versions.push(version);
      else groups.set(version.resumeId, { name: version.resumeName, versions: [version] });
    }
    return [...groups.values()];
  }, [versions]);

  const jobs = jobsQuery.data ?? [];
  const pastedLongEnough = jdText.trim().length >= 200;

  // The detail endpoint stops polling once the job settles; refresh the list then.
  useEffect(() => {
    const status = activeJob.data?.status;
    if (status && status !== "queued" && status !== "running") {
      void queryClient.invalidateQueries({ queryKey: ["analyses"] });
    }
  }, [activeJob.data?.status, queryClient]);

  // Drop stale ids (deleted or filtered away) from the detail pane.
  useEffect(() => {
    if (resumeVersionId || versions.length === 0) return;
    if (versions.length > 0) setResumeVersionId(versions[0].id);
  }, [versions, resumeVersionId]);

  const canSubmit =
    Boolean(resumeVersionId) &&
    (jdMode === "saved" ? Boolean(jdId) : pastedLongEnough) &&
    !submit.isPending;

  function handleSubmit() {
    if (!canSubmit) return;
    setSubmitError(null);
    submit.mutate(
      {
        resume_version_id: resumeVersionId,
        jd_id: jdMode === "saved" ? jdId : null,
        jd_text: jdMode === "pasted" ? jdText.trim() : null,
      },
      {
        onSuccess: (job) => {
          setActiveJobId(job.id);
          setSubmitError(null);
        },
        onError: (error) => setSubmitError(errorMessage(error)),
      },
    );
  }

  const hasResumes = versions.length > 0;
  const selectedJob = activeJobId ? activeJob.data : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Resume analyzer"
        subtitle="Compare one resume version with one job description. Every finding is tagged by where it came from."
        actions={
          stats.data && stats.data.total > 0 ? (
            <div className="flex items-center gap-4 rounded-lg border border-line bg-surface px-3 py-2 text-xs text-muted">
              <span>
                <span className="font-semibold text-fg tabular-nums">{stats.data.total}</span> runs
              </span>
              <span>
                <span className="font-semibold text-fg tabular-nums">
                  {stats.data.average_score != null ? stats.data.average_score.toFixed(1) : "—"}
                </span>{" "}
                average
              </span>
            </div>
          ) : undefined
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)] lg:items-start">
        <div className="space-y-4">
          <Card className="p-5">
            <SectionTitle
              title="Run a comparison"
              hint="Pick the resume version and the job you are targeting."
            />
            {versionsLoading ? (
              <LoadingBlock label="Loading resumes…" />
            ) : !hasResumes ? (
              <EmptyState
                className="py-8"
                icon={<Upload className="h-5 w-5" />}
                title="Upload a resume first"
                description="The analyzer reads your uploaded resume text. Add a resume to get started."
                action={
                  <Link to="/resumes">
                    <Button variant="primary" size="sm">
                      Go to resumes
                    </Button>
                  </Link>
                }
              />
            ) : (
              <div className="mt-4 space-y-4">
                <Field label="Resume version" htmlFor="analysis-resume">
                  <Select
                    id="analysis-resume"
                    value={resumeVersionId}
                    onChange={(event) => setResumeVersionId(event.target.value)}
                  >
                    {resumeGroups.map((group) => (
                      <optgroup key={group.name} label={group.name}>
                        {group.versions.map((version) => (
                          <option key={version.id} value={version.id}>
                            {group.name} · v{version.versionNo}
                            {version.label ? ` — ${version.label}` : ""}
                            {version.isCurrent ? " (current)" : ""}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </Select>
                </Field>

                <div>
                  <p className="mb-1.5 text-sm font-medium text-fg">Job description</p>
                  <Tabs<JdMode>
                    items={[
                      { value: "saved", label: "Saved job" },
                      { value: "pasted", label: "Paste text" },
                    ]}
                    value={jdMode}
                    onChange={(mode) => setJdMode(mode)}
                  />
                  <div className="pt-4">
                    {jdMode === "saved" ? (
                      jobs.length === 0 ? (
                        <p className="text-sm text-muted">
                          No saved job descriptions yet.{" "}
                          <Link to="/job-descriptions" className="text-accent hover:underline">
                            Add one
                          </Link>{" "}
                          or paste the text instead.
                        </p>
                      ) : (
                        <Field label="Saved job description" htmlFor="analysis-jd">
                          <Select
                            id="analysis-jd"
                            value={jdId}
                            onChange={(event) => setJdId(event.target.value)}
                          >
                            <option value="">Choose a job description…</option>
                            {jobs.map((job) => (
                              <option key={job.id} value={job.id}>
                                {job.title} — {job.company.name}
                              </option>
                            ))}
                          </Select>
                        </Field>
                      )
                    ) : (
                      <Field
                        label="Paste the job description"
                        htmlFor="analysis-jd-text"
                        hint={`${jdText.trim().length} characters${
                          pastedLongEnough ? "" : " · at least 200 needed"
                        }`}
                      >
                        <Textarea
                          id="analysis-jd-text"
                          rows={8}
                          value={jdText}
                          onChange={(event) => setJdText(event.target.value)}
                          placeholder="Paste the full job description, including requirements and responsibilities."
                        />
                      </Field>
                    )}
                  </div>
                </div>

                {submitError && <InlineAlert title="Could not submit">{submitError}</InlineAlert>}

                <Button
                  variant="primary"
                  className="w-full"
                  onClick={handleSubmit}
                  disabled={!canSubmit}
                  loading={submit.isPending}
                  icon={<Sparkles className="h-4 w-4" />}
                >
                  Analyze alignment
                </Button>
                <p className="flex gap-1.5 text-[11px] leading-relaxed text-subdued">
                  <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                  Results are stored so you can revisit them. Re-running the same resume + job
                  returns the existing result instead of duplicating it.
                </p>
              </div>
            )}
          </Card>

          {scores.data && scores.data.length > 0 && (
            <Card className="p-5">
              <SectionTitle title="Resume alignment" hint="Average across every completed analysis." />
              <ul className="mt-4 space-y-2.5">
                {scores.data.map((score) => (
                  <li key={score.resume_version_id} className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-medium text-fg">
                        {score.resume_name} · v{score.version_no}
                      </p>
                      <p className="text-[11px] text-subdued">
                        {score.label ?? "No label"} ·{" "}
                        {score.analyses === 1 ? "1 analysis" : `${score.analyses} analyses`}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
                        <div
                          className="h-full rounded-full bg-teal"
                          style={{ width: `${Math.max(0, Math.min(100, score.average_score))}%` }}
                        />
                      </div>
                      <span className="w-8 text-right text-sm font-semibold text-fg tabular-nums">
                        {score.average_score.toFixed(0)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card className="p-5">
            <SectionTitle
              title={selectedJob ? "Alignment result" : "Result"}
              hint={
                selectedJob
                  ? `${selectedJob.resume_version.resume_name} v${selectedJob.resume_version.version_no}`
                  : "Submit a comparison to see evidence-tagged findings here."
              }
              action={selectedJob ? <AnalysisStatusBadge status={selectedJob.status} /> : undefined}
            />
            <div className="mt-4">
              {!activeJobId ? (
                <EmptyState
                  className="py-16"
                  icon={<FileSearch className="h-5 w-5" />}
                  title="No analysis selected"
                  description="Pick a resume and a job description, then run an analysis. Results and findings appear here."
                />
              ) : activeJob.isLoading ? (
                <LoadingBlock label="Loading analysis…" />
              ) : activeJob.isError ? (
                <ErrorState
                  message="This analysis could not be loaded."
                  onRetry={() => void activeJob.refetch()}
                />
              ) : selectedJob ? (
                <ResultPanel job={selectedJob} />
              ) : null}
            </div>
          </Card>

          <Card className="p-5">
            <SectionTitle
              title="History"
              hint="Every comparison, newest first."
              action={
                stats.data ? (
                  <span className="text-[11px] text-subdued">
                    {stats.data.succeeded} succeeded · {stats.data.failed} failed
                  </span>
                ) : undefined
              }
            />
            <div className="mt-4">
              {history.isLoading ? (
                <LoadingBlock label="Loading history…" />
              ) : history.isError ? (
                <ErrorState
                  message="History could not be loaded."
                  onRetry={() => void history.refetch()}
                />
              ) : (history.data?.items.length ?? 0) === 0 ? (
                <EmptyState
                  className="py-10"
                  icon={<History className="h-5 w-5" />}
                  title="No analyses yet"
                  description="Your completed and in-progress comparisons will be listed here."
                />
              ) : (
                <ul className="space-y-2">
                  {history.data!.items.map((job) => (
                    <HistoryRow
                      key={job.id}
                      job={job}
                      active={job.id === activeJobId}
                      onSelect={() => setActiveJobId(job.id)}
                      onDelete={() => setDeleteTarget(job)}
                    />
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </div>
      </div>

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="fixed inset-0 bg-[#0a0e16]/55 backdrop-blur-[2px]"
            onClick={() => setDeleteTarget(null)}
            aria-hidden
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Delete analysis"
            className="relative z-10 w-full max-w-sm rounded-2xl border border-line bg-surface p-6 shadow-pop"
          >
            <div className="flex items-center gap-2 text-danger">
              <AlertTriangle className="h-4 w-4" aria-hidden />
              <h2 className="text-base font-semibold">Delete this analysis?</h2>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              The stored result and findings for{" "}
              <span className="font-medium text-fg">
                {deleteTarget.resume_version.resume_name} v{deleteTarget.resume_version.version_no}
              </span>{" "}
              will be removed. This cannot be undone.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setDeleteTarget(null)} disabled={remove.isPending}>
                Cancel
              </Button>
              <Button
                variant="danger"
                loading={remove.isPending}
                onClick={() => {
                  remove.mutate(deleteTarget.id, {
                    onSuccess: () => {
                      if (activeJobId === deleteTarget.id) setActiveJobId(null);
                      setDeleteTarget(null);
                    },
                  });
                }}
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 rounded-xl border border-line bg-surface px-4 py-3 text-xs text-muted">
        <ArrowRight className="h-3.5 w-3.5 text-accent" aria-hidden />
        <span>
          <span className="font-medium text-fg">How to read this:</span> resume evidence quotes your
          document, JD requirements quote the posting, and recommendations are inferred advice — never
          claims about your experience.
        </span>
      </div>
    </div>
  );
}
