import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  KeyRound,
  Laptop,
  LogOut,
  Monitor,
  Moon,
  Save,
  ShieldCheck,
  Sun,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthProvider";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { InlineAlert } from "@/components/ui/Feedback";
import { Field, Input, Select } from "@/components/ui/Form";
import { Card, PageHeader, SectionTitle } from "@/components/ui/Layout";
import { ConfirmDialog, Modal } from "@/components/ui/Overlay";
import { SegmentedControl } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { api, downloadFile, errorMessage, fieldErrors } from "@/lib/api";
import { COMMON_TIMEZONES, CURRENCY_OPTIONS } from "@/lib/constants";
import { formatDateTime, formatRelative } from "@/lib/format";
import {
  useMeta,
  useRevokeOtherSessions,
  useRevokeSession,
  useSessions,
} from "@/lib/queries";
import type { Theme } from "@/lib/types";

function deviceLabel(userAgent: string | null): string {
  if (!userAgent) return "Unknown device";
  const ua = userAgent.toLowerCase();
  const browser = ua.includes("edg")
    ? "Edge"
    : ua.includes("chrome")
      ? "Chrome"
      : ua.includes("firefox")
        ? "Firefox"
        : ua.includes("safari")
          ? "Safari"
          : "Browser";
  const os = ua.includes("windows")
    ? "Windows"
    : ua.includes("mac")
      ? "macOS"
      : ua.includes("linux")
        ? "Linux"
        : ua.includes("android")
          ? "Android"
          : ua.includes("iphone") || ua.includes("ipad")
            ? "iOS"
            : "Unknown OS";
  return `${browser} on ${os}`;
}

function ProfileSection() {
  const { owner, updateOwner } = useAuth();
  const toast = useToast();
  const [fullName, setFullName] = useState(owner?.full_name ?? "");
  const [timezone, setTimezone] = useState(owner?.timezone ?? "UTC");
  const [currency, setCurrency] = useState(owner?.currency ?? "USD");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setFullName(owner?.full_name ?? "");
    setTimezone(owner?.timezone ?? "UTC");
    setCurrency(owner?.currency ?? "USD");
  }, [owner?.full_name, owner?.timezone, owner?.currency]);

  const dirty =
    fullName !== (owner?.full_name ?? "") ||
    timezone !== owner?.timezone ||
    currency !== owner?.currency;

  const timezones = useMemo(() => {
    const list = [...COMMON_TIMEZONES];
    if (owner?.timezone && !list.includes(owner.timezone)) list.unshift(owner.timezone);
    return list;
  }, [owner?.timezone]);

  async function save() {
    setBusy(true);
    try {
      await updateOwner({
        full_name: fullName.trim() || null,
        timezone,
        currency: currency.toUpperCase(),
      });
      toast.success("Profile saved.");
    } catch (caught) {
      toast.error(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  if (!owner) return null;

  return (
    <Card className="p-5">
      <SectionTitle title="Profile" hint="Shown across your private workspace." />
      <div className="mt-5 flex items-center gap-3 rounded-xl border border-line bg-surface-2/40 px-4 py-3">
        <Avatar name={owner.full_name} email={owner.email} size="lg" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-fg">{owner.full_name ?? "Owner"}</p>
          <p className="truncate text-xs text-muted">{owner.email}</p>
          <p className="mt-0.5 text-[11px] text-subdued">
            Owner since {formatDateTime(owner.created_at)}
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field label="Full name" htmlFor="full-name">
          <Input
            id="full-name"
            maxLength={120}
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
          />
        </Field>
        <Field label="Currency" htmlFor="currency" hint="Used for salary displays.">
          <Select id="currency" value={currency} onChange={(event) => setCurrency(event.target.value)}>
            {CURRENCY_OPTIONS.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Timezone" htmlFor="timezone" hint="Dates are stored in UTC and shown in your browser.">
          <Select id="timezone" value={timezone} onChange={(event) => setTimezone(event.target.value)}>
            {timezones.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Email">
          <Input value={owner.email} readOnly disabled />
        </Field>
      </div>

      <div className="mt-4 flex justify-end">
        <Button
          variant="primary"
          icon={<Save className="h-4 w-4" />}
          loading={busy}
          disabled={!dirty}
          onClick={() => void save()}
        >
          Save profile
        </Button>
      </div>
    </Card>
  );
}

function ThemeSection() {
  const { owner, setTheme } = useAuth();
  return (
    <Card className="p-5">
      <SectionTitle title="Appearance" hint="Follow the system, or pin a theme to this account." />
      <div className="mt-4">
        <SegmentedControl<Theme>
          ariaLabel="Theme"
          value={owner?.theme ?? "system"}
          onChange={(theme) => void setTheme(theme)}
          options={[
            { value: "light", label: "Light", icon: <Sun className="h-3.5 w-3.5" /> },
            { value: "system", label: "System", icon: <Monitor className="h-3.5 w-3.5" /> },
            { value: "dark", label: "Dark", icon: <Moon className="h-3.5 w-3.5" /> },
          ]}
        />
      </div>
      <p className="mt-3 text-xs text-subdued">
        The preference is stored on your owner profile, so it follows you between browsers.
      </p>
    </Card>
  );
}

function PasswordSection() {
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setErrors({});
    if (next.length < 12) {
      setError("Use at least 12 characters for the new password.");
      return;
    }
    if (next !== confirm) {
      setError("The new passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await api.post<{ message: string }>("/auth/change-password", {
        current_password: current,
        new_password: next,
      });
      toast.success("Password updated. Other sessions were signed out.");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (caught) {
      setErrors(fieldErrors(caught));
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <SectionTitle title="Password" hint="Changing it signs out every other session." />
      <form className="mt-5 space-y-4" onSubmit={(event) => void submit(event)} noValidate>
        {error && <InlineAlert tone="danger">{error}</InlineAlert>}
        <Field label="Current password" error={errors.current_password}>
          <Input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="New password"
            error={errors.new_password}
            hint="At least 12 characters, mixing cases, digits and symbols."
          >
            <Input
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(event) => setNext(event.target.value)}
            />
          </Field>
          <Field label="Confirm new password">
            <Input
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
          </Field>
        </div>
        <div className="flex justify-end">
          <Button
            type="submit"
            variant="primary"
            icon={<KeyRound className="h-4 w-4" />}
            loading={busy}
            disabled={!current || !next || !confirm}
          >
            Update password
          </Button>
        </div>
      </form>
    </Card>
  );
}

function SessionsSection() {
  const sessions = useSessions();
  const revoke = useRevokeSession();
  const revokeOthers = useRevokeOtherSessions();
  const toast = useToast();
  const [confirmOthers, setConfirmOthers] = useState(false);

  async function revokeOne(id: string) {
    try {
      await revoke.mutateAsync(id);
      toast.success("Session signed out.");
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  async function doRevokeOthers() {
    try {
      const result = await revokeOthers.mutateAsync();
      toast.success(result.message);
      setConfirmOthers(false);
    } catch (caught) {
      toast.error(errorMessage(caught));
    }
  }

  const rows = sessions.data ?? [];
  const others = rows.filter((session) => !session.current).length;

  return (
    <Card className="p-5">
      <SectionTitle
        title="Active sessions"
        hint="Refresh tokens are opaque and rotate on every use."
        action={
          <Button
            size="sm"
            variant="secondary"
            icon={<LogOut className="h-3.5 w-3.5" />}
            disabled={others === 0}
            onClick={() => setConfirmOthers(true)}
          >
            Sign out others
          </Button>
        }
      />

      {sessions.isLoading && <p className="mt-4 text-sm text-muted">Loading sessions…</p>}
      {sessions.isError && (
        <p className="mt-4 text-sm text-danger">Sessions could not be loaded.</p>
      )}

      {rows.length > 0 && (
        <ul className="mt-4 divide-y divide-line">
          {rows.map((session) => (
            <li key={session.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="flex min-w-0 items-start gap-2.5">
                <span
                  className={clsx(
                    "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                    session.current ? "bg-accent-soft text-accent" : "bg-surface-2 text-subdued",
                  )}
                >
                  {session.current ? <ShieldCheck className="h-4 w-4" /> : <Laptop className="h-4 w-4" />}
                </span>
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm font-medium text-fg">
                    {deviceLabel(session.user_agent)}
                    {session.current && <Badge tone="accent">This device</Badge>}
                  </p>
                  <p className="text-[11px] text-subdued">
                    {session.ip ? `${session.ip} · ` : ""}
                    {session.last_used_at
                      ? `last used ${formatRelative(session.last_used_at)}`
                      : `signed in ${formatRelative(session.created_at)}`}
                    {" · "}
                    expires {formatDateTime(session.expires_at)}
                  </p>
                </div>
              </div>
              {!session.current && (
                <Button
                  size="sm"
                  variant="ghost"
                  loading={revoke.isPending}
                  onClick={() => void revokeOne(session.id)}
                >
                  Revoke
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={confirmOthers}
        onClose={() => setConfirmOthers(false)}
        onConfirm={() => void doRevokeOthers()}
        loading={revokeOthers.isPending}
        title="Sign out other sessions?"
        description={`${others} other session${others === 1 ? "" : "s"} will need to sign in again. This device stays signed in.`}
        confirmLabel="Sign out others"
        tone="primary"
      />
    </Card>
  );
}

function DataSection() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function exportData() {
    setBusy(true);
    try {
      await downloadFile("/auth/export", "careeros-export.json");
      toast.success("Export downloaded.");
    } catch (caught) {
      toast.error(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <SectionTitle title="Your data" hint="Everything is yours. Take a full copy at any time." />
      <p className="mt-3 text-sm leading-relaxed text-muted">
        The export includes companies, job descriptions, resumes and versions (without file bytes),
        applications, timelines, interviews, follow-ups, tasks and time entries as a single JSON
        document.
      </p>
      <div className="mt-4">
        <Button variant="secondary" icon={<Download className="h-4 w-4" />} loading={busy} onClick={() => void exportData()}>
          Export JSON
        </Button>
      </div>
    </Card>
  );
}

function AboutSection() {
  const meta = useMeta();
  if (!meta.data) return null;
  return (
    <Card className="p-5">
      <SectionTitle title="About this instance" hint="Local, single-owner deployment." />
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div className="flex items-center justify-between gap-3 border-b border-line pb-2">
          <dt className="text-muted">Version</dt>
          <dd className="font-medium text-fg">{meta.data.version}</dd>
        </div>
        <div className="flex items-center justify-between gap-3 border-b border-line pb-2">
          <dt className="text-muted">Environment</dt>
          <dd className="font-medium text-fg">{meta.data.environment}</dd>
        </div>
        <div className="flex items-center justify-between gap-3 border-b border-line pb-2">
          <dt className="text-muted">Owner account</dt>
          <dd>
            {meta.data.owner_configured ? (
              <Badge tone="success">
                <CheckCircle2 className="h-3 w-3" /> Configured
              </Badge>
            ) : (
              <Badge tone="warning">Missing</Badge>
            )}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-3 border-b border-line pb-2">
          <dt className="text-muted">AI provider</dt>
          <dd>
            {meta.data.ai_configured ? (
              <Badge tone="success">Connected</Badge>
            ) : (
              <Badge tone="neutral">Not configured</Badge>
            )}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-subdued">
        Fit analysis is planned for a later phase. Resume versions and job descriptions are already
        stored in the shape it needs.
      </p>
    </Card>
  );
}

function DangerSection() {
  const { owner, logout } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function performDelete() {
    setError(null);
    if (confirmation !== "DELETE") {
      setError('Type DELETE exactly to confirm.');
      return;
    }
    setBusy(true);
    try {
      await api.post<void>("/auth/delete-account", { password, confirmation });
      queryClient.clear();
      toast.success("Account deleted. All workspace data has been removed.");
      await logout();
      navigate("/login", { replace: true });
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="border-danger/30 p-5">
      <SectionTitle title="Danger zone" hint="Irreversible actions that affect the whole account." />
      <div className="mt-4 flex flex-col gap-3 rounded-xl border border-danger/25 bg-danger-soft/50 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-fg">Delete the owner account</p>
          <p className="text-xs text-muted">
            Removes every company, job description, resume file, application and session. There is
            no recovery.
          </p>
        </div>
        <Button
          variant="danger"
          icon={<Trash2 className="h-4 w-4" />}
          onClick={() => {
            setPassword("");
            setConfirmation("");
            setError(null);
            setOpen(true);
          }}
        >
          Delete account
        </Button>
      </div>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        size="sm"
        title="Delete the account?"
        description={`This removes ${owner?.email ?? "the owner account"} and all data. This cannot be undone.`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={busy}
              disabled={!password || confirmation !== "DELETE"}
              onClick={() => void performDelete()}
            >
              Permanently delete
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {error && <InlineAlert tone="danger">{error}</InlineAlert>}
          <InlineAlert tone="warning" title="This is permanent">
            Export your data first if you may want a copy later.
          </InlineAlert>
          <Field label="Current password">
            <Input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <Field label='Type "DELETE" to confirm'>
            <Input
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder="DELETE"
              autoComplete="off"
            />
          </Field>
        </div>
      </Modal>
    </Card>
  );
}

export function SettingsPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Settings"
        subtitle="Profile, security and data control for this private instance."
        actions={
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[11px] text-muted">
            <AlertTriangle className="h-3 w-3 text-warning" aria-hidden />
            Single-owner workspace
          </span>
        }
      />

      <div className="grid gap-5 xl:grid-cols-2">
        <div className="space-y-5">
          <ProfileSection />
          <ThemeSection />
          <DataSection />
          <AboutSection />
        </div>
        <div className="space-y-5">
          <SessionsSection />
          <PasswordSection />
          <DangerSection />
        </div>
      </div>
    </div>
  );
}
