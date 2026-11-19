import clsx from "clsx";
import {
  Building2,
  FileText,
  FileUp,
  MapPin,
  Plus,
  Search,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Input, Select, Toggle } from "@/components/ui/Form";
import { PageHeader } from "@/components/ui/Layout";
import { JobDescriptionDrawer } from "@/features/jobDescriptions/JobDescriptionDrawer";
import { JobDescriptionFormModal } from "@/features/jobDescriptions/JobDescriptionFormModal";
import { formatRelative, pluralize } from "@/lib/format";
import { useCompanyOptions, useJobDescriptions } from "@/lib/queries";
import type { JobDescription, JobDescriptionListItem } from "@/lib/types";

function JobCard({ job, onOpen }: { job: JobDescriptionListItem; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={clsx(
        "group flex h-full flex-col rounded-xl border border-line bg-surface p-4 text-left shadow-card transition-all",
        "hover:-translate-y-0.5 hover:border-line-strong hover:shadow-pop",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-fg group-hover:text-accent">{job.title}</p>
          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
            <Building2 className="h-3.5 w-3.5" aria-hidden />
            {job.company.name}
          </p>
        </div>
        {job.archived_at && <Badge tone="neutral">Archived</Badge>}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {job.seniority && <Badge tone="outline">{job.seniority}</Badge>}
        {job.location && (
          <span className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[11px] text-muted">
            <MapPin className="h-3 w-3" aria-hidden />
            {job.location}
          </span>
        )}
      </div>

      <p className="mt-3 line-clamp-3 flex-1 text-xs leading-relaxed text-subdued">
        {job.text_chars > 0
          ? `${job.text_chars.toLocaleString()} characters captured for analysis.`
          : "No posting text captured yet — open to add it."}
      </p>

      <p className="mt-3 border-t border-line pt-2.5 text-[11px] text-subdued">
        Updated {formatRelative(job.updated_at)}
      </p>
    </button>
  );
}

export function JobDescriptionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<JobDescription | null>(null);
  const [openId, setOpenId] = useState<string | null>(searchParams.get("open"));

  const companies = useCompanyOptions();
  const query = useJobDescriptions({
    search,
    company_id: companyId || undefined,
    include_archived: includeArchived,
  });

  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    if (openId !== null) return;
    if (!searchParams.get("open")) return;
    const next = new URLSearchParams(searchParams);
    next.delete("open");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId]);

  const items = query.data?.items ?? [];

  function openDetails(id: string) {
    setOpenId(id);
  }

  function closeDrawer() {
    setOpenId(null);
    if (searchParams.get("open")) {
      const next = new URLSearchParams(searchParams);
      next.delete("open");
      setSearchParams(next, { replace: true });
    }
  }

  function openCreate() {
    setEditing(null);
    setFormOpen(true);
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Job descriptions"
        subtitle={
          query.data
            ? `${pluralize(query.data.total, "posting")} kept with full text and context`
            : "Keep the postings you care about, ready for comparison."
        }
        actions={
          <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={openCreate}>
            Add job description
          </Button>
        }
      />

      <div className="surface flex flex-col gap-3 p-3 lg:flex-row lg:items-center">
        <div className="relative min-w-48 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subdued" aria-hidden />
          <Input
            className="pl-9"
            placeholder="Search titles, companies, text…"
            maxLength={120}
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Select
            className="w-44"
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
          <Toggle
            checked={includeArchived}
            onChange={setIncludeArchived}
            label="Show archived"
          />
        </div>
      </div>

      {query.isLoading && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-44 w-full" />
          ))}
        </div>
      )}

      {query.isError && (
        <div className="surface">
          <ErrorState message="Job descriptions could not be loaded." onRetry={() => void query.refetch()} />
        </div>
      )}

      {!query.isLoading && !query.isError && items.length === 0 && (
        <div className="surface">
          <EmptyState
            icon={<FileText className="h-5 w-5" />}
            title={search || companyId ? "No postings match" : "No job descriptions yet"}
            description={
              search || companyId
                ? "Adjust the search or company filter to see more."
                : "Paste the text of a role you are pursuing, or import a PDF, to give every application context."
            }
            action={
              !search && !companyId ? (
                <Button variant="primary" icon={<FileUp className="h-4 w-4" />} onClick={openCreate}>
                  Add the first posting
                </Button>
              ) : undefined
            }
          />
        </div>
      )}

      {items.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((job) => (
            <JobCard key={job.id} job={job} onOpen={() => openDetails(job.id)} />
          ))}
        </div>
      )}

      <JobDescriptionFormModal
        open={formOpen}
        onClose={() => {
          setFormOpen(false);
          setEditing(null);
        }}
        jobDescription={editing}
        onCreated={(id) => {
          setOpenId(id);
        }}
      />

      <JobDescriptionDrawer
        jobDescriptionId={openId}
        onClose={closeDrawer}
        onEdit={(job) => {
          setOpenId(null);
          setEditing(job);
          setFormOpen(true);
        }}
      />
    </div>
  );
}
