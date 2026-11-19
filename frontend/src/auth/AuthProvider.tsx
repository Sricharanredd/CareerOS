import { useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, csrfHeaders, refreshSession, setAccessToken, setUnauthorizedHandler } from "@/lib/api";
import type { OwnerProfile, Theme, TokenResponse } from "@/lib/types";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  owner: OwnerProfile | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  updateOwner: (patch: Partial<Pick<OwnerProfile, "full_name" | "timezone" | "currency" | "theme">>) => Promise<OwnerProfile>;
  reloadOwner: () => Promise<void>;
  setTheme: (theme: Theme) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function prefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && prefersDark());
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [owner, setOwner] = useState<OwnerProfile | null>(null);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setOwner(null);
    setStatus("anonymous");
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearSession();
      queryClient.clear();
    });
    return () => setUnauthorizedHandler(null);
  }, [clearSession, queryClient]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const refreshed = await refreshSession();
      if (cancelled) return;
      if (!refreshed) {
        setStatus("anonymous");
        return;
      }
      try {
        const profile = await api.get<OwnerProfile>("/auth/me");
        if (cancelled) return;
        setOwner(profile);
        setStatus("authenticated");
      } catch {
        if (!cancelled) setStatus("anonymous");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const theme = owner?.theme ?? "system";
    applyTheme(theme);
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [owner?.theme]);

  const login = useCallback(async (email: string, password: string) => {
    const data = await api.post<TokenResponse>("/auth/login", { email, password });
    setAccessToken(data.access_token);
    setOwner(data.owner);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post<void>("/auth/logout", undefined, { headers: csrfHeaders(), retryOn401: false });
    } finally {
      clearSession();
      queryClient.clear();
    }
  }, [clearSession, queryClient]);

  const updateOwner = useCallback(
    async (patch: Partial<Pick<OwnerProfile, "full_name" | "timezone" | "currency" | "theme">>) => {
      const updated = await api.patch<OwnerProfile>("/auth/me", patch);
      setOwner(updated);
      return updated;
    },
    [],
  );

  const reloadOwner = useCallback(async () => {
    const profile = await api.get<OwnerProfile>("/auth/me");
    setOwner(profile);
  }, []);

  const setTheme = useCallback(
    async (theme: Theme) => {
      setOwner((current) => (current ? { ...current, theme } : current));
      try {
        await updateOwner({ theme });
      } catch {
        await reloadOwner().catch(() => undefined);
      }
    },
    [reloadOwner, updateOwner],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ status, owner, login, logout, updateOwner, reloadOwner, setTheme }),
    [status, owner, login, logout, updateOwner, reloadOwner, setTheme],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
