import { Compass, Home } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
        <Compass className="h-6 w-6" aria-hidden />
      </span>
      <p className="mt-5 text-[11px] font-semibold uppercase tracking-[0.2em] text-subdued">404</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight text-fg">This page is off the map</h1>
      <p className="mt-2 max-w-sm text-sm text-muted">
        The page you were looking for does not exist in this workspace.
      </p>
      <Link to="/" className="mt-6">
        <Button variant="primary" icon={<Home className="h-4 w-4" />}>
          Back to dashboard
        </Button>
      </Link>
    </div>
  );
}
