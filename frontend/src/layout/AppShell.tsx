import clsx from "clsx";
import {
  BarChart3,
  BriefcaseBusiness,
  CalendarClock,
  Compass,
  FileText,
  LayoutDashboard,
  ListTodo,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Settings,
  Sparkles,
  Sun,
  UserRound,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/auth/AuthProvider";
import { Avatar } from "@/components/ui/Avatar";
import { IconButton } from "@/components/ui/Button";
import { useOverlay } from "@/components/ui/Overlay";
import { SegmentedControl } from "@/components/ui/Tabs";
import type { Theme } from "@/lib/types";

type NavItem = { to: string; label: string; icon: LucideIcon; end?: boolean };

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Workspace",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
      { to: "/applications", label: "Applications", icon: BriefcaseBusiness },
      { to: "/job-descriptions", label: "Job descriptions", icon: FileText },
      { to: "/resumes", label: "Resumes", icon: UserRound },
      { to: "/analyzer", label: "Analyzer", icon: Sparkles },
    ],
  },
  {
    label: "Momentum",
    items: [
      { to: "/tasks", label: "Tasks", icon: ListTodo },
      { to: "/interviews", label: "Interviews", icon: CalendarClock },
      { to: "/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
];

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/applications": "Applications",
  "/job-descriptions": "Job descriptions",
  "/resumes": "Resumes",
  "/analyzer": "Analyzer",
  "/tasks": "Tasks",
  "/interviews": "Interviews",
  "/analytics": "Analytics",
  "/settings": "Settings",
};

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2.5 rounded-lg focus-visible:outline-none">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-teal text-white shadow-sm">
        <Compass className="h-5 w-5" aria-hidden />
      </span>
      <span className="flex flex-col leading-none">
        <span className="text-[15px] font-semibold tracking-tight text-fg">CareerOS</span>
        <span className="mt-1 text-[10px] font-medium uppercase tracking-[0.16em] text-subdued">
          Private workspace
        </span>
      </span>
    </Link>
  );
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    clsx(
      "group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
      isActive ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-2 hover:text-fg",
    );

  return (
    <nav className="flex flex-col gap-5" aria-label="Main">
      {NAV_GROUPS.map((group) => (
        <div key={group.label}>
          <p className="px-2.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-subdued">
            {group.label}
          </p>
          <div className="space-y-0.5">
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={onNavigate}
                className={linkClass}
              >
                {({ isActive }) => (
                  <>
                    <item.icon
                      className={clsx(
                        "h-4 w-4",
                        isActive ? "text-accent" : "text-subdued group-hover:text-muted",
                      )}
                      aria-hidden
                    />
                    {item.label}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        </div>
      ))}
      <div>
        <p className="px-2.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-subdued">
          Account
        </p>
        <NavLink to="/settings" onClick={onNavigate} className={linkClass}>
          <Settings className="h-4 w-4 text-subdued group-hover:text-muted" aria-hidden />
          Settings
        </NavLink>
      </div>
    </nav>
  );
}

function ThemeControl() {
  const { owner, setTheme } = useAuth();
  const theme = owner?.theme ?? "system";
  return (
    <SegmentedControl<Theme>
      ariaLabel="Colour theme"
      value={theme}
      onChange={(next) => void setTheme(next)}
      options={[
        { value: "light", label: <Sun className="h-3.5 w-3.5" /> },
        { value: "system", label: <Monitor className="h-3.5 w-3.5" /> },
        { value: "dark", label: <Moon className="h-3.5 w-3.5" /> },
      ]}
    />
  );
}

function UserMenu() {
  const { owner, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  if (!owner) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-full border border-transparent p-0.5 pr-2 transition-colors hover:border-line hover:bg-surface-2 focus-visible:outline-none"
      >
        <Avatar name={owner.full_name} email={owner.email} size="sm" />
        <span className="hidden max-w-32 truncate text-sm font-medium text-fg sm:block">
          {owner.full_name ?? owner.email.split("@")[0]}
        </span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-30 mt-2 w-60 overflow-hidden rounded-xl border border-line bg-surface shadow-pop"
        >
          <div className="border-b border-line px-4 py-3">
            <p className="truncate text-sm font-medium text-fg">{owner.full_name ?? "Owner"}</p>
            <p className="truncate text-xs text-muted">{owner.email}</p>
          </div>
          <div className="p-1.5">
            <Link
              to="/settings"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-surface-2 hover:text-fg"
            >
              <Settings className="h-4 w-4" aria-hidden />
              Settings
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={() => void logout()}
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-surface-2 hover:text-fg"
            >
              <LogOut className="h-4 w-4" aria-hidden />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function AppShell() {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const closeMobile = useCallback(() => setMobileOpen(false), []);
  const mobilePanel = useOverlay(mobileOpen, closeMobile);
  const title = TITLES[location.pathname] ?? "CareerOS";

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-bg">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-line bg-bg-elevated px-3.5 py-5 lg:flex">
        <Brand />
        <div className="mt-8 flex-1">
          <NavItems />
        </div>
        <div className="rounded-xl border border-line bg-surface px-3 py-2.5 text-[11px] leading-relaxed text-subdued">
          Single-owner instance. Your data never leaves this machine.
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-[#0a0e16]/50 backdrop-blur-[2px]"
            onClick={closeMobile}
            aria-hidden
          />
          <div
            ref={mobilePanel}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="absolute inset-y-0 left-0 flex w-72 flex-col border-r border-line bg-bg-elevated px-4 py-5 outline-none"
          >
            <div className="flex items-center justify-between">
              <Brand />
              <IconButton label="Close navigation" onClick={closeMobile}>
                <X className="h-4 w-4" />
              </IconButton>
            </div>
            <div className="mt-8 flex-1">
              <NavItems onNavigate={closeMobile} />
            </div>
          </div>
        </div>
      )}

      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 border-b border-line bg-bg/85 backdrop-blur-md">
          <div className="flex h-14 items-center gap-3 px-4 sm:px-6">
            <IconButton
              label="Open navigation"
              className="lg:hidden"
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </IconButton>
            <span className="truncate text-sm font-medium text-muted">{title}</span>
            <div className="ml-auto flex items-center gap-2">
              <div className="hidden sm:block">
                <ThemeControl />
              </div>
              <UserMenu />
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
