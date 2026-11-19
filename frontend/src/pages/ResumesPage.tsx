import clsx from "clsx";
import { FileText, Plus, Search, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Input, Toggle } from "@/components/ui/Form";
import { PageHeader } from "@/components/ui/Layout";
import { ResumeDrawer } from "@/features/resumes/ResumeDrawer";
import {
  ResumeCreateModal,
  ResumeVersionModal,
  VersionEditModal,
} from "@/features/resumes/ResumeModals";
import { formatRelative, pluralize } from "@/lib/format";
import { useResumes } from "@/lib/queries";
import type { Resume, ResumeDetail, ResumeVersion } from "@/lib/types";

function ResumeCard({ resume, onOpen }: { resume: Resume; onOpen: () => void }) {
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
          <p className="truncate text-sm font-semibold text-fg group-hover:text-accent">{resume.name}</p>
          <p className="mt-0.5 truncate text-xs text-muted">{resume.headline ?? "No headline"}</p>
        </div>
        {resume.archived_at && <Badge tone="neutral">Archived</Badge>}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <Badge tone="accent">{pluralize(resume.version_count, "version")}</Badge>
        {resume.current_version_no != null && (
          <Badge tone="success">v{resume.current_version_no} current</Badge>
        )}
      </div>

      <p className="mt-3 flex flex-1 items-center gap-1.5 truncate text-xs text-subdued">
        <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden />
        {resume.current_file_name ?? "No file uploaded"}
      </p>

      <p className="mt-3 border-t border-line pt-2.5 text-[11px] text-subdued">
        Updated {formatRelative(resume.updated_at)}
      </p>
    </button>
  );
}

export function ResumesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [openId, setOpenId] = useState<string | null>(searchParams.get("open"));
  const [versionResume, setVersionResume] = useState<ResumeDetail | null>(null);
  const [editVersion, setEditVersion] = useState<{ resumeId: string; version: ResumeVersion } | null>(null);
  const [returnToId, setReturnToId] = useState<string | null>(null);

  const query = useResumes({ search, include_archived: includeArchived });

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

  function closeDrawer() {
    setOpenId(null);
    if (searchParams.get("open")) {
      const next = new URLSearchParams(searchParams);
      next.delete("open");
      setSearchParams(next, { replace: true });
    }
  }

  function reopenDrawer(id: string | null) {
    if (id) setOpenId(id);
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Resumes"
        subtitle={
          query.data
            ? `${pluralize(query.data.total, "resume")} and every version you have sent`
            : "Keep tailored versions of your resume, with notes and downloadable files."
        }
        actions={
          <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setCreateOpen(true)}>
            Upload resume
          </Button>
        }
      />

      <div className="surface flex flex-col gap-3 p-3 sm:flex-row sm:items-center">
        <div className="relative min-w-48 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subdued" aria-hidden />
          <Input
            className="pl-9"
            placeholder="Search by name or headline…"
            maxLength={120}
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
        </div>
        <Toggle checked={includeArchived} onChange={setIncludeArchived} label="Show archived" />
      </div>

      {query.isLoading && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full" />
          ))}
        </div>
      )}

      {query.isError && (
        <div className="surface">
          <ErrorState message="Resumes could not be loaded." onRetry={() => void query.refetch()} />
        </div>
      )}

      {!query.isLoading && !query.isError && items.length === 0 && (
        <div className="surface">
          <EmptyState
            icon={<Upload className="h-5 w-5" />}
            title={search ? "No resumes match" : "No resumes yet"}
            description={
              search
                ? "Try a different search term."
                : "Upload your base resume first. You can add tailored versions as applications go out."
            }
            action={
              !search ? (
                <Button variant="primary" icon={<Upload className="h-4 w-4" />} onClick={() => setCreateOpen(true)}>
                  Upload your resume
                </Button>
              ) : undefined
            }
          />
        </div>
      )}

      {items.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((resume) => (
            <ResumeCard key={resume.id} resume={resume} onOpen={() => setOpenId(resume.id)} />
          ))}
        </div>
      )}

      <ResumeCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(created) => setOpenId(created.id)}
      />

      <ResumeDrawer
        resumeId={openId}
        onClose={closeDrawer}
        onAddVersion={(resume) => {
          setReturnToId(resume.id);
          setOpenId(null);
          setVersionResume(resume);
        }}
        onEditVersion={(resumeId, version) => {
          setReturnToId(resumeId);
          setOpenId(null);
          setEditVersion({ resumeId, version });
        }}
      />

      <ResumeVersionModal
        open={Boolean(versionResume)}
        resume={versionResume}
        onClose={() => {
          setVersionResume(null);
          reopenDrawer(returnToId);
          setReturnToId(null);
        }}
      />

      <VersionEditModal
        open={Boolean(editVersion)}
        resumeId={editVersion?.resumeId ?? ""}
        version={editVersion?.version ?? null}
        onClose={() => {
          setEditVersion(null);
          reopenDrawer(returnToId);
          setReturnToId(null);
        }}
      />
    </div>
  );
}
