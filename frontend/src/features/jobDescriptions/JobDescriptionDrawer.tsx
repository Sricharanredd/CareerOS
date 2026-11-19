import clsx from "clsx";
import {
  Archive,
  ArchiveRestore,
  Building2,
  Download,
  FileText,
  Link2,
  MapPin,
  Pencil,
  Trash2,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState, InlineAlert, LoadingBlock } from "@/components/ui/Feedback";
import { ConfirmDialog, Drawer } from "@/components/ui/Overlay";
import { useToast } from "@/components/ui/Toast";
import { downloadFile, errorMessage } from "@/lib/api";
import { formatDateTime, labelize } from "@/lib/format";
import {
  useArchiveJobDescription,
  useDeleteJobDescription,
  useJobDescription,
} from "@/lib/queries";
import type { JobDescription } from "@/lib/types";

export function JobDescriptionDrawer({
  jobDescriptionId,
  onClose,
  onEdit,
}: {
  jobDescriptionId: string | null;
  onClose: () => void;
  onEdit: (job: JobDescription) => void;
}) {
  const query = useJobDescription(jobDescriptionId);
  const archive = useArchiveJobDescription(jobDescriptionId ?? "");
  const remove = useDeleteJobDescription(jobDescriptionId ?? "");
  const toast = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const job = query.data;
  const isArchived = Boolean(job?.archived_at);

  async function toggleArchive() {
    if (!job) return;
    try {
      await archive.mutateAsync(!isArchived);
      toast.success(isArchived ? "Job description restored." : "Job description archived.");
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function performDelete() {
    try {
      await remove.mutateAsync();
      toast.success("Job description deleted.");
      setConfirmDelete(false);
      onClose();
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function downloadSource() {
    if (!job?.source_file_id) return;
    try {
      await downloadFile(`/files/${job.source_file_id}/download`, "job-description");
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  return (
    <Drawer
      open={Boolean(jobDescriptionId)}
      onClose={onClose}
      width="max-w-2xl"
      title={job?.title ?? "Job description"}
      subtitle={
        job && (
          <span className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5">
              <Building2 className="h-3.5 w-3.5" aria-hidden />
              {job.company.name}
            </span>
            {job.seniority && <Badge tone="outline">{job.seniority}</Badge>}
            {isArchived && <Badge tone="neutral">Archived</Badge>}
          </span>
        )
      }
      footer={
        job && (
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
                icon={isArchived ? <ArchiveRestore className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
                loading={archive.isPending}
                onClick={() => void toggleArchive()}
              >
                {isArchived ? "Restore" : "Archive"}
              </Button>
            </div>
            <Button variant="secondary" onClick={() => job && onEdit(job)}>
              <Pencil className="h-4 w-4" aria-hidden />
              Edit
            </Button>
          </>
        )
      }
    >
      {query.isLoading && <LoadingBlock label="Loading job description…" />}
      {query.isError && (
        <ErrorState message="This job description could not be loaded." onRetry={() => void query.refetch()} />
      )}
      {job && (
        <div className="space-y-6">
          {isArchived && (
            <InlineAlert tone="warning" title="Archived">
              This job description is archived. Restore it to use it in new applications.
            </InlineAlert>
          )}

          <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
            <div>
              <dt className="text-[11px] font-medium uppercase tracking-wide text-subdued">Location</dt>
              <dd className="mt-1 flex items-center gap-1.5 text-sm text-fg">
                <MapPin className="h-3.5 w-3.5 text-subdued" aria-hidden />
                {job.location ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium uppercase tracking-wide text-subdued">Employment</dt>
              <dd className="mt-1 text-sm text-fg">
                {job.employment_type ? labelize(job.employment_type) : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium uppercase tracking-wide text-subdued">Posting</dt>
              <dd className="mt-1 text-sm">
                {job.url ? (
                  <a
                    href={job.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="inline-flex items-center gap-1 text-accent hover:underline"
                  >
                    Open original <Link2 className="h-3 w-3" />
                  </a>
                ) : (
                  <span className="text-subdued">—</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium uppercase tracking-wide text-subdued">Updated</dt>
              <dd className="mt-1 text-sm text-fg">{formatDateTime(job.updated_at)}</dd>
            </div>
          </dl>

          {(job.required_skills?.length || job.preferred_skills?.length) && (
            <div className="space-y-3">
              {job.required_skills?.length ? (
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-wide text-subdued">
                    Required skills
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {job.required_skills.map((skill) => (
                      <Badge key={skill} tone="accent">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
              {job.preferred_skills?.length ? (
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-wide text-subdued">
                    Preferred skills
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {job.preferred_skills.map((skill) => (
                      <Badge key={skill} tone="teal">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          )}

          {job.responsibilities?.length ? (
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-subdued">
                Responsibilities
              </p>
              <ul className="mt-1.5 space-y-1.5">
                {job.responsibilities.map((item) => (
                  <li key={item} className="flex gap-2 text-sm text-fg">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" aria-hidden />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div>
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-medium uppercase tracking-wide text-subdued">
                Job description text
              </p>
              <span className="text-[11px] text-subdued">{job.raw_text.length.toLocaleString()} characters</span>
            </div>
            <div
              className={clsx(
                "scroll-area mt-1.5 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-xl border border-line bg-surface-2/40 p-3.5 text-[13px] leading-relaxed text-fg",
                !job.raw_text && "text-subdued",
              )}
            >
              {job.raw_text || "No text captured."}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              {job.source_file_id && (
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Download className="h-3.5 w-3.5" />}
                  onClick={() => void downloadSource()}
                >
                  Download source file
                </Button>
              )}
              <span className="inline-flex items-center gap-1 text-[11px] text-subdued">
                <FileText className="h-3 w-3" aria-hidden />
                Stored for future fit analysis
              </span>
            </div>
          </div>

          {job.notes && (
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-subdued">Private notes</p>
              <p className="mt-1.5 whitespace-pre-wrap rounded-xl border border-line bg-surface-2/40 p-3.5 text-sm leading-relaxed text-fg">
                {job.notes}
              </p>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => void performDelete()}
        loading={remove.isPending}
        title="Delete this job description?"
        description="Applications linked to it will keep their history but lose the job description reference. This cannot be undone."
        confirmLabel="Delete job description"
      />
    </Drawer>
  );
}
