import clsx from "clsx";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BriefcaseBusiness,
  CalendarClock,
  CheckCircle2,
  Clock,
  Inbox,
  Plus,
  Send,
  Sparkles,
  Target,
  TrendingUp,
  Trophy,
} from "lucide-react";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/Feedback";
import { Card, PageHeader, SectionTitle } from "@/components/ui/Layout";
import { STATUS_DOT, STATUS_LABEL, STATUS_ORDER } from "@/lib/constants";
import { formatDate, formatDateTime, formatRelative, greeting, pluralize } from "@/lib/format";
import { useDashboard } from "@/lib/queries";
import type { ApplicationStatus, Dashboard } from "@/lib/types";

function MetricCard({
  label,
  value,
  hint,
  icon,
  accent,
}: {
  label: string;
  value: string | number;
  hint: string;
  icon: React.ReactNode;
  accent?: "accent" | "teal" | "success" | "warning";
}) {
  const accents = {
    accent: "bg-accent-soft text-accent",
    teal: "bg-teal-soft text-teal",
    success: "bg-success-soft text-success",
    warning: "bg-warning-soft text-warning",
  } as const;
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[13px] font-medium text-muted">{label}</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight text-fg tabular-nums">{value}</p>
        </div>
        <span
          className={clsx(
            "flex h-9 w-9 items-center justify-center rounded-lg",
            accents[accent ?? "accent"],
          )}
        >
          {icon}
        </span>
      </div>
      <p className="mt-3 text-xs text-subdued">{hint}</p>
    </Card>
  );
}

function percent(rate: number | null): string {
  if (rate == null) return "—";
  return `${Math.round(rate * 100)}%`;
}

function Pipeline({ data }: { data: Dashboard }) {
  const counts = new Map(data.by_status.map((row) => [row.status, row.count]));
  const max = Math.max(1, ...data.by_status.map((row) => row.count));
  return (
    <Card className="p-5 xl:col-span-2">
      <SectionTitle
        title="Pipeline"
        hint="Where every application currently sits."
        action={
          <Link
            to="/applications"
            className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
          >
            Open board <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        }
      />
      <div className="mt-5 space-y-3">
        {STATUS_ORDER.map((status) => {
          const count = counts.get(status) ?? 0;
          const width = Math.round((count / max) * 100);
          return (
            <div key={status} className="flex items-center gap-3">
              <span className="flex w-28 shrink-0 items-center gap-2 text-[13px] text-muted">
                <span className={clsx("h-1.5 w-1.5 rounded-full", STATUS_DOT[status])} aria-hidden />
                {STATUS_LABEL[status]}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                <div
                  className={clsx(
                    "h-full rounded-full transition-[width]",
                    status === "rejected" || status === "withdrawn" || status === "ghosted"
                      ? "bg-line-strong"
                      : status === "offer" || status === "accepted"
                        ? "bg-success"
                        : status === "interviewing"
                          ? "bg-teal"
                          : "bg-accent",
                  )}
                  style={{ width: count === 0 ? "0%" : `${Math.max(width, 6)}%` }}
                />
              </div>
              <span className="w-8 text-right text-[13px] font-medium text-fg tabular-nums">
                {count}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function Conversion({ data }: { data: Dashboard }) {
  const rows: { label: string; metric: Dashboard["response"] }[] = [
    { label: "Response rate", metric: data.response },
    { label: "Reached interview", metric: data.interview_conversion },
    { label: "Offer after interview", metric: data.offer_conversion },
  ];
  return (
    <Card className="flex flex-col p-5">
      <SectionTitle title="Conversion" hint="How the funnel is holding up." />
      <div className="mt-5 flex-1 space-y-4">
        {rows.map((row) => (
          <div key={row.label}>
            <div className="flex items-baseline justify-between">
              <span className="text-[13px] text-muted">{row.label}</span>
              <span className="text-lg font-semibold text-fg tabular-nums">
                {percent(row.metric.rate)}
              </span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full bg-gradient-to-r from-accent to-teal"
                style={{ width: `${Math.round((row.metric.rate ?? 0) * 100)}%` }}
              />
            </div>
            <p className="mt-1 text-[11px] text-subdued">
              {row.metric.numerator} of {row.metric.denominator} {row.metric.label}
            </p>
          </div>
        ))}
      </div>
      <div className="mt-5 flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2 text-xs text-muted">
        <Clock className="h-3.5 w-3.5" aria-hidden />
        {data.average_days_to_response != null
          ? `${data.average_days_to_response} days average to first response`
          : "No responses recorded yet"}
      </div>
    </Card>
  );
}

function Trend({ data }: { data: Dashboard }) {
  const max = Math.max(1, ...data.applications_trend.map((point) => point.count));
  return (
    <Card className="p-5 xl:col-span-2">
      <SectionTitle
        title="Applications per week"
        hint="Submitted over the last 12 weeks."
        action={
          <span className="inline-flex items-center gap-1 text-xs font-medium text-muted">
            <TrendingUp className="h-3.5 w-3.5" aria-hidden />
            {data.applied_this_week} this week
          </span>
        }
      />
      <div className="mt-6 flex h-32 items-end gap-1.5">
        {data.applications_trend.map((point) => (
          <div key={point.bucket} className="group flex h-full flex-1 flex-col justify-end">
            <div
              role="img"
              aria-label={`${point.count} applications in week of ${formatDate(point.bucket)}`}
              className="relative w-full rounded-t bg-accent/75 transition-colors group-hover:bg-accent"
              style={{ height: `${Math.max((point.count / max) * 100, point.count ? 6 : 2)}%` }}
              title={`${point.count} in week of ${formatDate(point.bucket)}`}
            >
              {point.count > 0 && (
                <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-[10px] font-medium text-muted opacity-0 transition-opacity group-hover:opacity-100 max-sm:opacity-100">
                  {point.count}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-subdued">
        <span>{formatDate(data.applications_trend[0]?.bucket ?? new Date())}</span>
        <span>
          {data.applications_trend.length > 2
            ? formatDate(data.applications_trend[Math.floor(data.applications_trend.length / 2)].bucket)
            : `${data.applied_this_month} this month`}
        </span>
        <span>This week</span>
      </div>
    </Card>
  );
}

function Upcoming({ data }: { data: Dashboard }) {
  return (
    <Card className="p-5">
      <SectionTitle
        title="Upcoming interviews"
        hint="Next conversations on the calendar."
        action={
          <Link
            to="/interviews"
            className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
          >
            All interviews <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        }
      />
      {data.upcoming_interviews.length === 0 ? (
        <EmptyState
          className="py-8"
          icon={<CalendarClock className="h-5 w-5" />}
          title="Nothing scheduled"
          description="Schedule the next conversation from the interviews page and it will appear here."
        />
      ) : (
        <ul className="mt-4 space-y-3">
          {data.upcoming_interviews.map((interview) => (
            <li key={interview.id} className="rounded-lg border border-line bg-surface-2/60 p-3">
              <p className="text-sm font-medium text-fg">{interview.application_title}</p>
              <p className="text-xs text-muted">{interview.company_name}</p>
              <p className="mt-1.5 text-xs text-accent">
                {formatDateTime(interview.scheduled_at)} · Round {interview.round_no}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ActivityFeed({ data }: { data: Dashboard }) {
  return (
    <Card className="p-5 xl:col-span-2">
      <SectionTitle
        title="Recent activity"
        hint="The last things that happened across your search."
        action={
          <Link
            to="/applications"
            className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
          >
            All applications <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        }
      />
      {data.recent_activity.length === 0 ? (
        <EmptyState
          className="py-8"
          icon={<Activity className="h-5 w-5" />}
          title="No activity yet"
          description="Status changes and notes will appear here as you work through applications."
        />
      ) : (
        <ul className="mt-4 divide-y divide-line">
          {data.recent_activity.slice(0, 8).map((item) => (
            <li key={item.id} className="flex items-start gap-3 py-3 first:pt-1 last:pb-1">
              <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-2 text-subdued">
                {item.type === "note" ? (
                  <Inbox className="h-3 w-3" />
                ) : item.type === "status_change" ? (
                  <ArrowUpRight className="h-3 w-3" />
                ) : (
                  <CheckCircle2 className="h-3 w-3" />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-fg">
                  <span className="font-medium">{item.application_title}</span>
                  <span className="text-muted"> · {item.company_name}</span>
                </p>
                <p className="text-xs text-muted">
                  {item.type === "status_change" && item.to_status ? (
                    <>
                      Moved to{" "}
                      <span className="font-medium text-fg">
                        {STATUS_LABEL[item.to_status as ApplicationStatus] ?? item.to_status}
                      </span>
                    </>
                  ) : item.type === "note" ? (
                    "Note added"
                  ) : (
                    "Application updated"
                  )}
                </p>
              </div>
              <span className="shrink-0 text-[11px] text-subdued">{formatRelative(item.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function FocusList({ data }: { data: Dashboard }) {
  const items = [
    {
      label: "Follow-ups due today",
      value: data.follow_ups.due_today,
      tone: data.follow_ups.due_today > 0 ? "text-warning" : "text-fg",
      to: "/applications",
    },
    {
      label: "Overdue follow-ups",
      value: data.follow_ups.overdue,
      tone: data.follow_ups.overdue > 0 ? "text-danger" : "text-fg",
      to: "/applications",
    },
    {
      label: "Open tasks",
      value: data.tasks.pending,
      tone: "text-fg",
      to: "/tasks",
    },
    {
      label: "Overdue tasks",
      value: data.tasks.overdue,
      tone: data.tasks.overdue > 0 ? "text-danger" : "text-fg",
      to: "/tasks",
    },
  ];
  return (
    <Card className="p-5">
      <SectionTitle title="Needs attention" hint="Follow-ups and tasks across the workspace." />
      <ul className="mt-4 space-y-1">
        {items.map((item) => (
          <li key={item.label}>
            <Link
              to={item.to}
              className="flex items-center justify-between gap-3 rounded-lg px-2 py-1.5 -mx-2 transition-colors hover:bg-surface-2"
            >
              <span className="text-[13px] text-muted">{item.label}</span>
              <span className={clsx("text-sm font-semibold tabular-nums", item.tone)}>
                {item.value}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-3 text-[11px]">
        <Link to="/tasks" className="font-medium text-accent hover:underline">
          Open tasks
        </Link>
        <Link to="/interviews" className="font-medium text-accent hover:underline">
          Interviews
        </Link>
        <Link to="/analytics" className="font-medium text-accent hover:underline">
          Analytics
        </Link>
      </div>
    </Card>
  );
}

function Onboarding() {
  return (
    <Card className="overflow-hidden">
      <div className="grid gap-6 p-6 lg:grid-cols-[1.4fr_1fr] lg:p-8">
        <div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/25 bg-accent-soft px-2.5 py-1 text-[11px] font-medium text-accent">
            <Sparkles className="h-3 w-3" aria-hidden /> Start here
          </span>
          <h2 className="mt-3 text-balance text-2xl font-semibold tracking-tight text-fg">
            Set up the workspace around your search.
          </h2>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted">
            CareerOS gets more useful with every detail you add. Begin with a resume and one job
            description, then log your first application.
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            <Link to="/resumes">
              <Button variant="primary" icon={<Plus className="h-4 w-4" />}>
                Upload a resume
              </Button>
            </Link>
            <Link to="/job-descriptions">
              <Button icon={<Plus className="h-4 w-4" />}>Add a job description</Button>
            </Link>
            <Link to="/applications?new=1">
              <Button variant="ghost">Log an application</Button>
            </Link>
          </div>
        </div>
        <ol className="space-y-3">
          {[
            { title: "Resume versions", body: "Keep every tailored version with notes.", icon: Target },
            { title: "Job descriptions", body: "Paste text or upload a PDF to keep context.", icon: BriefcaseBusiness },
            { title: "Applications", body: "Track stages, dates and follow-ups in one pipeline.", icon: Send },
          ].map((step, index) => (
            <li key={step.title} className="flex gap-3 rounded-xl border border-line bg-surface-2/50 p-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-surface text-xs font-semibold text-muted">
                {index + 1}
              </span>
              <div>
                <p className="flex items-center gap-1.5 text-sm font-medium text-fg">
                  <step.icon className="h-3.5 w-3.5 text-subdued" aria-hidden />
                  {step.title}
                </p>
                <p className="mt-0.5 text-xs text-muted">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </Card>
  );
}

export function DashboardPage() {
  const { owner } = useAuth();
  const query = useDashboard();
  const firstName = owner?.full_name?.split(" ")[0] ?? owner?.email.split("@")[0] ?? "there";
  const today = new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date());

  if (query.isLoading) return <LoadingBlock label="Loading dashboard…" />;
  if (query.isError) {
    return <ErrorState message="The dashboard could not be loaded." onRetry={() => void query.refetch()} />;
  }
  const data = query.data!;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${greeting()}, ${firstName}`}
        subtitle={`${today} · ${pluralize(data.active_applications, "active application")} in play`}
        actions={
          <>
            <Link to="/applications?view=board">
              <Button variant="secondary">View pipeline</Button>
            </Link>
            <Link to="/applications?new=1">
              <Button variant="primary" icon={<Plus className="h-4 w-4" />}>
                New application
              </Button>
            </Link>
          </>
        }
      />

      {data.total_applications === 0 && <Onboarding />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Active applications"
          value={data.active_applications}
          hint={`${data.total_applications} total · ${data.archived_applications} archived`}
          icon={<BriefcaseBusiness className="h-4 w-4" aria-hidden />}
        />
        <MetricCard
          label="Applied this month"
          value={data.applied_this_month}
          hint={`${data.applied_this_week} submitted this week`}
          icon={<Send className="h-4 w-4" aria-hidden />}
          accent="teal"
        />
        <MetricCard
          label="Interviews scheduled"
          value={data.interviews_scheduled}
          hint={`${data.by_status.find((row) => row.status === "interviewing")?.count ?? 0} applications in interviewing`}
          icon={<CalendarClock className="h-4 w-4" aria-hidden />}
          accent="warning"
        />
        <MetricCard
          label="Offers"
          value={data.offers}
          hint={
            data.rejections
              ? `${data.rejections} rejections recorded`
              : "No rejections recorded yet"
          }
          icon={<Trophy className="h-4 w-4" aria-hidden />}
          accent="success"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Pipeline data={data} />
        <Conversion data={data} />
        <Trend data={data} />
        <Upcoming data={data} />
        <ActivityFeed data={data} />
        <FocusList data={data} />
        <div className="xl:col-span-3">
          <Card className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-soft text-teal">
                <Activity className="h-4 w-4" aria-hidden />
              </span>
              <p className="text-sm text-muted">
                <span className="font-medium text-fg">Stay consistent.</span> Applications answered
                at <span className="font-medium text-fg">{percent(data.response.rate)}</span> — every
                follow-up counts.
              </p>
            </div>
            <Link to="/applications?new=1" className="text-xs font-medium text-accent hover:underline">
              Add today's application
            </Link>
          </Card>
        </div>
      </div>
    </div>
  );
}
