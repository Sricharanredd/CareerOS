import clsx from "clsx";
import {
  CalendarDays,
  Check,
  CheckCircle2,
  Clock,
  ListTodo,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  Timer,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button, IconButton } from "@/components/ui/Button";
import { EmptyState, ErrorState, InlineAlert, LoadingBlock } from "@/components/ui/Feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/Form";
import { Card, PageHeader, SectionTitle } from "@/components/ui/Layout";
import { ConfirmDialog, Modal } from "@/components/ui/Overlay";
import { Tabs } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { errorMessage } from "@/lib/api";
import { TASK_PRIORITY_LABEL } from "@/lib/constants";
import { formatDate, formatDateTime, formatRelative, parseDate } from "@/lib/format";
import {
  useApplications,
  useCompleteTask,
  useCreateTask,
  useCreateTimeEntry,
  useDashboard,
  useDeleteTask,
  useDeleteTimeEntry,
  useTasks,
  useTimeEntries,
  useUpdateTimeEntry,
} from "@/lib/queries";
import type { Task, TaskPriority } from "@/lib/types";

type Bucket = "today" | "overdue" | "upcoming" | "open" | "completed";

const BUCKETS: { value: Bucket; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "overdue", label: "Overdue" },
  { value: "upcoming", label: "Upcoming" },
  { value: "open", label: "All open" },
  { value: "completed", label: "Completed" },
];

const PRIORITY_TONE: Record<TaskPriority, "neutral" | "accent" | "warning"> = {
  low: "neutral",
  medium: "accent",
  high: "warning",
};

function toLocalInput(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

function fromLocalInput(value: string): string {
  return new Date(value).toISOString();
}

function formatDuration(minutes: number | null): string {
  if (minutes == null) return "running";
  const total = Math.round(minutes);
  const hours = Math.floor(total / 60);
  const mins = total % 60;
  if (hours === 0) return `${mins}m`;
  return `${hours}h ${String(mins).padStart(2, "0")}m`;
}

function elapsedLabel(startedAt: string, now: number): string {
  const start = parseDate(startedAt).getTime();
  const seconds = Math.max(0, Math.floor((now - start) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
    : `${minutes}:${String(secs).padStart(2, "0")}`;
}

function TaskRow({
  task,
  busy,
  running,
  onToggle,
  onDelete,
  onStart,
  onLog,
}: {
  task: Task;
  busy: boolean;
  running: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onStart: () => void;
  onLog: () => void;
}) {
  const done = task.status === "done";
  return (
    <li className="flex items-start gap-3 border-b border-line px-4 py-3 last:border-b-0">
      <button
        type="button"
        onClick={onToggle}
        disabled={busy}
        aria-label={done ? `Reopen ${task.title}` : `Complete ${task.title}`}
        aria-pressed={done}
        className={clsx(
          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors",
          done
            ? "border-success bg-success text-white"
            : "border-line-strong text-transparent hover:border-success hover:text-success/40",
        )}
      >
        <Check className="h-3 w-3" aria-hidden />
      </button>

      <div className="min-w-0 flex-1">
        <p
          className={clsx(
            "text-sm font-medium",
            done ? "text-subdued line-through" : "text-fg",
          )}
        >
          {task.title}
        </p>
        {task.description && (
          <p className="mt-0.5 line-clamp-2 text-xs text-muted">{task.description}</p>
        )}
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <Badge tone={PRIORITY_TONE[task.priority]}>{TASK_PRIORITY_LABEL[task.priority]}</Badge>
          {done && task.completed_at && (
            <span className="inline-flex items-center gap-1 text-[11px] text-subdued">
              <CheckCircle2 className="h-3 w-3" aria-hidden /> {formatRelative(task.completed_at)}
            </span>
          )}
          {!done && task.due_on && (
            <span
              className={clsx(
                "inline-flex items-center gap-1 text-[11px]",
                task.is_overdue ? "font-medium text-danger" : "text-subdued",
              )}
            >
              <CalendarDays className="h-3 w-3" aria-hidden />
              {task.is_overdue ? "Overdue " : "Due "}
              {formatDate(task.due_on)}
            </span>
          )}
          {task.application && (
            <Link
              to={`/applications?selected=${task.application.id}`}
              className="inline-flex max-w-full items-center gap-1 truncate text-[11px] text-accent hover:underline"
            >
              {task.application.title} · {task.application.company_name}
            </Link>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        {!done && (
          <>
            <IconButton
              label={running ? "A timer is already running" : `Start timer for ${task.title}`}
              onClick={onStart}
              disabled={running}
              className="h-8 w-8"
            >
              <Play className="h-3.5 w-3.5" />
            </IconButton>
            <IconButton label={`Log time for ${task.title}`} onClick={onLog} className="h-8 w-8">
              <Timer className="h-3.5 w-3.5" />
            </IconButton>
          </>
        )}
        <IconButton
          label={`Delete ${task.title}`}
          onClick={onDelete}
          className="h-8 w-8 hover:bg-danger-soft hover:text-danger"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </IconButton>
      </div>
    </li>
  );
}

export function TasksPage() {
  const toast = useToast();
  const [bucket, setBucket] = useState<Bucket>("today");
  const [search, setSearch] = useState("");
  const [quickTitle, setQuickTitle] = useState("");
  const [quickDue, setQuickDue] = useState(toLocalInput(new Date()).slice(0, 10));
  const [quickPriority, setQuickPriority] = useState<TaskPriority>("medium");
  const [quickApplication, setQuickApplication] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [quickDescription, setQuickDescription] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null);
  const [timeTarget, setTimeTarget] = useState<Task | null>(null);
  const [timeStart, setTimeStart] = useState("");
  const [timeEnd, setTimeEnd] = useState("");
  const [timeError, setTimeError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const dashboard = useDashboard();
  const tasks = useTasks({
    bucket,
    search: search.trim() || undefined,
  });
  const applications = useApplications({ page: 1, page_size: 100 });
  const timeEntries = useTimeEntries({});
  const createTask = useCreateTask();
  const completeTask = useCompleteTask();
  const deleteTask = useDeleteTask();
  const createTimeEntry = useCreateTimeEntry();
  const updateTimeEntry = useUpdateTimeEntry();
  const deleteTimeEntry = useDeleteTimeEntry();

  const runningEntry = useMemo(
    () => timeEntries.data?.items.find((entry) => entry.ended_at == null) ?? null,
    [timeEntries.data],
  );
  const recentEntries = useMemo(
    () => (timeEntries.data?.items ?? []).filter((entry) => entry.ended_at != null).slice(0, 8),
    [timeEntries.data],
  );

  useEffect(() => {
    if (!runningEntry) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [runningEntry]);

  const applicationOptions = applications.data?.items ?? [];

  function handleQuickAdd() {
    const title = quickTitle.trim();
    if (!title) return;
    createTask.mutate(
      {
        title,
        due_on: quickDue || null,
        priority: quickPriority,
        description: quickDescription.trim() || null,
        application_id: quickApplication || null,
      },
      {
        onSuccess: () => {
          setQuickTitle("");
          setQuickDescription("");
          setQuickApplication("");
          toast.success("Task added");
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  }

  function handleToggle(task: Task) {
    completeTask.mutate(
      { id: task.id, completed: task.status !== "done" },
      {
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  }

  function startTimer(task: Task) {
    if (runningEntry) return;
    createTimeEntry.mutate(
      { task_id: task.id, started_at: new Date().toISOString() },
      {
        onSuccess: () => toast.success(`Timer started: ${task.title}`),
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  }

  function stopTimer() {
    if (!runningEntry) return;
    updateTimeEntry.mutate(
      { id: runningEntry.id, payload: { ended_at: new Date().toISOString() } },
      {
        onSuccess: () => toast.success("Timer stopped"),
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  }

  function openTimeModal(task: Task) {
    const end = new Date();
    const start = new Date(end.getTime() - 30 * 60_000);
    setTimeStart(toLocalInput(start));
    setTimeEnd(toLocalInput(end));
    setTimeError(null);
    setTimeTarget(task);
  }

  function submitTimeEntry() {
    if (!timeTarget) return;
    if (!timeStart) {
      setTimeError("Choose a start time.");
      return;
    }
    const startedAt = fromLocalInput(timeStart);
    const endedAt = timeEnd ? fromLocalInput(timeEnd) : null;
    if (endedAt && new Date(endedAt) <= new Date(startedAt)) {
      setTimeError("The end time must be after the start time.");
      return;
    }
    createTimeEntry.mutate(
      { task_id: timeTarget.id, started_at: startedAt, ended_at: endedAt },
      {
        onSuccess: () => {
          setTimeTarget(null);
          toast.success(`Time logged: ${timeTarget.title}`);
        },
        onError: (error) => setTimeError(errorMessage(error)),
      },
    );
  }

  const items = tasks.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tasks"
        subtitle="The small steps that keep the search moving. Complete them, log the time, and see the pattern."
        actions={
          dashboard.data ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-line bg-surface px-3 py-2 text-xs text-muted">
              <span>
                <span className="font-semibold text-fg tabular-nums">{dashboard.data.tasks.pending}</span> open
              </span>
              <span>
                <span className="font-semibold text-danger tabular-nums">{dashboard.data.tasks.overdue}</span> overdue
              </span>
              <span>
                <span className="font-semibold text-fg tabular-nums">{dashboard.data.tasks.due_today}</span> today
              </span>
              <span>
                <span className="font-semibold text-success tabular-nums">
                  {dashboard.data.tasks.completed_this_week}
                </span>{" "}
                this week
              </span>
            </div>
          ) : undefined
        }
      />

      {runningEntry && (
        <div className="flex flex-col gap-3 rounded-xl border border-accent/30 bg-accent-soft px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface text-accent">
              <Clock className="h-4 w-4 animate-pulse" aria-hidden />
            </span>
            <div>
              <p className="text-sm font-medium text-fg">
                {runningEntry.task_title ?? "Untagged session"}
              </p>
              <p className="text-xs text-muted">
                Started {formatRelative(runningEntry.started_at)} · <span className="tabular-nums">{elapsedLabel(runningEntry.started_at, now)}</span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={stopTimer} loading={updateTimeEntry.isPending} icon={<Pause className="h-3.5 w-3.5" />}>
              Stop timer
            </Button>
            <IconButton
              label="Discard running timer"
              onClick={() => deleteTimeEntry.mutate(runningEntry.id)}
              className="h-8 w-8 hover:bg-danger-soft hover:text-danger"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </IconButton>
          </div>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px] xl:items-start">
        <div className="space-y-4">
          <Card className="p-4">
            <form
              className="flex flex-col gap-2 sm:flex-row sm:items-end"
              onSubmit={(event) => {
                event.preventDefault();
                handleQuickAdd();
              }}
            >
              <Field label="Quick add" htmlFor="task-title" className="flex-1">
                <Input
                  id="task-title"
                  value={quickTitle}
                  onChange={(event) => setQuickTitle(event.target.value)}
                  placeholder="e.g. Send a follow-up to the recruiter"
                  maxLength={250}
                />
              </Field>
              <Field label="Due" htmlFor="task-due" className="sm:w-40">
                <Input
                  id="task-due"
                  type="date"
                  value={quickDue}
                  onChange={(event) => setQuickDue(event.target.value)}
                />
              </Field>
              <Field label="Priority" htmlFor="task-priority" className="sm:w-36">
                <Select
                  id="task-priority"
                  value={quickPriority}
                  onChange={(event) => setQuickPriority(event.target.value as TaskPriority)}
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </Select>
              </Field>
              <Button type="submit" variant="primary" disabled={!quickTitle.trim()} loading={createTask.isPending} icon={<Plus className="h-4 w-4" />}>
                Add
              </Button>
            </form>
            <button
              type="button"
              onClick={() => setShowAdvanced((value) => !value)}
              className="mt-2 text-[11px] font-medium text-accent hover:underline"
            >
              {showAdvanced ? "Hide details" : "Add a note or link an application"}
            </button>
            {showAdvanced && (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Field label="Link to application" htmlFor="task-application">
                  <Select
                    id="task-application"
                    value={quickApplication}
                    onChange={(event) => setQuickApplication(event.target.value)}
                  >
                    <option value="">No application</option>
                    {applicationOptions.map((application) => (
                      <option key={application.id} value={application.id}>
                        {application.title} — {application.company.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Note" htmlFor="task-note">
                  <Textarea
                    id="task-note"
                    rows={2}
                    value={quickDescription}
                    onChange={(event) => setQuickDescription(event.target.value)}
                    placeholder="Optional context"
                  />
                </Field>
              </div>
            )}
          </Card>

          <Card className="overflow-hidden">
            <div className="flex flex-col gap-3 px-4 pt-3 sm:flex-row sm:items-center sm:justify-between">
              <Tabs<Bucket>
                items={BUCKETS.map((item) => ({ value: item.value, label: item.label }))}
                value={bucket}
                onChange={setBucket}
                className="border-0"
              />
              <div className="relative w-full sm:w-56">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subdued" aria-hidden />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search tasks"
                  aria-label="Search tasks"
                  className="h-8 pl-8 text-[13px]"
                />
              </div>
            </div>

            <div className="mt-2 border-t border-line">
              {tasks.isLoading ? (
                <LoadingBlock label="Loading tasks…" />
              ) : tasks.isError ? (
                <ErrorState message="Tasks could not be loaded." onRetry={() => void tasks.refetch()} />
              ) : items.length === 0 ? (
                <EmptyState
                  className="py-14"
                  icon={<ListTodo className="h-5 w-5" />}
                  title={
                    bucket === "today"
                      ? "Nothing due today"
                      : bucket === "overdue"
                        ? "No overdue tasks"
                        : bucket === "completed"
                          ? "Nothing completed yet"
                          : "No tasks here"
                  }
                  description={
                    bucket === "today"
                      ? "Add a task above or pick another tab to see the rest of the list."
                      : "Tasks you add will appear in this view."
                  }
                />
              ) : (
                <ul>
                  {items.map((task) => (
                    <TaskRow
                      key={task.id}
                      task={task}
                      busy={completeTask.isPending}
                      running={Boolean(runningEntry)}
                      onToggle={() => handleToggle(task)}
                      onDelete={() => setDeleteTarget(task)}
                      onStart={() => startTimer(task)}
                      onLog={() => openTimeModal(task)}
                    />
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="p-5">
            <SectionTitle title="Time logged" hint="Recent finished sessions." />
            {timeEntries.isLoading ? (
              <LoadingBlock label="Loading time…" />
            ) : recentEntries.length === 0 ? (
              <p className="mt-4 rounded-lg border border-dashed border-line-strong px-3 py-6 text-center text-xs text-subdued">
                No finished sessions yet. Start a timer from any task or log time manually.
              </p>
            ) : (
              <ul className="mt-4 divide-y divide-line">
                {recentEntries.map((entry) => (
                  <li key={entry.id} className="flex items-start justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                    <div className="min-w-0">
                      <p className="truncate text-[13px] text-fg">{entry.task_title ?? "Untagged"}</p>
                      <p className="text-[11px] text-subdued">
                        {formatDateTime(entry.started_at)} · {formatDuration(entry.duration_minutes)}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => deleteTimeEntry.mutate(entry.id)}
                      aria-label="Delete time entry"
                      className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-subdued hover:bg-danger-soft hover:text-danger"
                    >
                      <Trash2 className="h-3 w-3" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="p-5">
            <SectionTitle title="Working rhythm" hint="Small, honest signals." />
            <p className="mt-3 text-xs leading-relaxed text-muted">
              Time entries are per task and cannot overlap. Durations and weekly totals are computed
              from these records on the analytics page — nothing is estimated.
            </p>
            <Link
              to="/analytics"
              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
            >
              Open analytics <RotateCcw className="h-3 w-3" aria-hidden />
            </Link>
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteTask.mutate(deleteTarget.id, {
            onSuccess: () => {
              setDeleteTarget(null);
              toast.success("Task deleted");
            },
            onError: (error) => {
              toast.error(errorMessage(error));
              setDeleteTarget(null);
            },
          });
        }}
        title="Delete this task?"
        description={
          deleteTarget
            ? `“${deleteTarget.title}” will be removed. Its logged time entries stay in your records.`
            : undefined
        }
        confirmLabel="Delete task"
        loading={deleteTask.isPending}
      />

      <Modal
        open={Boolean(timeTarget)}
        onClose={() => setTimeTarget(null)}
        title="Log time"
        description={timeTarget?.title}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setTimeTarget(null)} disabled={createTimeEntry.isPending}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={submitTimeEntry}
              loading={createTimeEntry.isPending}
              icon={<Timer className="h-4 w-4" />}
            >
              Save entry
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Started" htmlFor="time-start" required>
            <Input
              id="time-start"
              type="datetime-local"
              value={timeStart}
              onChange={(event) => setTimeStart(event.target.value)}
            />
          </Field>
          <Field
            label="Ended"
            htmlFor="time-end"
            hint="Leave blank to keep the timer running and stop it later from the banner."
          >
            <Input
              id="time-end"
              type="datetime-local"
              value={timeEnd}
              onChange={(event) => setTimeEnd(event.target.value)}
            />
          </Field>
          {timeError && <InlineAlert title="Could not log time">{timeError}</InlineAlert>}
        </div>
      </Modal>
    </div>
  );
}
