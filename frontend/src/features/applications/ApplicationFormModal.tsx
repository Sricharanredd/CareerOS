import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { CompanyPicker } from "@/features/companies/CompanyPicker";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { InlineAlert } from "@/components/ui/Feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Overlay";
import { useToast } from "@/components/ui/Toast";
import { ApiError, errorMessage, fieldErrors } from "@/lib/api";
import {
  CURRENCY_OPTIONS,
  EMPLOYMENT_TYPE_LABEL,
  SALARY_PERIOD_LABEL,
  WORK_MODE_LABEL,
} from "@/lib/constants";
import { toDateInputValue } from "@/lib/format";
import {
  useAllResumeVersions,
  useCreateApplication,
  useJobOptions,
  useUpdateApplication,
} from "@/lib/queries";
import type {
  Application,
  ApplicationDetail,
  ApplicationInput,
  ApplicationStatus,
  EmploymentType,
  SalaryPeriod,
  WorkMode,
} from "@/lib/types";

interface FormState {
  company_id: string;
  title: string;
  status: ApplicationStatus;
  jd_id: string;
  resume_version_id: string;
  location: string;
  work_mode: string;
  employment_type: string;
  job_url: string;
  applied_on: string;
  follow_up_on: string;
  source: string;
  salary_min: string;
  salary_max: string;
  salary_currency: string;
  salary_period: string;
  notes: string;
  rejection_reason: string;
  offer_amount: string;
  offer_deadline: string;
}

const EMPTY: FormState = {
  company_id: "",
  title: "",
  status: "applied",
  jd_id: "",
  resume_version_id: "",
  location: "",
  work_mode: "",
  employment_type: "",
  job_url: "",
  applied_on: toDateInputValue(new Date().toISOString()),
  follow_up_on: "",
  source: "",
  salary_min: "",
  salary_max: "",
  salary_currency: "",
  salary_period: "",
  notes: "",
  rejection_reason: "",
  offer_amount: "",
  offer_deadline: "",
};

function fromApplication(application: ApplicationDetail): FormState {
  return {
    company_id: application.company.id,
    title: application.title,
    status: application.status,
    jd_id: application.jd_id ?? "",
    resume_version_id: application.resume_version_id ?? "",
    location: application.location ?? "",
    work_mode: application.work_mode ?? "",
    employment_type: application.employment_type ?? "",
    job_url: application.job_url ?? "",
    applied_on: toDateInputValue(application.applied_on),
    follow_up_on: toDateInputValue(application.follow_up_on),
    source: application.source ?? "",
    salary_min: application.salary_min ?? "",
    salary_max: application.salary_max ?? "",
    salary_currency: application.salary_currency ?? "",
    salary_period: application.salary_period ?? "",
    notes: application.notes ?? "",
    rejection_reason: application.rejection_reason ?? "",
    offer_amount: application.offer_amount ?? "",
    offer_deadline: toDateInputValue(application.offer_deadline),
  };
}

function orNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function toPayload(state: FormState, duplicateOverride = false): ApplicationInput {
  return {
    company_id: state.company_id,
    title: state.title.trim(),
    status: state.status,
    jd_id: orNull(state.jd_id),
    resume_version_id: orNull(state.resume_version_id),
    location: orNull(state.location),
    work_mode: (state.work_mode || null) as WorkMode | null,
    employment_type: (state.employment_type || null) as EmploymentType | null,
    job_url: orNull(state.job_url),
    applied_on: orNull(state.applied_on),
    follow_up_on: orNull(state.follow_up_on),
    source: orNull(state.source),
    salary_min: orNull(state.salary_min),
    salary_max: orNull(state.salary_max),
    salary_currency: state.salary_currency ? state.salary_currency.toUpperCase() : null,
    salary_period: (state.salary_period || null) as SalaryPeriod | null,
    notes: orNull(state.notes),
    duplicate_override: duplicateOverride,
  };
}

export function ApplicationFormModal({
  open,
  onClose,
  application,
  defaultStatus,
}: {
  open: boolean;
  onClose: () => void;
  application?: ApplicationDetail | null;
  defaultStatus?: ApplicationStatus;
}) {
  const editing = Boolean(application);
  const toast = useToast();
  const createApplication = useCreateApplication();
  const updateApplication = useUpdateApplication(application?.id ?? "");
  const [form, setForm] = useState<FormState>(EMPTY);
  const [formError, setFormError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [duplicates, setDuplicates] = useState<Application[] | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const jobOptions = useJobOptions(form.company_id || undefined);
  const { versions: resumeVersions } = useAllResumeVersions(open && !editing);

  useEffect(() => {
    if (!open) return;
    if (application) {
      setForm(fromApplication(application));
      setShowAdvanced(
        Boolean(
          application.rejection_reason || application.offer_amount || application.offer_deadline,
        ),
      );
    } else {
      setForm({
        ...EMPTY,
        status: defaultStatus ?? "applied",
        company_id: "",
        applied_on: toDateInputValue(new Date().toISOString()),
      });
      setShowAdvanced(false);
    }
    setFormError(null);
    setErrors({});
    setDuplicates(null);
  }, [open, application, defaultStatus]);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent, duplicateOverride = false) {
    event.preventDefault();
    setFormError(null);
    setErrors({});
    if (!form.company_id) {
      setErrors({ company_id: "Choose a company." });
      return;
    }
    if (!form.title.trim()) {
      setErrors({ title: "Give the role a title." });
      return;
    }
    if (form.salary_min && form.salary_max && Number(form.salary_min) > Number(form.salary_max)) {
      setErrors({ salary_max: "Maximum must be at least the minimum." });
      return;
    }

    const payload = toPayload(form, duplicateOverride);
    try {
      if (editing && application) {
        const { status: _status, duplicate_override: _ignore, ...rest } = payload;
        await updateApplication.mutateAsync(rest);
        toast.success("Application updated.");
      } else {
        await createApplication.mutateAsync(payload);
        toast.success("Application added.");
      }
      onClose();
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "duplicate_application") {
        const matches = (caught.details as { matches?: Application[] } | undefined)?.matches ?? [];
        setDuplicates(matches);
        setFormError(caught.message);
        return;
      }
      setErrors(fieldErrors(caught));
      setFormError(errorMessage(caught));
    }
  }

  const busy = createApplication.isPending || updateApplication.isPending;

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={editing ? "Edit application" : "New application"}
      description={
        editing
          ? "Update the details. Status changes are tracked separately in the timeline."
          : "Log a role you have saved or applied to."
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="application-form"
            loading={busy}
          >
            {editing ? "Save changes" : "Add application"}
          </Button>
        </>
      }
    >
      <form id="application-form" className="space-y-5" onSubmit={(event) => void submit(event)} noValidate>
        {formError && !duplicates && <InlineAlert tone="danger">{formError}</InlineAlert>}
        {duplicates && (
          <div className="space-y-2 rounded-xl border border-warning/30 bg-warning-soft p-3.5 text-sm text-warning">
            <p className="flex items-center gap-1.5 font-semibold">
              <AlertTriangle className="h-4 w-4" aria-hidden />
              Possible duplicate
            </p>
            <p className="opacity-90">{formError}</p>
            <ul className="space-y-1.5">
              {duplicates.map((match) => (
                <li key={match.id} className="flex items-center justify-between gap-2 rounded-lg bg-surface px-3 py-2">
                  <span className="truncate text-fg">
                    {match.title} · {match.company.name}
                  </span>
                  <StatusBadge status={match.status} />
                </li>
              ))}
            </ul>
            <div className="flex justify-end gap-2 pt-1">
              <Button size="sm" variant="ghost" onClick={() => setDuplicates(null)}>
                Review the form
              </Button>
              <Button
                size="sm"
                variant="secondary"
                loading={busy}
                onClick={(event) => void submit(event, true)}
              >
                Add anyway
              </Button>
            </div>
          </div>
        )}

        <CompanyPicker
          value={form.company_id}
          onChange={(companyId) => {
            setForm((current) => ({ ...current, company_id: companyId, jd_id: "" }));
          }}
          error={errors.company_id}
          autoFocus
        />

        <Field label="Role title" required error={errors.title}>
          <Input
            placeholder="e.g. Senior Product Designer"
            maxLength={250}
            value={form.title}
            onChange={(event) => set("title", event.target.value)}
          />
        </Field>

        {!editing && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Starting stage" hint="New applications start as saved or applied.">
              <Select
                value={form.status}
                onChange={(event) => set("status", event.target.value as ApplicationStatus)}
              >
                <option value="saved">Saved</option>
                <option value="applied">Applied</option>
              </Select>
            </Field>
            <Field label="Applied on">
              <Input
                type="date"
                value={form.applied_on}
                onChange={(event) => set("applied_on", event.target.value)}
              />
            </Field>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Job description" hint="Link the JD to keep its context.">
            <Select
              value={form.jd_id}
              onChange={(event) => set("jd_id", event.target.value)}
              disabled={!form.company_id || jobOptions.isLoading}
            >
              <option value="">
                {!form.company_id
                  ? "Choose a company first"
                  : jobOptions.data?.length
                    ? "No job description"
                    : "No job descriptions for this company"}
              </option>
              {jobOptions.data?.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.title}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Resume version" hint="The version you sent for this role.">
            <Select
              value={form.resume_version_id}
              onChange={(event) => set("resume_version_id", event.target.value)}
              disabled={resumeVersions.length === 0 && !editing}
            >
              <option value="">
                {resumeVersions.length === 0 ? "No resume versions yet" : "No resume linked"}
              </option>
              {resumeVersions.map((version) => (
                <option key={version.id} value={version.id}>
                  {version.resumeName} · v{version.versionNo}
                  {version.label ? ` — ${version.label}` : ""}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Location">
            <Input
              placeholder="City, country or Remote"
              maxLength={200}
              value={form.location}
              onChange={(event) => set("location", event.target.value)}
            />
          </Field>
          <Field label="Job posting URL" error={errors.job_url}>
            <Input
              type="url"
              placeholder="https://…"
              maxLength={1000}
              value={form.job_url}
              onChange={(event) => set("job_url", event.target.value)}
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Work mode">
            <Select value={form.work_mode} onChange={(event) => set("work_mode", event.target.value)}>
              <option value="">Not specified</option>
              {(Object.keys(WORK_MODE_LABEL) as WorkMode[]).map((mode) => (
                <option key={mode} value={mode}>
                  {WORK_MODE_LABEL[mode]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Employment type">
            <Select
              value={form.employment_type}
              onChange={(event) => set("employment_type", event.target.value)}
            >
              <option value="">Not specified</option>
              {(Object.keys(EMPLOYMENT_TYPE_LABEL) as EmploymentType[]).map((type) => (
                <option key={type} value={type}>
                  {EMPLOYMENT_TYPE_LABEL[type]}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-4">
          <Field label="Salary min" error={errors.salary_min}>
            <Input
              type="number"
              min={0}
              step="1"
              value={form.salary_min}
              onChange={(event) => set("salary_min", event.target.value)}
            />
          </Field>
          <Field label="Salary max" error={errors.salary_max}>
            <Input
              type="number"
              min={0}
              step="1"
              value={form.salary_max}
              onChange={(event) => set("salary_max", event.target.value)}
            />
          </Field>
          <Field label="Currency">
            <Select
              value={form.salary_currency}
              onChange={(event) => set("salary_currency", event.target.value)}
            >
              <option value="">—</option>
              {CURRENCY_OPTIONS.map((currency) => (
                <option key={currency} value={currency}>
                  {currency}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Per">
            <Select
              value={form.salary_period}
              onChange={(event) => set("salary_period", event.target.value)}
            >
              <option value="">—</option>
              {(Object.keys(SALARY_PERIOD_LABEL) as SalaryPeriod[]).map((period) => (
                <option key={period} value={period}>
                  {SALARY_PERIOD_LABEL[period]}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Source" hint="Where the role came from.">
            <Input
              placeholder="Referral, LinkedIn, careers page…"
              maxLength={120}
              value={form.source}
              onChange={(event) => set("source", event.target.value)}
            />
          </Field>
          <Field label="Follow up on">
            <Input
              type="date"
              value={form.follow_up_on}
              onChange={(event) => set("follow_up_on", event.target.value)}
            />
          </Field>
        </div>

        <Field label="Notes">
          <Textarea
            rows={4}
            placeholder="Context worth remembering: recruiter names, salary expectations, next steps…"
            maxLength={20000}
            value={form.notes}
            onChange={(event) => set("notes", event.target.value)}
          />
        </Field>

        {editing && (
          <div className="rounded-xl border border-line bg-surface-2/40">
            <button
              type="button"
              className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-fg"
              onClick={() => setShowAdvanced((current) => !current)}
            >
              Outcome details
              <span className="text-xs font-normal text-subdued">
                {showAdvanced ? "Hide" : "Rejection reason, offer terms"}
              </span>
            </button>
            {showAdvanced && (
              <div className="space-y-4 border-t border-line px-4 py-4">
                <Field label="Rejection reason">
                  <Textarea
                    rows={2}
                    maxLength={20000}
                    value={form.rejection_reason}
                    onChange={(event) => set("rejection_reason", event.target.value)}
                  />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Offer amount" error={errors.offer_amount}>
                    <Input
                      type="number"
                      min={0}
                      step="1"
                      value={form.offer_amount}
                      onChange={(event) => set("offer_amount", event.target.value)}
                    />
                  </Field>
                  <Field label="Offer deadline">
                    <Input
                      type="date"
                      value={form.offer_deadline}
                      onChange={(event) => set("offer_deadline", event.target.value)}
                    />
                  </Field>
                </div>
                <p className="text-xs text-subdued">
                  Offer details are stored for reporting. Change status to Accepted or Rejected
                  from the application timeline when the decision lands.
                </p>
              </div>
            )}
          </div>
        )}
      </form>
    </Modal>
  );
}
