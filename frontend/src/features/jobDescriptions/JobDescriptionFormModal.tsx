import { FileUp, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { CompanyPicker } from "@/features/companies/CompanyPicker";
import { Button } from "@/components/ui/Button";
import { InlineAlert } from "@/components/ui/Feedback";
import { Field, Input, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Overlay";
import { SegmentedControl } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { errorMessage, fieldErrors } from "@/lib/api";
import {
  useCreateJobDescription,
  useCreateJobFromFile,
  useUpdateJobDescription,
} from "@/lib/queries";
import type { JobDescription } from "@/lib/types";

interface FormState {
  company_id: string;
  title: string;
  location: string;
  url: string;
  seniority: string;
  employment_type: string;
  raw_text: string;
  required_skills: string;
  preferred_skills: string;
  responsibilities: string;
  notes: string;
}

const EMPTY: FormState = {
  company_id: "",
  title: "",
  location: "",
  url: "",
  seniority: "",
  employment_type: "",
  raw_text: "",
  required_skills: "",
  preferred_skills: "",
  responsibilities: "",
  notes: "",
};

function orNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function splitList(value: string): string[] | null {
  const items = value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length ? items : null;
}

export function JobDescriptionFormModal({
  open,
  onClose,
  jobDescription,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  jobDescription?: JobDescription | null;
  onCreated?: (id: string) => void;
}) {
  const editing = Boolean(jobDescription);
  const toast = useToast();
  const create = useCreateJobDescription();
  const createFromFile = useCreateJobFromFile();
  const update = useUpdateJobDescription(jobDescription?.id ?? "");

  const [mode, setMode] = useState<"paste" | "upload">("paste");
  const [form, setForm] = useState<FormState>(EMPTY);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    if (jobDescription) {
      setForm({
        company_id: jobDescription.company.id,
        title: jobDescription.title,
        location: jobDescription.location ?? "",
        url: jobDescription.url ?? "",
        seniority: jobDescription.seniority ?? "",
        employment_type: jobDescription.employment_type ?? "",
        raw_text: jobDescription.raw_text,
        required_skills: jobDescription.required_skills?.join(", ") ?? "",
        preferred_skills: jobDescription.preferred_skills?.join(", ") ?? "",
        responsibilities: jobDescription.responsibilities?.join("\n") ?? "",
        notes: jobDescription.notes ?? "",
      });
      setMode("paste");
    } else {
      setForm(EMPTY);
      setTitle("");
      setCompanyId("");
      setFile(null);
      setMode("paste");
    }
    setError(null);
    setErrors({});
  }, [open, jobDescription]);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setErrors({});

    if (editing) {
      if (!form.company_id) return setError("Choose a company.");
      if (!form.title.trim()) return setError("Give the job description a title.");
      try {
        await update.mutateAsync({
          company_id: form.company_id,
          title: form.title.trim(),
          location: orNull(form.location),
          url: orNull(form.url),
          seniority: orNull(form.seniority),
          employment_type: orNull(form.employment_type),
          raw_text: form.raw_text,
          notes: orNull(form.notes),
          required_skills: splitList(form.required_skills),
          preferred_skills: splitList(form.preferred_skills),
          responsibilities: splitList(form.responsibilities.replace(/[,\n]/g, "\n")),
        });
        toast.success("Job description updated.");
        onClose();
      } catch (caught) {
        setErrors(fieldErrors(caught));
        setError(errorMessage(caught));
      }
      return;
    }

    if (mode === "upload") {
      if (!companyId) return setError("Choose a company.");
      if (!title.trim()) return setError("Give the job description a title.");
      if (!file) return setError("Choose a PDF, DOCX or TXT file.");
      try {
        const created = await createFromFile.mutateAsync({
          companyId,
          title: title.trim(),
          file,
        });
        toast.success("Job description imported.");
        onCreated?.(created.id);
        onClose();
      } catch (caught) {
        setErrors(fieldErrors(caught));
        setError(errorMessage(caught));
      }
      return;
    }

    if (!form.company_id) return setError("Choose a company.");
    if (!form.title.trim()) return setError("Give the job description a title.");
    if (!form.raw_text.trim()) return setError("Paste the job description text, or switch to upload.");

    try {
      const created = await create.mutateAsync({
        company_id: form.company_id,
        title: form.title.trim(),
        location: orNull(form.location),
        url: orNull(form.url),
        seniority: orNull(form.seniority),
        employment_type: orNull(form.employment_type),
        raw_text: form.raw_text,
        notes: orNull(form.notes),
        required_skills: splitList(form.required_skills),
        preferred_skills: splitList(form.preferred_skills),
        responsibilities: splitList(form.responsibilities.replace(/[,\n]/g, "\n")),
      });
      toast.success("Job description added.");
      onCreated?.(created.id);
      onClose();
    } catch (caught) {
      setErrors(fieldErrors(caught));
      setError(errorMessage(caught));
    }
  }

  const busy = create.isPending || createFromFile.isPending || update.isPending;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={editing ? "Edit job description" : "Add job description"}
      description={
        editing
          ? "Refine the details kept alongside this role."
          : "Keep the full posting text so future analysis has context."
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="jd-form" loading={busy}>
            {editing ? "Save changes" : mode === "upload" ? "Import file" : "Add job description"}
          </Button>
        </>
      }
    >
      <form id="jd-form" className="space-y-5" onSubmit={(event) => void submit(event)} noValidate>
        {error && <InlineAlert tone="danger">{error}</InlineAlert>}

        {!editing && (
          <SegmentedControl
            ariaLabel="How to add the job description"
            value={mode}
            onChange={setMode}
            options={[
              { value: "paste", label: "Paste text" },
              { value: "upload", label: "Upload file" },
            ]}
          />
        )}

        {!editing && mode === "upload" ? (
          <>
            <CompanyPicker value={companyId} onChange={setCompanyId} error={errors.company_id} />
            <Field label="Role title" required error={errors.title}>
              <Input
                placeholder="e.g. Staff Backend Engineer"
                maxLength={250}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </Field>
            <div>
              <p className="mb-1.5 text-[13px] font-medium text-fg">File</p>
              {file ? (
                <div className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface-2/60 px-3.5 py-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <FileUp className="h-4 w-4 shrink-0 text-accent" aria-hidden />
                    <span className="truncate text-sm text-fg">{file.name}</span>
                    <span className="shrink-0 text-xs text-subdued">
                      {(file.size / 1024).toFixed(0)} KB
                    </span>
                  </div>
                  <button
                    type="button"
                    aria-label="Remove file"
                    className="rounded p-1 text-subdued hover:bg-surface-3 hover:text-fg"
                    onClick={() => {
                      setFile(null);
                      if (fileRef.current) fileRef.current.value = "";
                    }}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <label className="flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-line-strong bg-surface-2/40 px-4 py-8 text-center transition-colors hover:border-accent hover:bg-accent-soft/40">
                  <FileUp className="h-5 w-5 text-muted" aria-hidden />
                  <span className="text-sm font-medium text-fg">Choose a file</span>
                  <span className="text-xs text-subdued">PDF, DOCX or TXT · up to 5 MB</span>
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                    className="sr-only"
                    onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  />
                </label>
              )}
            </div>
          </>
        ) : (
          <>
            <CompanyPicker
              value={form.company_id}
              onChange={(value) => set("company_id", value)}
              error={errors.company_id}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Role title" required error={errors.title}>
                <Input
                  placeholder="e.g. Staff Backend Engineer"
                  maxLength={250}
                  value={form.title}
                  onChange={(event) => set("title", event.target.value)}
                />
              </Field>
              <Field label="Location">
                <Input
                  placeholder="City, country or Remote"
                  maxLength={200}
                  value={form.location}
                  onChange={(event) => set("location", event.target.value)}
                />
              </Field>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Seniority">
                <Input
                  placeholder="Junior, Mid, Senior, Staff…"
                  maxLength={64}
                  value={form.seniority}
                  onChange={(event) => set("seniority", event.target.value)}
                />
              </Field>
              <Field label="Employment type">
                <Input
                  placeholder="Full-time, Contract…"
                  maxLength={32}
                  value={form.employment_type}
                  onChange={(event) => set("employment_type", event.target.value)}
                />
              </Field>
            </div>

            <Field label="Posting URL" error={errors.url}>
              <Input
                type="url"
                placeholder="https://…"
                maxLength={1000}
                value={form.url}
                onChange={(event) => set("url", event.target.value)}
              />
            </Field>

            <Field
              label="Job description text"
              required={!editing}
              hint="Paste the full posting. Plain text keeps the best extraction quality."
              error={errors.raw_text}
            >
              <Textarea
                rows={8}
                maxLength={200000}
                placeholder="About the role, responsibilities, requirements…"
                value={form.raw_text}
                onChange={(event) => set("raw_text", event.target.value)}
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Required skills" hint="Comma-separated.">
                <Input
                  placeholder="Python, SQL, distributed systems"
                  value={form.required_skills}
                  onChange={(event) => set("required_skills", event.target.value)}
                />
              </Field>
              <Field label="Preferred skills" hint="Comma-separated.">
                <Input
                  placeholder="Kubernetes, Terraform"
                  value={form.preferred_skills}
                  onChange={(event) => set("preferred_skills", event.target.value)}
                />
              </Field>
            </div>

            <Field label="Responsibilities" hint="One per line, or comma-separated.">
              <Textarea
                rows={4}
                placeholder={"Own the platform roadmap\nMentor engineers"}
                value={form.responsibilities}
                onChange={(event) => set("responsibilities", event.target.value)}
              />
            </Field>

            <Field label="Private notes">
              <Textarea
                rows={3}
                maxLength={20000}
                placeholder="Why this role is interesting, questions to ask, referral contact…"
                value={form.notes}
                onChange={(event) => set("notes", event.target.value)}
              />
            </Field>
          </>
        )}
      </form>
    </Modal>
  );
}
