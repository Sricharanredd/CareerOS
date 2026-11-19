import clsx from "clsx";
import {
  Archive,
  ArchiveRestore,
  ArrowRight,
  Building2,
  CalendarClock,
  Check,
  ExternalLink,
  FileText,
  Link2,
  MailPlus,
  MapPin,
  Pencil,
  PlusCircle,
  Send,
  SkipForward,
  StickyNote,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, InlineAlert, LoadingBlock } from "@/components/ui/Feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/Form";
import { ConfirmDialog, Drawer } from "@/components/ui/Overlay";
import { Tabs } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import {
  ALLOWED_TRANSITIONS,
  EMPLOYMENT_TYPE_LABEL,
  FOLLOW_UP_CHANNEL_LABEL,
  FOLLOW_UP_STATUS_LABEL,
  STATUS_LABEL,
  WORK_MODE_LABEL,
} from "@/lib/constants";
import { errorMessage } from "@/lib/api";
import {
  formatDate,
  formatDateTime,
  formatRelative,
  formatSalaryRange,
  labelize,
} from "@/lib/format";
import {
  useAddNote,
  useApplication,
  useArchiveApplication,
  useChangeStatus,
  useCreateFollowUp,
  useDeleteApplication,
  useDeleteFollowUp,
  useFollowUps,
  useUpdateFollowUp,
} from "@/lib/queries";
import type { ApplicationStatus, FollowUp, FollowUpChannel, TimelineEvent } from "@/lib/types";

const EVENT_ICON: Record<string, React.ReactNode> = {
  created: <PlusCircle className="h-3.5 w-3.5" />,
  status_change: <ArrowRight className="h-3.5 w-3.5" />,
  updated: <Pencil className="h-3.5 w-3.5" />,
  note: <StickyNote className="h-3.5 w-3.5" />,
  archived: <Archive className="h-3.5 w-3.5" />,
};

function eventText(event: TimelineEvent): string {
  switch (event.type) {
    case "created":
      return `Application created${event.to_status ? ` as ${labelize(event.to_status)}` : ""}`;
    case "status_change":
      return `Moved from ${labelize(event.from_status)} to ${labelize(event.to_status)}`;
    case "updated": {
      const fields = (event.payload?.fields as string[] | undefined) ?? [];
      return fields.length
        ? `Updated ${fields.map((field) => labelize(field)).join(", ")}`
        : "Application updated";
    }
    case "note":
      return (event.payload?.note as string | undefined) ?? "Note added";
    case "archived":
      return "Application archived";
    default:
      return labelize(event.type);
  }
}

function Detail({
  label,
  children,
  icon,
}: {
  label: string;
  children: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div>
      <dt className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-subdued">
        {icon}
        {label}
      </dt>
      <dd className="mt-1 text-sm text-fg">{children || <span className="text-subdued">—</span>}</dd>
    </div>
  );
}

function defaultFollowUpDate(): string {
  return new Date(Date.now() + 3 * 86_400_000).toISOString().slice(0, 10);
}

export function ApplicationDrawer({
  applicationId,
  onClose,
  onEdit,
}: {
  applicationId: string | null;
  onClose: () => void;
  onEdit: () => void;
}) {
  const query = useApplication(applicationId);
  const navigate = useNavigate();
  const toast = useToast();
  const [tab, setTab] = useState<"overview" | "follow-ups" | "timeline">("overview");
  const [note, setNote] = useState("");
  const [target, setTarget] = useState<ApplicationStatus | "">("");
  const [moveNote, setMoveNote] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [followUpDue, setFollowUpDue] = useState(defaultFollowUpDate);
  const [followUpChannel, setFollowUpChannel] = useState<FollowUpChannel>("email");
  const [followUpNotes, setFollowUpNotes] = useState("");

  const addNote = useAddNote(applicationId ?? "");
  const changeStatus = useChangeStatus(applicationId ?? "");
  const archive = useArchiveApplication(applicationId ?? "");
  const remove = useDeleteApplication(applicationId ?? "");
  const followUps = useFollowUps({ application_id: applicationId ?? undefined, scope: "all" });
  const createFollowUp = useCreateFollowUp();
  const updateFollowUp = useUpdateFollowUp();
  const deleteFollowUp = useDeleteFollowUp();

  useEffect(() => {
    setTab("overview");
    setNote("");
    setTarget("");
    setMoveNote("");
    setConfirmDelete(false);
    setFollowUpDue(defaultFollowUpDate());
    setFollowUpChannel("email");
    setFollowUpNotes("");
  }, [applicationId]);

  const application = query.data;
  const isArchived = Boolean(application?.archived_at);
  const transitions = application ? ALLOWED_TRANSITIONS[application.status] : [];

  async function move() {
    if (!target) return;
    try {
      await changeStatus.mutateAsync({ status: target, note: moveNote.trim() || undefined });
      toast.success(`Moved to ${STATUS_LABEL[target]}.`);
      setTarget("");
      setMoveNote("");
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function submitNote() {
    if (!note.trim()) return;
    try {
      await addNote.mutateAsync(note.trim());
      setNote("");
      toast.success("Note added to the timeline.");
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function toggleArchive() {
    if (!application) return;
    try {
      await archive.mutateAsync(!isArchived);
      toast.success(isArchived ? "Application restored." : "Application archived.");
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function performDelete() {
    try {
      await remove.mutateAsync();
      toast.success("Application deleted.");
      setConfirmDelete(false);
      onClose();
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function submitFollowUp() {
    if (!applicationId || !followUpDue) return;
    try {
      await createFollowUp.mutateAsync({
        application_id: applicationId,
        due_on: followUpDue,
        channel: followUpChannel,
        notes: followUpNotes.trim() || null,
      });
      setFollowUpNotes("");
      setFollowUpDue(defaultFollowUpDate());
      toast.success("Follow-up scheduled.");
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function setFollowUpStatus(followUp: FollowUp, status: "done" | "skipped" | "pending") {
    try {
      await updateFollowUp.mutateAsync({ id: followUp.id, payload: { status } });
      toast.success(
        status === "done"
          ? "Follow-up marked done."
          : status === "skipped"
            ? "Follow-up skipped."
            : "Follow-up reopened.",
      );
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function removeFollowUp(followUp: FollowUp) {
    try {
      await deleteFollowUp.mutateAsync(followUp.id);
      toast.success("Follow-up removed.");
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  return (
    <Drawer
      open={Boolean(applicationId)}
      onClose={onClose}
      width="max-w-2xl"
      title={
        application ? (
          <span className="flex items-center gap-2">
            <span className="truncate">{application.title}</span>
          </span>
        ) : (
          "Application"
        )
      }
      subtitle={
        application && (
          <span className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5">
              <Building2 className="h-3.5 w-3.5" aria-hidden />
              {application.company.name}
            </span>
            <StatusBadge status={application.status} />
            {isArchived && (
              <span className="rounded-full border border-line bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-subdued">
                Archived
              </span>
            )}
          </span>
        )
      }
      footer={
        application && (
          <>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="text-danger hover:bg-danger-soft hover:text-danger"
                icon={<Trash2 className="h-4 w-4" />}
                onClick={() => setConfirmDelete(true)}
              >
                Delete
              </Button>
              <Button
                variant="ghost"
                size="sm"
                icon={
                  isArchived ? <ArchiveRestore className="h-4 w-4" /> : <Archive className="h-4 w-4" />
                }
                loading={archive.isPending}
                onClick={() => void toggleArchive()}
              >
                {isArchived ? "Restore" : "Archive"}
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={onEdit} disabled={isArchived}>
                <Pencil className="h-4 w-4" aria-hidden />
                Edit details
              </Button>
            </div>
          </>
        )
      }
    >
      {query.isLoading && <LoadingBlock label="Loading application…" />}
      {query.isError && (
        <ErrorState message="This application could not be loaded." onRetry={() => void query.refetch()} />
      )}
      {application && (
        <div className="space-y-5">
          {isArchived && (
            <InlineAlert tone="warning" title="This application is archived">
              Restore it to change status or edit details. Archived applications are hidden from the
              default list and board.
            </InlineAlert>
          )}

          <Tabs
            items={[
              { value: "overview", label: "Overview" },
              {
                value: "follow-ups",
                label: "Follow-ups",
                count: followUps.data?.total ?? 0,
              },
              { value: "timeline", label: "Timeline", count: application.events.length },
            ]}
            value={tab}
            onChange={setTab}
          />

          {tab === "overview" ? (
            <div className="space-y-5">
              <div className="rounded-xl border border-line bg-surface-2/40 p-4">
                <p className="text-[11px] font-medium uppercase tracking-wide text-subdued">
                  Move stage
                </p>
                {transitions.length === 0 ? (
                  <p className="mt-1.5 text-sm text-muted">
                    {STATUS_LABEL[application.status]} is a final stage. No further transitions are
                    available.
                  </p>
                ) : (
                  <div className="mt-2 space-y-2">
                    <div className="flex flex-wrap gap-2">
                      <Select
                        className="min-w-40 flex-1"
                        value={target}
                        disabled={isArchived || changeStatus.isPending}
                        onChange={(event) => setTarget(event.target.value as ApplicationStatus | "")}
                      >
                        <option value="">Choose the next stage</option>
                        {transitions.map((status) => (
                          <option key={status} value={status}>
                            {STATUS_LABEL[status]}
                          </option>
                        ))}
                      </Select>
                      <Button
                        variant="primary"
                        disabled={!target || isArchived}
                        loading={changeStatus.isPending}
                        onClick={() => void move()}
                      >
                        <Send className="h-4 w-4" aria-hidden />
                        Move
                      </Button>
                    </div>
                    {target && (
                      <Textarea
                        rows={2}
                        placeholder={
                          target === "rejected"
                            ? "Optional: record the rejection reason"
                            : "Optional note for the timeline"
                        }
                        maxLength={500}
                        value={moveNote}
                        disabled={isArchived}
                        onChange={(event) => setMoveNote(event.target.value)}
                      />
                    )}
                  </div>
                )}
              </div>

              <dl className="grid gap-x-6 gap-y-5 sm:grid-cols-2">
                <Detail label="Applied on" icon={<CalendarClock className="h-3 w-3" />}>
                  {formatDate(application.applied_on)}
                </Detail>
                <Detail label="Follow up on" icon={<CalendarClock className="h-3 w-3" />}>
                  {application.follow_up_on ? formatDate(application.follow_up_on) : null}
                </Detail>
                <Detail label="Location" icon={<MapPin className="h-3 w-3" />}>
                  {application.location}
                </Detail>
                <Detail label="Work mode">
                  {application.work_mode ? WORK_MODE_LABEL[application.work_mode] : null}
                </Detail>
                <Detail label="Employment">
                  {application.employment_type
                    ? EMPLOYMENT_TYPE_LABEL[application.employment_type]
                    : null}
                </Detail>
                <Detail label="Salary">
                  {formatSalaryRange(
                    application.salary_min,
                    application.salary_max,
                    application.salary_currency,
                    application.salary_period,
                  )}
                </Detail>
                <Detail label="Source">{application.source}</Detail>
                <Detail label="Job posting">
                  {application.job_url ? (
                    <a
                      href={application.job_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-1 text-accent hover:underline"
                    >
                      Open posting <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : null}
                </Detail>
                <Detail label="Job description" icon={<FileText className="h-3 w-3" />}>
                  {application.job_description ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 text-accent hover:underline"
                      onClick={() => {
                        onClose();
                        navigate(`/job-descriptions?open=${application.job_description?.id}`);
                      }}
                    >
                      {application.job_description.title} <ArrowRight className="h-3 w-3" />
                    </button>
                  ) : null}
                </Detail>
                <Detail label="Resume version" icon={<Link2 className="h-3 w-3" />}>
                  {application.resume_version
                    ? `v${application.resume_version.version_no}${
                        application.resume_version.label
                          ? ` — ${application.resume_version.label}`
                          : ""
                      }`
                    : null}
                </Detail>
                <Detail label="Created">{formatDateTime(application.created_at)}</Detail>
                <Detail label="Last updated">{formatDateTime(application.updated_at)}</Detail>
              </dl>

              {application.notes && (
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-wide text-subdued">Notes</p>
                  <p className="mt-1.5 whitespace-pre-wrap rounded-xl border border-line bg-surface-2/40 p-3.5 text-sm leading-relaxed text-fg">
                    {application.notes}
                  </p>
                </div>
              )}

              {(application.rejection_reason || application.offer_amount || application.offer_deadline) && (
                <div className="grid gap-4 sm:grid-cols-2">
                  {application.rejection_reason && (
                    <div className="sm:col-span-2">
                      <p className="text-[11px] font-medium uppercase tracking-wide text-subdued">
                        Rejection reason
                      </p>
                      <p className="mt-1.5 whitespace-pre-wrap rounded-xl border border-danger/25 bg-danger-soft p-3.5 text-sm text-danger">
                        {application.rejection_reason}
                      </p>
                    </div>
                  )}
                  {application.offer_amount && (
                    <Detail label="Offer amount">
                      {formatSalaryRange(
                        application.offer_amount,
                        null,
                        application.salary_currency,
                        application.salary_period,
                      )}
                    </Detail>
                  )}
                  {application.offer_deadline && (
                    <Detail label="Offer deadline">{formatDate(application.offer_deadline)}</Detail>
                  )}
                </div>
              )}

              {!isArchived && (
                <div className="rounded-xl border border-line bg-surface-2/40 p-4">
                  <Field label="Add a note" hint="Notes are appended to the timeline and never overwritten.">
                    <Textarea
                      rows={3}
                      placeholder="Recruiter call went well — next round scheduled…"
                      maxLength={2000}
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                    />
                  </Field>
                  <div className="mt-2 flex justify-end">
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={addNote.isPending}
                      disabled={!note.trim()}
                      onClick={() => void submitNote()}
                    >
                      Add note
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ) : tab === "follow-ups" ? (
            <div className="space-y-5">
              {!isArchived && (
                <div className="rounded-xl border border-line bg-surface-2/40 p-4">
                  <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-subdued">
                    <MailPlus className="h-3.5 w-3.5" aria-hidden /> Schedule a follow-up
                  </p>
                  <div className="mt-2 grid gap-3 sm:grid-cols-2">
                    <Field label="Due on" htmlFor="follow-up-due">
                      <Input
                        id="follow-up-due"
                        type="date"
                        value={followUpDue}
                        onChange={(event) => setFollowUpDue(event.target.value)}
                      />
                    </Field>
                    <Field label="Channel" htmlFor="follow-up-channel">
                      <Select
                        id="follow-up-channel"
                        value={followUpChannel}
                        onChange={(event) =>
                          setFollowUpChannel(event.target.value as FollowUpChannel)
                        }
                      >
                        {(Object.keys(FOLLOW_UP_CHANNEL_LABEL) as FollowUpChannel[]).map((channel) => (
                          <option key={channel} value={channel}>
                            {FOLLOW_UP_CHANNEL_LABEL[channel]}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </div>
                  <Field label="Note" htmlFor="follow-up-note" className="mt-3">
                    <Textarea
                      id="follow-up-note"
                      rows={2}
                      maxLength={2000}
                      placeholder="Optional: what to ask or send"
                      value={followUpNotes}
                      onChange={(event) => setFollowUpNotes(event.target.value)}
                    />
                  </Field>
                  <div className="mt-2 flex justify-end">
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={createFollowUp.isPending}
                      disabled={!followUpDue}
                      onClick={() => void submitFollowUp()}
                    >
                      Add follow-up
                    </Button>
                  </div>
                </div>
              )}

              {followUps.isLoading ? (
                <LoadingBlock label="Loading follow-ups…" />
              ) : followUps.isError ? (
                <ErrorState
                  message="Follow-ups could not be loaded."
                  onRetry={() => void followUps.refetch()}
                />
              ) : (followUps.data?.items.length ?? 0) === 0 ? (
                <EmptyState
                  className="py-10"
                  icon={<CalendarClock className="h-5 w-5" />}
                  title="No follow-ups yet"
                  description="Set a reminder for the next nudge. Due dates and completions feed the follow-up performance metric."
                />
              ) : (
                <ul className="space-y-2">
                  {followUps.data!.items.map((followUp) => (
                    <li key={followUp.id} className="rounded-xl border border-line bg-surface p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={clsx(
                                "text-sm font-medium",
                                followUp.status === "done" ? "text-subdued line-through" : "text-fg",
                              )}
                            >
                              Due {formatDate(followUp.due_on)}
                            </span>
                            <Badge tone="neutral">{FOLLOW_UP_CHANNEL_LABEL[followUp.channel]}</Badge>
                            <Badge
                              tone={
                                followUp.status === "done"
                                  ? "success"
                                  : followUp.status === "skipped"
                                    ? "warning"
                                    : followUp.is_overdue
                                      ? "danger"
                                      : "accent"
                              }
                            >
                              {FOLLOW_UP_STATUS_LABEL[followUp.status]}
                            </Badge>
                            {followUp.is_overdue && <Badge tone="danger">Overdue</Badge>}
                          </div>
                          {followUp.notes && (
                            <p className="mt-1 whitespace-pre-wrap text-xs text-muted">{followUp.notes}</p>
                          )}
                          {followUp.done_at && (
                            <p className="mt-1 text-[11px] text-subdued">
                              Completed {formatRelative(followUp.done_at)}
                            </p>
                          )}
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          {followUp.status === "pending" ? (
                            <>
                              <Button
                                size="sm"
                                variant="ghost"
                                icon={<Check className="h-3.5 w-3.5" />}
                                onClick={() => void setFollowUpStatus(followUp, "done")}
                                disabled={updateFollowUp.isPending}
                              >
                                Done
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                icon={<SkipForward className="h-3.5 w-3.5" />}
                                onClick={() => void setFollowUpStatus(followUp, "skipped")}
                                disabled={updateFollowUp.isPending}
                              >
                                Skip
                              </Button>
                            </>
                          ) : (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => void setFollowUpStatus(followUp, "pending")}
                              disabled={updateFollowUp.isPending}
                            >
                              Reopen
                            </Button>
                          )}
                          <button
                            type="button"
                            onClick={() => void removeFollowUp(followUp)}
                            aria-label="Delete follow-up"
                            className="flex h-7 w-7 items-center justify-center rounded-md text-subdued hover:bg-danger-soft hover:text-danger"
                          >
                            <Trash2 className="h-3.5 w-3.5" aria-hidden />
                          </button>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <ol className="relative space-y-4 border-l border-line pl-5">
              {application.events.length === 0 && (
                <li className="text-sm text-muted">No events recorded yet.</li>
              )}
              {application.events.map((event, index) => (
                <li key={event.id} className="relative">
                  <span
                    className={clsx(
                      "absolute -left-[30px] flex h-6 w-6 items-center justify-center rounded-full border",
                      event.type === "status_change"
                        ? "border-accent/30 bg-accent-soft text-accent"
                        : event.type === "note"
                          ? "border-warning/30 bg-warning-soft text-warning"
                          : "border-line bg-surface text-subdued",
                    )}
                  >
                    {EVENT_ICON[event.type]}
                  </span>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="text-sm font-medium text-fg">
                      {index === 0 ? "Latest · " : ""}
                      {eventText(event)}
                    </p>
                    <time
                      className="text-[11px] text-subdued"
                      dateTime={event.created_at}
                      title={formatDateTime(event.created_at)}
                    >
                      {formatRelative(event.created_at)}
                    </time>
                  </div>
                  {event.type === "status_change" && event.to_status && (
                    <div className="mt-1.5 flex items-center gap-1.5 text-xs text-muted">
                      <StatusBadge status={event.from_status as ApplicationStatus} />
                      <ArrowRight className="h-3 w-3" />
                      <StatusBadge status={event.to_status as ApplicationStatus} />
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => void performDelete()}
        loading={remove.isPending}
        title="Delete this application?"
        description="This permanently removes the application, its timeline and any linked notes. Resume files and job descriptions are kept."
        confirmLabel="Delete application"
      />
    </Drawer>
  );
}
