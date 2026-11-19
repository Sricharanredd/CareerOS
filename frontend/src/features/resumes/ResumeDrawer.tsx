import clsx from "clsx";
import {
  Archive,
  ArchiveRestore,
  CheckCircle2,
  Download,
  FileText,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState, InlineAlert, LoadingBlock } from "@/components/ui/Feedback";
import { ConfirmDialog, Drawer } from "@/components/ui/Overlay";
import { useToast } from "@/components/ui/Toast";
import { downloadFile, errorMessage } from "@/lib/api";
import { formatDate, formatDateTime, pluralize } from "@/lib/format";
import {
  useArchiveResume,
  useDeleteResume,
  useResume,
  useResumeUsage,
  useSetCurrentVersion,
} from "@/lib/queries";
import type { ResumeDetail, ResumeVersion } from "@/lib/types";

export function ResumeDrawer({
  resumeId,
  onClose,
  onAddVersion,
  onEditVersion,
}: {
  resumeId: string | null;
  onClose: () => void;
  onAddVersion: (resume: ResumeDetail) => void;
  onEditVersion: (resumeId: string, version: ResumeVersion) => void;
}) {
  const query = useResume(resumeId);
  const usage = useResumeUsage(resumeId);
  const archive = useArchiveResume(resumeId ?? "");
  const remove = useDeleteResume(resumeId ?? "");
  const setCurrent = useSetCurrentVersion(resumeId ?? "");
  const toast = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const resume = query.data;
  const isArchived = Boolean(resume?.archived_at);
  const inUse = Boolean(usage.data && (usage.data.application_count > 0 || usage.data.analysis_count > 0));

  async function toggleArchive() {
    if (!resume) return;
    try {
      await archive.mutateAsync(!isArchived);
      toast.success(isArchived ? "Resume restored." : "Resume archived.");
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function performDelete() {
    try {
      await remove.mutateAsync();
      toast.success("Resume deleted.");
      setConfirmDelete(false);
      onClose();
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function download(version: ResumeVersion) {
    try {
      await downloadFile(`/files/${version.file_id}/download`, `${resume?.name ?? "resume"}-v${version.version_no}`);
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function makeCurrent(version: ResumeVersion) {
    try {
      await setCurrent.mutateAsync(version.id);
      toast.success(`v${version.version_no} is now the current version.`);
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  return (
    <Drawer
      open={Boolean(resumeId)}
      onClose={onClose}
      width="max-w-2xl"
      title={resume?.name ?? "Resume"}
      subtitle={
        resume && (
          <span className="flex flex-wrap items-center gap-2">
            {resume.headline && <span className="truncate">{resume.headline}</span>}
            <Badge tone="neutral">{pluralize(resume.version_count, "version")}</Badge>
            {isArchived && <Badge tone="neutral">Archived</Badge>}
          </span>
        )
      }
      footer={
        resume && (
          <>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="text-danger hover:bg-danger-soft hover:text-danger"
                icon={<Trash2 className="h-4 w-4" />}
                disabled={inUse}
                onClick={() => setConfirmDelete(true)}
              >
                Delete
              </Button>
              <Button
                variant="ghost"
                size="sm"
                icon={isArchived ? <ArchiveRestore className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
                loading={archive.isPending}
                onClick={() => void toggleArchive()}
              >
                {isArchived ? "Restore" : "Archive"}
              </Button>
            </div>
            <Button
              variant="primary"
              icon={<Plus className="h-4 w-4" />}
              onClick={() => onAddVersion(resume)}
            >
              New version
            </Button>
          </>
        )
      }
    >
      {query.isLoading && <LoadingBlock label="Loading resume…" />}
      {query.isError && <ErrorState message="This resume could not be loaded." onRetry={() => void query.refetch()} />}
      {resume && (
        <div className="space-y-5">
          {isArchived && (
            <InlineAlert tone="warning" title="Archived">
              Archived resumes stay attached to past applications. Restore it to use it again.
            </InlineAlert>
          )}

          {inUse && usage.data && (
            <InlineAlert tone="accent" title="This resume is in use">
              Referenced by {pluralize(usage.data.application_count, "application")}
              {usage.data.analysis_count
                ? ` and ${pluralize(usage.data.analysis_count, "analysis")}`
                : ""}
              . Archive it instead of deleting to keep history intact.
            </InlineAlert>
          )}

          <div>
            <p className="text-[11px] font-medium uppercase tracking-wide text-subdued">Versions</p>
            <ul className="mt-2 space-y-2">
              {resume.versions.map((version) => (
                <li
                  key={version.id}
                  className={clsx(
                    "rounded-xl border p-3.5",
                    version.is_current
                      ? "border-accent/30 bg-accent-soft/40"
                      : "border-line bg-surface-2/40",
                  )}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-fg">
                        <span className="rounded-md border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-muted">
                          v{version.version_no}
                        </span>
                        {version.label ?? "Untitled version"}
                        {version.is_current && (
                          <span className="inline-flex items-center gap-1 text-[11px] font-medium text-success">
                            <CheckCircle2 className="h-3 w-3" aria-hidden />
                            Current
                          </span>
                        )}
                      </p>
                      <p className="mt-1 text-[11px] text-subdued">
                        Uploaded {formatDate(version.created_at)} ·{" "}
                        {version.extracted_chars.toLocaleString()} characters extracted
                      </p>
                      {version.notes && (
                        <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-muted">
                          {version.notes}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-0.5">
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Download className="h-3.5 w-3.5" />}
                        onClick={() => void download(version)}
                      >
                        Download
                      </Button>
                      {!version.is_current && (
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={setCurrent.isPending}
                          onClick={() => void makeCurrent(version)}
                        >
                          Set current
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Pencil className="h-3.5 w-3.5" />}
                        onClick={() => onEditVersion(resume.id, version)}
                      >
                        Edit
                      </Button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div className="flex items-center justify-between rounded-xl border border-line bg-surface-2/40 px-4 py-3 text-sm">
            <span className="flex items-center gap-2 text-muted">
              <FileText className="h-4 w-4" aria-hidden />
              {resume.current_file_name ?? "No current file"}
            </span>
            <span className="text-[11px] text-subdued">Updated {formatDateTime(resume.updated_at)}</span>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => void performDelete()}
        loading={remove.isPending}
        title="Delete this resume?"
        description="All versions and their uploaded files are permanently removed. Applications that reference it keep their notes and timeline."
        confirmLabel="Delete resume"
      />
    </Drawer>
  );
}
