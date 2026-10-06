import type { Metadata } from "next";
import { Suspense } from "react";

import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api/server-client";

export const metadata: Metadata = { title: "Public Atlas" };

/**
 * The console's pages (runs, assignments, institutions, review, countries, evals) come with the
 * console itself. Until then the home page shows that the API is reachable.
 */
export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-svh max-w-2xl flex-col justify-center gap-6 p-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Public Atlas</h1>
        <p className="text-muted-foreground">
          A verified map of the public sector: places, institutions, their homepages and the web
          pages that carry procurement signals.
        </p>
      </div>
      <Suspense fallback={<ApiStatus status="checking" />}>
        <ApiHealth />
      </Suspense>
    </main>
  );
}

async function ApiHealth() {
  const status: "ok" | "down" = await api
    .GET("/health")
    .then(({ data }) => (data?.status === "ok" ? "ok" : "down"))
    .catch(() => "down");
  return <ApiStatus status={status} />;
}

function ApiStatus({ status }: { status: "ok" | "down" | "checking" }) {
  const label = { ok: "API reachable", down: "API unreachable", checking: "Checking the API…" }[
    status
  ];
  return (
    <div className="flex items-center gap-2 text-sm">
      <Badge variant={status === "ok" ? "default" : "outline"}>{label}</Badge>
    </div>
  );
}
