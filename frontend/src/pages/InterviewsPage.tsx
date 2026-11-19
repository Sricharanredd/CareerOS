import {
  CalendarClock,
  CalendarPlus,
  CheckCircle2,
  Clock,
  ExternalLink,
  MapPin,
  Trash2,
  UserRound,
  Video,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, InlineAlert, LoadingBlock } from "@/components/ui/Feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/Form";
import { Card, PageHeader } from "@/components/ui/Layout";
import { ConfirmDialog, Modal } from "@/components/ui/Overlay";
import { Tabs } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { errorMessage } from "@/lib/api";
import { INTERVIEW_OUTCOME_LABEL, INTERVIEW_TYPE_LABEL } from "@/lib/constants";
import { formatDate, formatDateTime, formatRelative } from "@/lib/format";
import {
  useApplications,
  useCreateInterview,
  useDeleteInterview,
  useInterviews,
  useUpdateInterview,
} from "@/lib/queries";
import type { Interview, InterviewOutcome, InterviewType } from "@/lib/types";

type Scope = "upcoming" | "past" | "all";

const SCOPES: { value: Scope; label: string }[] = [
  { value: "upcoming", label: "Upcoming" },
  { value: "past", label: "Past" },
  { value: "all", label: "All" },
];

const OUTCOME_TONE: Record<InterviewOutcome, "neutral" | "success" | "danger" | "warning"> = {
  pending: "neutral",
  passed: "success",
  failed: "danger",
  cancelled: "warning",
  no_show: "warning",
};

function toLocalInput(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

function defaultSchedule(): string {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(10, 0, 0, 0);
  return toLocalInput(date);
}

function localTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function InterviewCard({
  interview,
  onOutcome,
  onDelete,
}: {
  interview: Interview;
  onOutcome: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-fg">Round {interview.round_no}</span>
            <Badge tone="accent">{INTERVIEW_TYPE_LABEL[interview.type]}</Badge>
            <Badge tone={OUTCOME_TONE[interview.outcome]}>
              {INTERVIEW_OUTCOME_LABEL[interview.outcome]}
            </Badge>
          </div>
          <p className="mt-1.5 text-sm text-fg">
            {interview.application.title}
            <span className="text-muted"> · {interview.application.company_name}</span>
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            <span className="inline-flex items-center gap-1">
              <CalendarClock className="h-3.5 w-3.5" aria-hidden />
              {formatDateTime(interview.scheduled_at)}
            </span>
            <span className="text-subdued">{interview.timezone}</span>
            <span className="text-subdued">· {formatRelative(interview.scheduled_at)}</span>
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-subdued">
            {interview.interviewer && (
              <span className="inline-flex items-center gap-1">
                <UserRound className="h-3.5 w-3.5" aria-hidden />
                {interview.interviewer}
              </span>
            )}
            {interview.location && (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5" aria-hidden />
                {interview.location}
              </span>
            )}
            {interview.link && (
              <a
                href={interview.link}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-accent hover:underline"
              >
                <Video className="h-3.5 w-3.5" aria-hidden />
                Join link
                <ExternalLink className="h-3 w-3" aria-hidden />
              </a>
            )}
          </div>
          {interview.prep_notes && (
            <p className="mt-2 rounded-lg bg-surface-2/60 px-3 py-2 text-xs leading-relaxed text-muted">
              {interview.prep_notes}
            </p>
          )}
          {interview.feedback && (
            <p className="mt-2 border-l-2 border-line-strong pl-2.5 text-xs leading-relaxed text-muted">
              <span className="font-medium text-fg">Feedback:</span> {interview.feedback}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button size="sm" variant="secondary" onClick={onOutcome}>
            {interview.outcome === "pending" ? "Record outcome" : "Edit outcome"}
          </Button>
          <button
            type="button"
            onClick={onDelete}
            aria-label="Delete interview"
            className="flex h-8 w-8 items-center justify-center rounded-md text-subdued hover:bg-danger-soft hover:text-danger"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      </div>
    </li>
  );
}

export function InterviewsPage() {
  const toast = useToast();
  const [scope, setScope] = useState<Scope>("upcoming");
  const [applicationFilter, setApplicationFilter] = useState("");
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [form, setForm] = useState({
    application_id: "",
    round_no: "",
    type: "video" as InterviewType,
    scheduled_at: defaultSchedule(),
    timezone: localTimezone(),
    interviewer: "",
    location: "",
    link: "",
    prep_notes: "",
  });
  const [outcomeTarget, setOutcomeTarget] = useState<Interview | null>(null);
  const [outcome, setOutcome] = useState<InterviewOutcome>("pending");
  const [feedback, setFeedback] = useState("");
  const [outcomeError, setOutcomeError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Interview | null>(null);

  const interviews = useInterviews({
    scope,
    application_id: applicationFilter || undefined,
  });
  const applications = useApplications({ page: 1, page_size: 100 });
  const createInterview = useCreateInterview();
  const updateInterview = useUpdateInterview();
  const deleteInterview = useDeleteInterview();

  const applicationOptions = applications.data?.items ?? [];

  const upcomingCount = useMemo(
    () =>
      scope === "upcoming"
        ? interviews.data?.total
        : undefined,
    [scope, interviews.data],
  );

  function openSchedule() {
    setForm((current) => ({
      ...current,
      application_id: applicationFilter || current.application_id || "",
      scheduled_at: defaultSchedule(),
      timezone: localTimezone(),
    }));
    setScheduleError(null);
    setScheduleOpen(true);
  }

  function submitSchedule() {
    if (!form.application_id) {
      setScheduleError("Choose the application this interview belongs to.");
      return;
    }
    if (!form.scheduled_at) {
      setScheduleError("Choose the date and time.");
      return;
    }
    setScheduleError(null);
    createInterview.mutate(
      {
        application_id: form.application_id,
        round_no: form.round_no ? Number(form.round_no) : null,
        type: form.type,
        scheduled_at: new Date(form.scheduled_at).toISOString(),
        timezone: form.timezone || "UTC",
        interviewer: form.interviewer.trim() || null,
        location: form.location.trim() || null,
        link: form.link.trim() || null,
        prep_notes: form.prep_notes.trim() || null,
      },
      {
        onSuccess: () => {
          setScheduleOpen(false);
          toast.success("Interview scheduled");
        },
        onError: (error) => setScheduleError(errorMessage(error)),
      },
    );
  }

  function openOutcome(interview: Interview) {
    setOutcomeTarget(interview);
    setOutcome(interview.outcome);
    setFeedback(interview.feedback ?? "");
    setOutcomeError(null);
  }

  function submitOutcome() {
    if (!outcomeTarget) return;
    updateInterview.mutate(
      {
        id: outcomeTarget.id,
        payload: { outcome, feedback: feedback.trim() || null },
      },
      {
        onSuccess: () => {
          setOutcomeTarget(null);
          toast.success("Outcome saved");
        },
        onError: (error) => setOutcomeError(errorMessage(error)),
      },
    );
  }

  const items = interviews.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Interviews"
        subtitle="Every conversation on the schedule, with rounds, prep notes and honest outcomes."
        actions={
          <>
            {upcomingCount != null && (
              <span className="hidden items-center gap-1.5 text-xs text-muted sm:inline-flex">
                <Clock className="h-3.5 w-3.5" aria-hidden />
                {upcomingCount} upcoming
              </span>
            )}
            <Button
              variant="primary"
              icon={<CalendarPlus className="h-4 w-4" />}
              onClick={openSchedule}
              disabled={applicationOptions.length === 0}
            >
              Schedule interview
            </Button>
          </>
        }
      />

      {applications.data && applicationOptions.length === 0 && (
        <InlineAlert tone="warning" title="No active applications">
          Interviews attach to an active application.{" "}
          <Link to="/applications?new=1" className="underline">
            Log an application
          </Link>{" "}
          first, then come back to schedule the conversation.
        </InlineAlert>
      )}

      <Card className="overflow-hidden">
        <div className="flex flex-col gap-3 px-4 pt-3 sm:flex-row sm:items-center sm:justify-between">
          <Tabs<Scope>
            items={SCOPES.map((item) => ({ value: item.value, label: item.label }))}
            value={scope}
            onChange={setScope}
            className="border-0"
          />
          <Field label="Application" htmlFor="interview-app-filter" className="w-full sm:w-64">
            <Select
              id="interview-app-filter"
              value={applicationFilter}
              onChange={(event) => setApplicationFilter(event.target.value)}
              className="h-8 text-[13px]"
            >
              <option value="">All applications</option>
              {applicationOptions.map((application) => (
                <option key={application.id} value={application.id}>
                  {application.title} — {application.company.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="mt-2 border-t border-line p-3">
          {interviews.isLoading ? (
            <LoadingBlock label="Loading interviews…" />
          ) : interviews.isError ? (
            <ErrorState
              message="Interviews could not be loaded."
              onRetry={() => void interviews.refetch()}
            />
          ) : items.length === 0 ? (
            <EmptyState
              className="py-14"
              icon={<CalendarClock className="h-5 w-5" />}
              title={
                scope === "upcoming"
                  ? "No interviews scheduled"
                  : scope === "past"
                    ? "No past interviews"
                    : "No interviews yet"
              }
              description={
                scope === "upcoming"
                  ? "Schedule the next conversation and it will appear here with its prep notes."
                  : "Interviews you record will show up in this view."
              }
              action={
                applicationOptions.length > 0 ? (
                  <Button variant="secondary" size="sm" onClick={openSchedule}>
                    Schedule interview
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <ul className="space-y-3">
              {items.map((interview) => (
                <InterviewCard
                  key={interview.id}
                  interview={interview}
                  onOutcome={() => openOutcome(interview)}
                  onDelete={() => setDeleteTarget(interview)}
                />
              ))}
            </ul>
          )}
        </div>
      </Card>

      <Modal
        open={scheduleOpen}
        onClose={() => setScheduleOpen(false)}
        title="Schedule interview"
        description="The round number is assigned automatically unless you set one."
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setScheduleOpen(false)} disabled={createInterview.isPending}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={submitSchedule}
              loading={createInterview.isPending}
              icon={<CalendarPlus className="h-4 w-4" />}
            >
              Schedule
            </Button>
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Application" htmlFor="interview-application" required className="sm:col-span-2">
            <Select
              id="interview-application"
              value={form.application_id}
              onChange={(event) => setForm({ ...form, application_id: event.target.value })}
            >
              <option value="">Choose an application…</option>
              {applicationOptions.map((application) => (
                <option key={application.id} value={application.id}>
                  {application.title} — {application.company.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Date and time" htmlFor="interview-when" required>
            <Input
              id="interview-when"
              type="datetime-local"
              value={form.scheduled_at}
              onChange={(event) => setForm({ ...form, scheduled_at: event.target.value })}
            />
          </Field>
          <Field label="Timezone" htmlFor="interview-timezone" hint="IANA name, for example Asia/Kolkata.">
            <Input
              id="interview-timezone"
              value={form.timezone}
              onChange={(event) => setForm({ ...form, timezone: event.target.value })}
              maxLength={64}
            />
          </Field>
          <Field label="Type" htmlFor="interview-type">
            <Select
              id="interview-type"
              value={form.type}
              onChange={(event) => setForm({ ...form, type: event.target.value as InterviewType })}
            >
              {(Object.keys(INTERVIEW_TYPE_LABEL) as InterviewType[]).map((type) => (
                <option key={type} value={type}>
                  {INTERVIEW_TYPE_LABEL[type]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Round" htmlFor="interview-round" hint="Leave blank to number it automatically.">
            <Input
              id="interview-round"
              type="number"
              min={1}
              max={99}
              value={form.round_no}
              onChange={(event) => setForm({ ...form, round_no: event.target.value })}
              placeholder="Auto"
            />
          </Field>
          <Field label="Interviewer" htmlFor="interview-interviewer">
            <Input
              id="interview-interviewer"
              value={form.interviewer}
              onChange={(event) => setForm({ ...form, interviewer: event.target.value })}
              maxLength={200}
            />
          </Field>
          <Field label="Location" htmlFor="interview-location" hint="Office, address, or “Remote”.">
            <Input
              id="interview-location"
              value={form.location}
              onChange={(event) => setForm({ ...form, location: event.target.value })}
              maxLength={300}
            />
          </Field>
          <Field label="Meeting link" htmlFor="interview-link" className="sm:col-span-2">
            <Input
              id="interview-link"
              type="url"
              value={form.link}
              onChange={(event) => setForm({ ...form, link: event.target.value })}
              placeholder="https://"
              maxLength={1000}
            />
          </Field>
          <Field label="Prep notes" htmlFor="interview-prep" className="sm:col-span-2">
            <Textarea
              id="interview-prep"
              rows={3}
              value={form.prep_notes}
              onChange={(event) => setForm({ ...form, prep_notes: event.target.value })}
              placeholder="Topics to revise, questions to ask, people to reference."
            />
          </Field>
        </div>
        {scheduleError && (
          <div className="mt-4">
            <InlineAlert title="Could not schedule">{scheduleError}</InlineAlert>
          </div>
        )}
      </Modal>

      <Modal
        open={Boolean(outcomeTarget)}
        onClose={() => setOutcomeTarget(null)}
        title="Interview outcome"
        description={
          outcomeTarget
            ? `Round ${outcomeTarget.round_no} · ${outcomeTarget.application.title}`
            : undefined
        }
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOutcomeTarget(null)} disabled={updateInterview.isPending}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={submitOutcome}
              loading={updateInterview.isPending}
              icon={<CheckCircle2 className="h-4 w-4" />}
            >
              Save outcome
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Outcome" htmlFor="outcome-select">
            <Select
              id="outcome-select"
              value={outcome}
              onChange={(event) => setOutcome(event.target.value as InterviewOutcome)}
            >
              {(Object.keys(INTERVIEW_OUTCOME_LABEL) as InterviewOutcome[]).map((value) => (
                <option key={value} value={value}>
                  {INTERVIEW_OUTCOME_LABEL[value]}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Feedback"
            htmlFor="outcome-feedback"
            hint="What was asked, what went well, and what to prepare next time."
          >
            <Textarea
              id="outcome-feedback"
              rows={4}
              value={feedback}
              onChange={(event) => setFeedback(event.target.value)}
              maxLength={20_000}
            />
          </Field>
          <p className="text-[11px] leading-relaxed text-subdued">
            {outcomeTarget && (
              <>
                Scheduled {formatDate(outcomeTarget.scheduled_at)} ·{" "}
              </>
            )}
            Outcomes feed the interview conversion metric on analytics.
          </p>
          {outcomeError && <InlineAlert title="Could not save">{outcomeError}</InlineAlert>}
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteInterview.mutate(deleteTarget.id, {
            onSuccess: () => {
              setDeleteTarget(null);
              toast.success("Interview deleted");
            },
            onError: (error) => {
              toast.error(errorMessage(error));
              setDeleteTarget(null);
            },
          });
        }}
        title="Delete this interview?"
        description={
          deleteTarget
            ? `Round ${deleteTarget.round_no} with ${deleteTarget.application.company_name} will be removed from the schedule and analytics.`
            : undefined
        }
        confirmLabel="Delete interview"
        loading={deleteInterview.isPending}
      />
    </div>
  );
}
