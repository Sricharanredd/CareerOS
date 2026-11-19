import clsx from "clsx";
import {
  Activity,
  ArrowRight,
  BarChart3,
  BriefcaseBusiness,
  CalendarCheck,
  Clock,
  FileSearch,
  Gauge,
  Info,
  ListTodo,
  Send,
  Target,
  Timer,
  TrendingUp,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/Feedback";
import { Card, PageHeader, SectionTitle } from "@/components/ui/Layout";
import { SegmentedControl } from "@/components/ui/Tabs";
import { STATUS_DOT, STATUS_LABEL, STATUS_ORDER } from "@/lib/constants";
import { formatDate, formatMonth, formatRelative } from "@/lib/format";
import { useAnalytics } from "@/lib/queries";
import type { Analytics, ConversionMetric } from "@/lib/types";

function percent(rate: number | null): string {
  if (rate == null) return "Not enough data";
  return `${Math.round(rate * 100)}%`;
}

function formatMinutes(minutes: number): string {
  if (minutes <= 0) return "0m";
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return hours ? `${hours}h ${String(mins).padStart(2, "0")}m` : `${mins}m`;
}

function MetricCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: string | number;
  hint: string;
  icon: React.ReactNode;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[13px] font-medium text-muted">{label}</p>
          <p
            className={clsx(
              "mt-2 font-semibold tracking-tight text-fg",
              typeof value === "number" ? "text-3xl tabular-nums" : "text-xl",
            )}
          >
            {value}
          </p>
        </div>
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent">
          {icon}
        </span>
      </div>
      <p className="mt-3 text-xs text-subdued">{hint}</p>
    </Card>
  );
}

function ConversionRow({ label, metric }: { label: string; metric: ConversionMetric }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] text-muted">{label}</span>
        <span
          className={clsx(
            "text-lg font-semibold tabular-nums",
            metric.rate == null ? "text-sm font-medium text-subdued" : "text-fg",
          )}
        >
          {percent(metric.rate)}
        </span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface-2">
        {metric.rate != null && (
          <div
            className="h-full rounded-full bg-gradient-to-r from-accent to-teal"
            style={{ width: `${Math.round(metric.rate * 100)}%` }}
          />
        )}
      </div>
      <p className="mt-1 text-[11px] text-subdued">
        {metric.denominator === 0
          ? `No ${metric.label} recorded yet`
          : `${metric.numerator} of ${metric.denominator} ${metric.label}`}
      </p>
    </div>
  );
}

function Chart({
  points,
  valueLabel,
  color = "bg-accent/80",
  emptyLabel,
}: {
  points: { key: string; label: string; shortLabel: string; value: number }[];
  valueLabel: (value: number) => string;
  color?: string;
  emptyLabel: string;
}) {
  const max = Math.max(1, ...points.map((point) => point.value));
  const total = points.reduce((sum, point) => sum + point.value, 0);
  if (total === 0) {
    return (
      <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-line-strong text-xs text-subdued">
        {emptyLabel}
      </div>
    );
  }
  return (
    <div>
      <div className="flex h-32 items-end gap-1.5" role="group" aria-label={emptyLabel}>
        {points.map((point) => (
          <div key={point.key} className="group flex h-full flex-1 flex-col justify-end">
            <div
              role="img"
              aria-label={`${point.label}: ${valueLabel(point.value)}`}
              title={`${point.label}: ${valueLabel(point.value)}`}
              className={clsx(
                "w-full rounded-t transition-colors group-hover:opacity-100",
                point.value === 0 ? "bg-surface-2" : `${color} opacity-85`,
              )}
              style={{ height: `${Math.max((point.value / max) * 100, point.value ? 6 : 2)}%` }}
            />
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-subdued">
        <span>{points[0]?.shortLabel}</span>
        <span>{points[Math.floor(points.length / 2)]?.shortLabel}</span>
        <span>{points[points.length - 1]?.shortLabel}</span>
      </div>
    </div>
  );
}

function Distribution({
  rows,
  emptyLabel,
  dot,
}: {
  rows: { id: string; label: string; count: number; dotClass?: string }[];
  emptyLabel: string;
  dot?: boolean;
}) {
  const visible = rows.filter((row) => row.count > 0);
  if (visible.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-line-strong px-3 py-6 text-center text-xs text-subdued">
        {emptyLabel}
      </p>
    );
  }
  const max = Math.max(1, ...visible.map((row) => row.count));
  return (
    <ul className="space-y-2.5">
      {visible.map((row) => (
        <li key={row.id} className="flex items-center gap-3">
          <span className="flex w-28 shrink-0 items-center gap-2 truncate text-[13px] text-muted" title={row.label}>
            {dot && <span className={clsx("h-1.5 w-1.5 shrink-0 rounded-full", row.dotClass)} aria-hidden />}
            <span className="truncate">{row.label}</span>
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full rounded-full bg-accent/75"
              style={{ width: `${Math.max((row.count / max) * 100, 4)}%` }}
            />
          </div>
          <span className="w-8 text-right text-[13px] font-medium text-fg tabular-nums">{row.count}</span>
        </li>
      ))}
    </ul>
  );
}

export function AnalyticsPage() {
  const query = useAnalytics();
  const [trend, setTrend] = useState<"weekly" | "monthly">("weekly");

  if (query.isLoading) return <LoadingBlock label="Computing analytics…" />;
  if (query.isError) {
    return (
      <ErrorState message="Analytics could not be loaded." onRetry={() => void query.refetch()} />
    );
  }

  const data: Analytics = query.data!;
  const trendPoints =
    trend === "weekly"
      ? data.applications_weekly.map((point) => ({
          key: point.week,
          label: `Week of ${formatDate(point.week)}`,
          shortLabel: formatDate(point.week),
          value: point.count,
        }))
      : data.applications_monthly.map((point) => ({
          key: point.month,
          label: formatMonth(point.month),
          shortLabel: formatMonth(point.month),
          value: point.count,
        }));

  const taskPoints = data.tasks_completed_weekly.map((point) => ({
    key: point.week,
    label: `Week of ${formatDate(point.week)}`,
    shortLabel: formatDate(point.week),
    value: point.count,
  }));

  const timePoints = data.time_logged_weekly.map((point) => ({
    key: point.week,
    label: `Week of ${formatDate(point.week)}`,
    shortLabel: formatDate(point.week),
    value: point.minutes,
  }));

  const followUps = data.follow_up_performance;
  const totalLogged = data.time_logged_weekly.reduce((sum, point) => sum + point.minutes, 0);
  const totalTasks = data.tasks_completed_weekly.reduce((sum, point) => sum + point.count, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        subtitle="Every number here is computed from your own records. Ratios appear only when there is a denominator."
        actions={
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-2 text-xs text-muted">
            <Activity className="h-3.5 w-3.5" aria-hidden />
            Updated {formatRelative(data.generated_at)}
          </span>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Total applications"
          value={data.total_applications}
          hint={`${data.active_applications} active · ${data.submitted} submitted`}
          icon={<BriefcaseBusiness className="h-4 w-4" aria-hidden />}
        />
        <MetricCard
          label="Response rate"
          value={percent(data.response.rate)}
          hint={
            data.response.denominator === 0
              ? "Submit an application first"
              : `${data.response.numerator} of ${data.response.denominator} answered`
          }
          icon={<Send className="h-4 w-4" aria-hidden />}
        />
        <MetricCard
          label="Average days to response"
          value={
            data.average_days_to_response == null
              ? "Not enough data"
              : `${data.average_days_to_response} days`
          }
          hint="Measured from submission to the first recorded response"
          icon={<Clock className="h-4 w-4" aria-hidden />}
        />
        <MetricCard
          label="Average alignment"
          value={
            data.average_alignment == null ? "Not enough data" : data.average_alignment.toFixed(1)
          }
          hint={
            data.resume_alignment.length
              ? `${data.resume_alignment.length} resume ${
                  data.resume_alignment.length === 1 ? "version" : "versions"
                } analysed`
              : "Run the resume analyzer to populate this"
          }
          icon={<Gauge className="h-4 w-4" aria-hidden />}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="p-5">
          <SectionTitle title="Funnel" hint="Conversion at each step, with the raw counts." />
          <div className="mt-5 space-y-5">
            <ConversionRow label="Application → response" metric={data.response} />
            <ConversionRow label="Application → interview" metric={data.interview_conversion} />
            <ConversionRow label="Interview → offer" metric={data.offer_conversion} />
          </div>
        </Card>

        <Card className="p-5 xl:col-span-2">
          <SectionTitle
            title="Applications over time"
            hint="Only applications with a submission date."
            action={
              <SegmentedControl<"weekly" | "monthly">
                ariaLabel="Trend granularity"
                value={trend}
                onChange={setTrend}
                options={[
                  { value: "weekly", label: "Weekly" },
                  { value: "monthly", label: "Monthly" },
                ]}
              />
            }
          />
          <div className="mt-6">
            <Chart
              points={trendPoints}
              valueLabel={(value) => `${value} ${value === 1 ? "application" : "applications"}`}
              color="bg-accent/80"
              emptyLabel="No applications submitted in this window"
            />
          </div>
          <p className="mt-4 flex items-center gap-1.5 text-[11px] text-subdued">
            <TrendingUp className="h-3.5 w-3.5" aria-hidden />
            {trend === "weekly"
              ? "Last 12 weeks, grouped by Monday."
              : "Last 6 months, grouped by calendar month."}
          </p>
        </Card>

        <Card className="p-5">
          <SectionTitle title="By status" hint="Every application currently on file." />
          <div className="mt-4">
            <Distribution
              dot
              emptyLabel="No applications yet"
              rows={STATUS_ORDER.map((status) => ({
                id: status,
                label: STATUS_LABEL[status],
                count: data.by_status.find((row) => row.status === status)?.count ?? 0,
                dotClass: STATUS_DOT[status],
              }))}
            />
          </div>
        </Card>

        <Card className="p-5">
          <SectionTitle title="By company" hint="Where your applications cluster." />
          <div className="mt-4">
            <Distribution
              emptyLabel="No companies with applications"
              rows={data.by_company.map((row) => ({
                id: row.company_id,
                label: row.company_name,
                count: row.count,
              }))}
            />
          </div>
        </Card>

        <Card className="p-5">
          <SectionTitle title="By source" hint="Which channels actually produce applications." />
          <div className="mt-4">
            <Distribution
              emptyLabel="No sources recorded on applications"
              rows={data.by_source.map((row) => ({
                id: row.source,
                label: row.source,
                count: row.count,
              }))}
            />
          </div>
        </Card>

        <Card className="p-5">
          <SectionTitle title="Follow-up performance" hint="Completed on or before the due date." />
          <div className="mt-4 rounded-xl bg-surface-2/50 p-4">
            <p
              className={clsx(
                "font-semibold tracking-tight",
                followUps.rate == null ? "text-lg text-subdued" : "text-3xl text-fg tabular-nums",
              )}
            >
              {percent(followUps.rate)}
            </p>
            <p className="mt-1 text-xs text-muted">
              {followUps.total_due === 0
                ? "No follow-ups were due yet"
                : `${followUps.completed_on_time} of ${followUps.total_due} due follow-ups completed on time`}
            </p>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-[13px]">
            {[
              { label: "Completed", value: followUps.completed, tone: "text-fg" },
              { label: "Pending overdue", value: followUps.pending_overdue, tone: followUps.pending_overdue ? "text-danger" : "text-fg" },
              { label: "Pending", value: followUps.pending, tone: "text-fg" },
              { label: "Skipped", value: followUps.skipped, tone: "text-fg" },
            ].map((row) => (
              <div key={row.label} className="flex items-center justify-between gap-2">
                <dt className="text-muted">{row.label}</dt>
                <dd className={clsx("font-semibold tabular-nums", row.tone)}>{row.value}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card className="p-5">
          <SectionTitle title="Tasks completed" hint="Done tasks per week." />
          <div className="mt-4">
            <Chart
              points={taskPoints}
              valueLabel={(value) => `${value} ${value === 1 ? "task" : "tasks"}`}
              color="bg-teal/75"
              emptyLabel="No tasks completed in this window"
            />
          </div>
          <p className="mt-3 text-[11px] text-subdued">
            {totalTasks === 0 ? "No completions recorded." : `${totalTasks} tasks completed over 12 weeks.`}
          </p>
        </Card>

        <Card className="p-5 xl:col-span-2">
          <SectionTitle title="Time logged" hint="Finished and running sessions, per week." />
          <div className="mt-4">
            <Chart
              points={timePoints}
              valueLabel={(value) => formatMinutes(value)}
              color="bg-accent/70"
              emptyLabel="No time logged in this window"
            />
          </div>
          <p className="mt-3 flex items-center gap-1.5 text-[11px] text-subdued">
            <Timer className="h-3.5 w-3.5" aria-hidden />
            {totalLogged === 0 ? "No sessions recorded yet." : `${formatMinutes(totalLogged)} logged over 12 weeks.`}
          </p>
        </Card>

        <Card className="p-5">
          <SectionTitle title="Resume alignment" hint="Average score per resume version." />
          {data.resume_alignment.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                className="py-8"
                icon={<FileSearch className="h-5 w-5" />}
                title="No analyses yet"
                description="Run the analyzer to compare a resume with a job description."
                action={
                  <Link to="/analyzer" className="text-xs font-medium text-accent hover:underline">
                    Open analyzer
                  </Link>
                }
              />
            </div>
          ) : (
            <ul className="mt-4 space-y-3">
              {data.resume_alignment.map((score) => (
                <li key={score.resume_version_id} className="flex items-center gap-3">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium text-fg">
                      {score.resume_name} · v{score.version_no}
                    </span>
                    <span className="text-[11px] text-subdued">
                      {score.label ?? "No label"} · {score.analyses}{" "}
                      {score.analyses === 1 ? "analysis" : "analyses"}
                    </span>
                  </span>
                  <div className="h-2 w-16 shrink-0 overflow-hidden rounded-full bg-surface-2">
                    <div
                      className="h-full rounded-full bg-teal"
                      style={{ width: `${Math.max(0, Math.min(100, score.average_score))}%` }}
                    />
                  </div>
                  <span className="w-8 shrink-0 text-right text-[13px] font-semibold text-fg tabular-nums">
                    {score.average_score.toFixed(0)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-5 xl:col-span-2">
          <SectionTitle
            title="Recent analyses"
            hint="Newest completed comparisons."
            action={
              <Link to="/analyzer" className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">
                Analyzer <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
            }
          />
          {data.analysis_history.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                className="py-8"
                icon={<BarChart3 className="h-5 w-5" />}
                title="No completed analyses"
                description="Alignment history builds up as you run comparisons."
              />
            </div>
          ) : (
            <ul className="mt-4 divide-y divide-line">
              {data.analysis_history.slice(0, 8).map((entry) => (
                <li key={entry.job_id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-soft text-xs font-semibold text-teal tabular-nums">
                    {entry.score}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] text-fg">
                      {entry.resume_name} · v{entry.version_no}
                      {entry.label ? ` — ${entry.label}` : ""}
                    </p>
                    <p className="truncate text-[11px] text-subdued">
                      {entry.jd_title ?? "Pasted job description"}
                    </p>
                  </div>
                  <span className="shrink-0 text-[11px] text-subdued">
                    {formatRelative(entry.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card className="p-5">
        <SectionTitle title="How these are calculated" hint="No hidden weighting, no estimates." />
        <dl className="mt-4 grid gap-4 text-xs leading-relaxed sm:grid-cols-2 lg:grid-cols-4">
          {[
            {
              term: "Response rate",
              body: "Applications with any recorded response ÷ applications with a submission date.",
            },
            {
              term: "Interview conversion",
              body: "Applications that reached interviewing or beyond ÷ applications submitted.",
            },
            {
              term: "Offer conversion",
              body: "Offers ÷ applications that reached an interview.",
            },
            {
              term: "Follow-up performance",
              body: "Follow-ups completed on or before their due date ÷ follow-ups that were due.",
            },
          ].map((item) => (
            <div key={item.term}>
              <dt className="flex items-center gap-1.5 font-medium text-fg">
                <Target className="h-3.5 w-3.5 text-subdued" aria-hidden />
                {item.term}
              </dt>
              <dd className="mt-1 text-muted">{item.body}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 flex items-start gap-1.5 rounded-lg bg-surface-2/60 px-3 py-2 text-[11px] text-subdued">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          When a denominator is zero the ratio shows “Not enough data” rather than 0%. Alignment is
          never presented as a hiring probability.
        </p>
      </Card>

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { label: "Applications interviewed", value: data.interview_conversion.numerator, icon: <CalendarCheck className="h-4 w-4" />, link: "/interviews" },
          { label: "Tasks completed", value: totalTasks, icon: <ListTodo className="h-4 w-4" />, link: "/tasks" },
          { label: "Applications answered", value: data.response.numerator, icon: <Send className="h-4 w-4" />, link: "/applications" },
        ].map((item) => (
          <Link
            key={item.label}
            to={item.link}
            className="surface flex items-center justify-between gap-3 px-4 py-3 text-sm text-muted transition-colors hover:border-line-strong hover:text-fg"
          >
            <span className="flex items-center gap-2">
              <span className="text-subdued">{item.icon}</span>
              {item.label}
            </span>
            <span className="flex items-center gap-1.5 font-semibold text-fg tabular-nums">
              {item.value}
              <ArrowRight className="h-3.5 w-3.5 text-subdued" aria-hidden />
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
