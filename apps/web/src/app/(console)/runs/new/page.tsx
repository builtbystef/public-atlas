import type { Metadata } from "next";
import { Suspense } from "react";

import { FormPage } from "@/components/shared/layout/form-page";
import { PageHeader } from "@/components/shared/layout/page-header";
import { FormSkeleton } from "@/components/shared/skeletons";
import { RunForm } from "@/features/runs/components/run-form";
import { unwrap } from "@/lib/api/errors";
import { getApi } from "@/lib/api/server";

export const metadata: Metadata = { title: "New run" };

export default function NewRunPage() {
  return (
    <FormPage>
      <PageHeader
        title="New run"
        description="Choose what the agent works on. In step mode, release assignments from the run's page."
      />
      <Suspense fallback={<FormSkeleton />}>
        <NewRunForm />
      </Suspense>
    </FormPage>
  );
}

async function NewRunForm() {
  const api = await getApi();
  const countries = unwrap(await api.GET("/countries"));
  return <RunForm countries={countries} />;
}
