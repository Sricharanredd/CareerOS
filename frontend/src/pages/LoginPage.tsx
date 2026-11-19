import { Compass, Eye, EyeOff, Layers, LockKeyhole, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { InlineAlert, Spinner } from "@/components/ui/Feedback";
import { Field, Input } from "@/components/ui/Form";
import { errorMessage } from "@/lib/api";
import { useMeta } from "@/lib/queries";

const HIGHLIGHTS = [
  {
    icon: Layers,
    title: "One pipeline, every stage",
    body: "Saved, applied, interviewing, offer — see the whole search at a glance.",
  },
  {
    icon: ShieldCheck,
    title: "Private by default",
    body: "A single-owner workspace. Nothing is shared, indexed or syndicated.",
  },
  {
    icon: Sparkles,
    title: "Ready for assisted analysis",
    body: "Resume versions and job descriptions are stored to power fit scoring next.",
  },
];

export function LoginPage() {
  const { status, login } = useAuth();
  const meta = useMeta();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center gap-3 text-sm text-muted">
        <Spinner />
        Checking your session…
      </div>
    );
  }

  if (status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-[#0b1020] px-12 py-12 text-white lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-80"
          style={{
            backgroundImage:
              "radial-gradient(60rem 40rem at 10% -10%, rgba(99,102,241,0.35), transparent 60%), radial-gradient(45rem 32rem at 100% 110%, rgba(13,148,136,0.32), transparent 60%)",
          }}
          aria-hidden
        />
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)",
            backgroundSize: "56px 56px",
          }}
          aria-hidden
        />
        <div className="relative flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/20 backdrop-blur">
            <Compass className="h-5 w-5" aria-hidden />
          </span>
          <div className="leading-tight">
            <p className="text-[15px] font-semibold tracking-tight">CareerOS</p>
            <p className="text-[11px] uppercase tracking-[0.2em] text-white/50">Private workspace</p>
          </div>
        </div>

        <div className="relative max-w-md">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-white/45">
            Run the search like a system
          </p>
          <h1 className="mt-4 text-balance text-4xl font-semibold leading-[1.1] tracking-tight">
            Your career, in one calm, private workspace.
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-white/60">
            CareerOS keeps applications, job descriptions and resume versions in one place, so
            you always know what to do next — and never lose the context of a conversation.
          </p>
          <ul className="mt-9 space-y-5">
            {HIGHLIGHTS.map((item) => (
              <li key={item.title} className="flex gap-3.5">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/15">
                  <item.icon className="h-4 w-4 text-white/80" aria-hidden />
                </span>
                <div>
                  <p className="text-sm font-medium text-white/90">{item.title}</p>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-white/50">{item.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative flex items-center gap-2 text-[11px] text-white/40">
          <LockKeyhole className="h-3.5 w-3.5" aria-hidden />
          Local-first · MySQL-backed · Single owner
        </div>
      </section>

      <section className="flex items-center justify-center px-5 py-12 sm:px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-teal text-white">
              <Compass className="h-5 w-5" aria-hidden />
            </span>
            <div className="leading-tight">
              <p className="text-sm font-semibold text-fg">CareerOS</p>
              <p className="text-[10px] uppercase tracking-[0.18em] text-subdued">Private workspace</p>
            </div>
          </div>

          <h2 className="text-2xl font-semibold tracking-tight text-fg">Welcome back</h2>
          <p className="mt-1.5 text-sm text-muted">
            Sign in with the owner account to open your workspace.
          </p>

          <form className="mt-8 space-y-4" onSubmit={onSubmit} noValidate>
            {error && <InlineAlert tone="danger">{error}</InlineAlert>}

            <Field label="Email" htmlFor="email">
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="username"
                autoFocus
                required
                placeholder="you@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </Field>

            <Field label="Password" htmlFor="password">
              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  className="pr-11"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <button
                  type="button"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  onClick={() => setShowPassword((current) => !current)}
                  className="absolute right-1.5 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-subdued hover:bg-surface-2 hover:text-fg"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </Field>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="w-full"
              loading={busy}
              disabled={!email.trim() || !password}
            >
              Sign in
            </Button>
          </form>

          <p className="mt-6 text-xs leading-relaxed text-subdued">
            There is no sign-up. The owner account is created once from the backend CLI. If you
            are locked out, an administrator can reset the password locally.
          </p>

          {meta.data && (
            <p className="mt-8 flex items-center justify-between border-t border-line pt-4 text-[11px] text-subdued">
              <span>
                {meta.data.app_name} v{meta.data.version} · {meta.data.environment}
              </span>
              <span>{meta.data.ai_configured ? "AI configured" : "AI not configured"}</span>
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
