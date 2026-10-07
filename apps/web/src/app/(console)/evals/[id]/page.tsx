import type { Metadata } from "next";
import { Suspense } from "react";

import { DetailSkeleton } from "@/components/shared/skeletons";
import { EvalRunDetail } from "@/features/evals/components/eval-run-detail";
import { getApi, unwrapOrNotFound } from "@/lib/api/server";
import { getTimeZone } from "@/lib/time-zone/server";

export const metadata: Metadata = { title: "Eval run" };

type Params = Promise<{ id: string }>;

export default function EvalRunPage({ params }: { params: Params }) {
  return (
    <Suspense fallback={<DetailSkeleton />}>
      <EvalRunContent params={params} />
    </Suspense>
  );
}

async function EvalRunContent({ params }: { params: Params }) {
  const [{ id }, api, timeZone] = await Promise.all([params, getApi(), getTimeZone()]);
  const run = unwrapOrNotFound(
    await api.GET("/eval-runs/{eval_run_id}", { params: { path: { eval_run_id: id } } }),
  );
  return <EvalRunDetail run={run} timeZone={timeZone} />;
}
