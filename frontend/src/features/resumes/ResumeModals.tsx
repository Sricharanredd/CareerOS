import { FileUp, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { InlineAlert } from "@/components/ui/Feedback";
import { Field, Input, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Overlay";
import { useToast } from "@/components/ui/Toast";
import { errorMessage, fieldErrors } from "@/lib/api";
import {
  useAddResumeVersion,
  useCreateResume,
  useUpdateResumeVersion,
} from "@/lib/queries";
import type { ResumeDetail, ResumeVersion } from "@/lib/types";

function FilePicker({
  file,
  onFile,
  inputRef,
}: {
  file: File | null;
  onFile: (file: File | null) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}) {
  if (file) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface-2/60 px-3.5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <FileUp className="h-4 w-4 shrink-0 text-accent" aria-hidden />
          <span className="truncate text-sm text-fg">{file.name}</span>
          <span className="shrink-0 text-xs text-subdued">{(file.size / 1024).toFixed(0)} KB</span>
        </div>
        <button
          type="button"
          aria-label="Remove file"
          className="rounded p-1 text-subdued hover:bg-surface-3 hover:text-fg"
          onClick={() => {
            onFile(null);
            if (inputRef.current) inputRef.current.value = "";
          }}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    );
  }
  return (
    <label className="flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-line-strong bg-surface-2/40 px-4 py-8 text-center transition-colors hover:border-accent hover:bg-accent-soft/40">
      <FileUp className="h-5 w-5 text-muted" aria-hidden />
      <span className="text-sm font-medium text-fg">Choose a file</span>
      <span className="text-xs text-subdued">PDF, DOCX or TXT · up to 5 MB</span>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
        className="sr-only"
        onChange={(event) => onFile(event.target.files?.[0] ?? null)}
      />
    </label>
  );
}

export function ResumeCreateModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated?: (resume: ResumeDetail) => void;
}) {
  const create = useCreateResume();
  const toast = useToast();
  const [name, setName] = useState("");
  const [headline, setHeadline] = useState("");
  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setName("");
    setHeadline("");
    setLabel("");
    setNotes("");
    setFile(null);
    setError(null);
    setErrors({});
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setErrors({});
    if (!name.trim()) return setError("Give the resume a name, e.g. “Product — 2026”.");
    if (!file) return setError("Choose a PDF, DOCX or TXT file to upload.");
    try {
      const created = await create.mutateAsync({
        name: name.trim(),
        file,
        headline: headline.trim() || undefined,
        label: label.trim() || undefined,
        notes: notes.trim() || undefined,
      });
      toast.success("Resume uploaded.");
      onCreated?.(created);
      onClose();
    } catch (caught) {
      setErrors(fieldErrors(caught));
      setError(errorMessage(caught));
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="md"
      title="Upload resume"
      description="Each resume keeps every version as an immutable snapshot."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="resume-create-form" loading={create.isPending}>
            Upload resume
          </Button>
        </>
      }
    >
      <form id="resume-create-form" className="space-y-5" onSubmit={(event) => void submit(event)} noValidate>
        {error && <InlineAlert tone="danger">{error}</InlineAlert>}
        <Field label="Resume name" required hint="Used to tell versions apart, e.g. “Backend — core”." error={errors.name}>
          <Input
            autoFocus
            maxLength={200}
            placeholder="Product — 2026"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label="Headline" hint="Optional. The positioning of this resume.">
          <Input
            maxLength={250}
            placeholder="Senior product leader · fintech"
            value={headline}
            onChange={(event) => setHeadline(event.target.value)}
          />
        </Field>
        <div>
          <p className="mb-1.5 text-[13px] font-medium text-fg">
            File <span className="text-danger">*</span>
          </p>
          <FilePicker file={file} onFile={setFile} inputRef={inputRef} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Version label">
            <Input
              maxLength={120}
              placeholder="Tailored for fintech"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
            />
          </Field>
          <Field label="Private notes">
            <Input
              maxLength={200}
              placeholder="What changed in this version"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </Field>
        </div>
      </form>
    </Modal>
  );
}

export function ResumeVersionModal({
  open,
  onClose,
  resume,
}: {
  open: boolean;
  onClose: () => void;
  resume: ResumeDetail | null;
}) {
  const addVersion = useAddResumeVersion(resume?.id ?? "");
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [makeCurrent, setMakeCurrent] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setFile(null);
    setLabel("");
    setNotes("");
    setMakeCurrent(true);
    setError(null);
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!file) return setError("Choose a file to upload as the new version.");
    try {
      await addVersion.mutateAsync({
        file,
        label: label.trim() || undefined,
        notes: notes.trim() || undefined,
        makeCurrent,
      });
      toast.success("New resume version added.");
      onClose();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  const nextVersion = (resume?.versions[0]?.version_no ?? 0) + 1;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="md"
      title={`New version · v${nextVersion}`}
      description={resume ? `${resume.name} keeps earlier versions unchanged.` : undefined}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={addVersion.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="resume-version-form" loading={addVersion.isPending}>
            Add version
          </Button>
        </>
      }
    >
      <form id="resume-version-form" className="space-y-5" onSubmit={(event) => void submit(event)} noValidate>
        {error && <InlineAlert tone="danger">{error}</InlineAlert>}
        <div>
          <p className="mb-1.5 text-[13px] font-medium text-fg">
            File <span className="text-danger">*</span>
          </p>
          <FilePicker file={file} onFile={setFile} inputRef={inputRef} />
        </div>
        <Field label="Version label">
          <Input
            maxLength={120}
            placeholder="Tailored for platform roles"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
          />
        </Field>
        <Field label="Notes">
          <Textarea
            rows={3}
            maxLength={20000}
            placeholder="What is different in this version?"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>
        <label className="flex items-center gap-2.5 text-sm text-fg">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-line-strong accent-[var(--accent)]"
            checked={makeCurrent}
            onChange={(event) => setMakeCurrent(event.target.checked)}
          />
          Make this the current version
        </label>
      </form>
    </Modal>
  );
}

export function VersionEditModal({
  open,
  onClose,
  resumeId,
  version,
}: {
  open: boolean;
  onClose: () => void;
  resumeId: string;
  version: ResumeVersion | null;
}) {
  const update = useUpdateResumeVersion(resumeId);
  const toast = useToast();
  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !version) return;
    setLabel(version.label ?? "");
    setNotes(version.notes ?? "");
    setError(null);
  }, [open, version]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!version) return;
    setError(null);
    try {
      await update.mutateAsync({
        versionId: version.id,
        label: label.trim() || null,
        notes: notes.trim() || null,
      });
      toast.success("Version details updated.");
      onClose();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="sm"
      title={version ? `Edit v${version.version_no}` : "Edit version"}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={update.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="version-edit-form" loading={update.isPending}>
            Save
          </Button>
        </>
      }
    >
      <form id="version-edit-form" className="space-y-4" onSubmit={(event) => void submit(event)} noValidate>
        {error && <InlineAlert tone="danger">{error}</InlineAlert>}
        <Field label="Label">
          <Input maxLength={120} value={label} onChange={(event) => setLabel(event.target.value)} />
        </Field>
        <Field label="Notes">
          <Textarea
            rows={4}
            maxLength={20000}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>
      </form>
    </Modal>
  );
}
