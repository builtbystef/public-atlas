import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/shared/layout/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { databaseLabels } from "@/lib/api/database";
import { unwrap } from "@/lib/api/errors";
import { getApi, getDatabase } from "@/lib/api/server";
import { formatCost } from "@/lib/formatting/money";
import { paths } from "@/lib/routes";

export const metadata: Metadata = { title: "Overview" };

/** The console's front page: one count per section, each a link into it. */
export default function OverviewPage() {
  return (
    <>
      <PageHeader
        title="Overview"
        description={
          <Suspense fallback="Reading…">
            <CurrentDatabase />
          </Suspense>
        }
      />
      <Suspense fallback={<OverviewSkeleton />}>
        <Counts />
      </Suspense>
    </>
  );
}

async function CurrentDatabase() {
  return <>{databaseLabels[await getDatabase()]}</>;
}

const ONE = { limit: 1, offset: 0 };

async function Counts() {
  const api = await getApi();
  const [runs, running, institutions, needsReview, open, evalRuns] = await Promise.all([
    api.GET("/runs", { params: { query: ONE } }).then(unwrap),
    api.GET("/assignments", { params: { query: { ...ONE, status: "running" } } }).then(unwrap),
    api.GET("/institutions", { params: { query: ONE } }).then(unwrap),
    api
      .GET("/institutions", { params: { query: { ...ONE, status: "needs_review" } } })
      .then(unwrap),
    api.GET("/review-items", { params: { query: { ...ONE, status: "open" } } }).then(unwrap),
    api.GET("/eval-runs", { params: { query: ONE } }).then(unwrap),
  ]);
  const latestRun = runs.items[0];
  const latestEval = evalRuns.items[0];
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <StatCard
        label="Runs"
        value={runs.total}
        href={paths.runs}
        detail={latestRun ? `Latest: ${latestRun.name}` : "Start one from the runs page."}
      />
      <StatCard
        label="Assignments running"
        value={running.total}
        href={`${paths.assignments}?status=running`}
      />
      <StatCard
        label="Institutions"
        value={institutions.total}
        href={paths.institutions}
        detail={`${needsReview.total} awaiting review`}
      />
      <StatCard label="Open review items" value={open.total} href={paths.review} />
      <StatCard
        label="Eval runs"
        value={evalRuns.total}
        href={paths.evals}
        detail={latestEval ? `Latest cost ${formatCost(latestEval.cost)}` : undefined}
      />
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 5 }, (_, i) => (
        <Skeleton key={i} className="h-28" />
      ))}
    </div>
  );
}
