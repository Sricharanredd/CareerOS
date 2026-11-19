import clsx from "clsx";
import {
  ArrowRight,
  BriefcaseBusiness,
  ChevronRight,
  Columns3,
  Filter,
  Plus,
  RotateCcw,
  Search,
  Table2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Checkbox, Input, Select } from "@/components/ui/Form";
import { PageHeader } from "@/components/ui/Layout";
import { SegmentedControl } from "@/components/ui/Tabs";
import { ApplicationDrawer } from "@/features/applications/ApplicationDrawer";
import { ApplicationFormModal } from "@/features/applications/ApplicationFormModal";
import {
  ACTIVE_STATUSES,
  APPLICATION_SORTS,
  PAGE_SIZE,
  STATUS_DOT,
  STATUS_LABEL,
  STATUS_ORDER,
  WORK_MODE_LABEL,
} from "@/lib/constants";
import { formatDate, formatRelative, formatSalaryRange, pluralize } from "@/lib/format";
import {
  useApplication,
  useApplicationBoard,
  useApplications,
  useCompanyOptions,
} from "@/lib/queries";
import type { Application, ApplicationStatus, WorkMode } from "@/lib/types";

type View = "list" | "board";

function FollowUpCell({ application }: { application: Application }) {
  if (!application.follow_up_on) return <span className="text-subdued">—</span>;
  const date = new Date(`${application.follow_up_on}T00:00:00`);
  const overdue =
    date.getTime() < Date.now() && !["accepted", "rejected", "withdrawn", "ghosted"].includes(application.status);
  return (
    <span className={clsx("inline-flex items-center gap-1.5 text-[13px]", overdue ? "text-danger" : "text-muted")}>
      {formatDate(application.follow_up_on)}
      {overdue && <span className="rounded-full bg-danger-soft px-1.5 py-0.5 text-[10px] font-semibold">due</span>}
    </span>
  );
}

function ApplicationTable({
  items,
  onOpen,
  loading,
}: {
  items: Application[];
  onOpen: (id: string) => void;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="space-y-2 p-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-12 w-full" />
        ))}
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<BriefcaseBusiness className="h-5 w-5" />}
        title="No applications match"
        description="Try clearing filters, or add the first role you are pursuing."
      />
    );
  }

  return (
    <>
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left text-[11px] uppercase tracking-wide text-subdued">
              <th className="px-4 py-3 font-medium">Role</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="hidden px-4 py-3 font-medium lg:table-cell">Mode</th>
              <th className="px-4 py-3 font-medium">Applied</th>
              <th className="hidden px-4 py-3 font-medium md:table-cell">Follow up</th>
              <th className="px-4 py-3 font-medium">Updated</th>
              <th className="w-10 px-2 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {items.map((application) => (
              <tr
                key={application.id}
                onClick={() => onOpen(application.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onOpen(application.id);
                  }
                }}
                tabIndex={0}
                className="group cursor-pointer transition-colors hover:bg-surface-2/60 focus-visible:bg-surface-2/60 focus-visible:outline-none"
              >
                <td className="max-w-72 px-4 py-3">
                  <p className="truncate font-medium text-fg group-hover:text-accent">{application.title}</p>
                  <p className="truncate text-xs text-muted">{application.company.name}</p>
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={application.status} />
                </td>
                <td className="hidden px-4 py-3 text-[13px] text-muted lg:table-cell">
                  {application.work_mode ? WORK_MODE_LABEL[application.work_mode] : "—"}
                </td>
                <td className="px-4 py-3 text-[13px] text-muted">
                  {formatDate(application.applied_on)}
                </td>
                <td className="hidden px-4 py-3 md:table-cell">
                  <FollowUpCell application={application} />
                </td>
                <td className="px-4 py-3 text-[13px] text-subdued">
                  {formatRelative(application.updated_at)}
                </td>
                <td className="px-2 py-3 text-subdued">
                  <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="divide-y divide-line sm:hidden">
        {items.map((application) => (
          <li key={application.id}>
            <button
              type="button"
              onClick={() => onOpen(application.id)}
              className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-surface-2/60"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-fg">{application.title}</p>
                <p className="truncate text-xs text-muted">{application.company.name}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <StatusBadge status={application.status} />
                  <span className="text-[11px] text-subdued">{formatDate(application.applied_on)}</span>
                </div>
              </div>
              <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-subdued" />
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

function ApplicationBoard({
  includeArchived,
  onOpen,
}: {
  includeArchived: boolean;
  onOpen: (id: string) => void;
}) {
  const query = useApplicationBoard(includeArchived);

  if (query.isLoading) {
    return (
      <div className="flex gap-3 overflow-x-auto p-4">
        {STATUS_ORDER.slice(0, 5).map((status) => (
          <div key={status} className="w-64 shrink-0 space-y-2">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ))}
      </div>
    );
  }
  if (query.isError) {
    return <ErrorState message="The board could not be loaded." onRetry={() => void query.refetch()} />;
  }

  const columns = query.data?.columns ?? [];
  const total = columns.reduce((sum, column) => sum + column.count, 0);

  if (total === 0) {
    return (
      <EmptyState
        icon={<Columns3 className="h-5 w-5" />}
        title="The board is empty"
        description="Add an application to see it move through the pipeline."
      />
    );
  }

  return (
    <div className="scroll-area flex gap-3 overflow-x-auto p-4">
      {columns.map((column) => (
        <section key={column.status} className="w-64 shrink-0">
          <header className="mb-2 flex items-center justify-between px-1">
            <span className="flex items-center gap-1.5 text-[13px] font-medium text-fg">
              <span className={clsx("h-1.5 w-1.5 rounded-full", STATUS_DOT[column.status])} aria-hidden />
              {STATUS_LABEL[column.status]}
            </span>
            <span className="rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] font-semibold text-subdued">
              {column.count}
            </span>
          </header>
          <div className="space-y-2">
            {column.items.length === 0 && (
              <div className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-[11px] text-subdued">
                Nothing here
              </div>
            )}
            {column.items.map((application) => (
              <button
                key={application.id}
                type="button"
                onClick={() => onOpen(application.id)}
                className="w-full rounded-xl border border-line bg-surface p-3 text-left shadow-card transition-colors hover:border-line-strong hover:bg-surface-2/50"
              >
                <p className="line-clamp-2 text-[13px] font-medium leading-snug text-fg">
                  {application.title}
                </p>
                <p className="mt-0.5 truncate text-[11px] text-muted">{application.company.name}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-subdued">
                  {application.work_mode && (
                    <span className="rounded border border-line px-1.5 py-0.5">
                      {WORK_MODE_LABEL[application.work_mode]}
                    </span>
                  )}
                  {application.follow_up_on && (
                    <span className="rounded border border-warning/30 bg-warning-soft px-1.5 py-0.5 text-warning">
                      Follow up {formatDate(application.follow_up_on)}
                    </span>
                  )}
                  {application.salary_max && (
                    <span className="truncate">
                      {formatSalaryRange(
                        application.salary_min,
                        application.salary_max,
                        application.salary_currency,
                        application.salary_period,
                      )}
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

export function ApplicationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const [view, setView] = useState<View>(searchParams.get("view") === "board" ? "board" : "list");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<ApplicationStatus | "">("");
  const [companyId, setCompanyId] = useState("");
  const [workMode, setWorkMode] = useState<WorkMode | "">("");
  const [sort, setSort] = useState("-created_at");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [page, setPage] = useState(1);

  const [formOpen, setFormOpen] = useState(searchParams.get("new") === "1");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(searchParams.get("open"));

  const companies = useCompanyOptions();
  const query = useApplications({
    search,
    status: status ? [status] : undefined,
    company_id: companyId || undefined,
    work_mode: workMode || undefined,
    include_archived: includeArchived,
    sort,
    page,
    page_size: PAGE_SIZE,
  });
  const editingQuery = useApplication(editingId);

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    setPage(1);
  }, [status, companyId, workMode, includeArchived, sort]);

  useEffect(() => {
    if (openId === null && searchParams.get("open")) {
      const next = new URLSearchParams(searchParams);
      next.delete("open");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId]);

  useEffect(() => {
    if (formOpen || editingId) return;
    if (searchParams.get("new") !== "1") return;
    const next = new URLSearchParams(searchParams);
    next.delete("new");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formOpen, editingId]);

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filtersActive =
    Boolean(search || status || companyId || workMode || includeArchived) || sort !== "-created_at";

  const activeCount = useMemo(
    () => items.filter((item) => ACTIVE_STATUSES.includes(item.status)).length,
    [items],
  );

  function changeView(next: View) {
    setView(next);
    const params = new URLSearchParams(searchParams);
    if (next === "board") params.set("view", "board");
    else params.delete("view");
    setSearchParams(params, { replace: true });
  }

  function resetFilters() {
    setSearchInput("");
    setSearch("");
    setStatus("");
    setCompanyId("");
    setWorkMode("");
    setSort("-created_at");
    setIncludeArchived(false);
    setPage(1);
  }

  function openApplication(id: string) {
    setOpenId(id);
  }

  function closeDrawer() {
    setOpenId(null);
    const params = new URLSearchParams(searchParams);
    params.delete("open");
    setSearchParams(params, { replace: true });
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Applications"
        subtitle={
          query.data
            ? `${pluralize(total, "application")} tracked · ${activeCount} active on this page`
            : "Every role you are pursuing, in one pipeline."
        }
        actions={
          <>
            <SegmentedControl<View>
              ariaLabel="View applications as"
              value={view}
              onChange={changeView}
              options={[
                { value: "list", label: "List", icon: <Table2 className="h-3.5 w-3.5" /> },
                { value: "board", label: "Board", icon: <Columns3 className="h-3.5 w-3.5" /> },
              ]}
            />
            <Button
              variant="primary"
              icon={<Plus className="h-4 w-4" />}
              onClick={() => {
                setEditingId(null);
                setFormOpen(true);
              }}
            >
              New application
            </Button>
          </>
        }
      />

      <div className="surface overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-line p-3 lg:flex-row lg:items-center">
          {view === "list" && (
            <>
              <div className="relative min-w-48 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subdued" aria-hidden />
                <Input
                  className="pl-9"
                  placeholder="Search roles, companies, notes…"
                  maxLength={120}
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
                <Select
                  className="sm:w-40"
                  aria-label="Filter by status"
                  value={status}
                  onChange={(event) => setStatus(event.target.value as ApplicationStatus | "")}
                >
                  <option value="">All statuses</option>
                  {STATUS_ORDER.map((option) => (
                    <option key={option} value={option}>
                      {STATUS_LABEL[option]}
                    </option>
                  ))}
                </Select>
                <Select
                  className="sm:w-44"
                  aria-label="Filter by company"
                  value={companyId}
                  onChange={(event) => setCompanyId(event.target.value)}
                >
                  <option value="">All companies</option>
                  {companies.data?.map((company) => (
                    <option key={company.id} value={company.id}>
                      {company.name}
                    </option>
                  ))}
                </Select>
                <Select
                  className="sm:w-36"
                  aria-label="Filter by work mode"
                  value={workMode}
                  onChange={(event) => setWorkMode(event.target.value as WorkMode | "")}
                >
                  <option value="">Any mode</option>
                  {(Object.keys(WORK_MODE_LABEL) as WorkMode[]).map((mode) => (
                    <option key={mode} value={mode}>
                      {WORK_MODE_LABEL[mode]}
                    </option>
                  ))}
                </Select>
                <Select
                  className="sm:w-44"
                  aria-label="Sort applications"
                  value={sort}
                  onChange={(event) => setSort(event.target.value)}
                >
                  {APPLICATION_SORTS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </div>
            </>
          )}
          <div className="flex items-center gap-3">
            <Checkbox
              label="Archived"
              checked={includeArchived}
              onChange={(event) => setIncludeArchived(event.target.checked)}
            />
            {view === "list" && filtersActive && (
              <Button size="sm" variant="ghost" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={resetFilters}>
                Reset
              </Button>
            )}
          </div>
        </div>

        {view === "list" ? (
          query.isError ? (
            <ErrorState message="Applications could not be loaded." onRetry={() => void query.refetch()} />
          ) : (
            <ApplicationTable items={items} onOpen={openApplication} loading={query.isLoading} />
          )
        ) : (
          <ApplicationBoard includeArchived={includeArchived} onOpen={openApplication} />
        )}

        {view === "list" && total > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-xs text-muted">
            <span>
              Page {page} of {totalPages} · {pluralize(total, "result")}
            </span>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                Previous
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              </Button>
            </div>
          </div>
        )}
      </div>

      <p className="flex items-center gap-1.5 text-[11px] text-subdued">
        <Filter className="h-3 w-3" aria-hidden />
        Click any row to open its timeline. Filters apply to the list view; the board always shows the full pipeline.
      </p>

      <ApplicationFormModal
        open={formOpen && (!editingId || Boolean(editingQuery.data))}
        onClose={() => {
          setFormOpen(false);
          setEditingId(null);
        }}
        application={editingId ? editingQuery.data ?? null : null}
      />

      <ApplicationDrawer
        applicationId={editingId ? null : openId}
        onClose={closeDrawer}
        onEdit={() => {
          if (openId) {
            setEditingId(openId);
            setFormOpen(true);
          }
        }}
      />
    </div>
  );
}
