"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { ReactNode } from "react";

import { Detail } from "@/components/shared/detail-list";
import { ExternalLink } from "@/components/shared/external-link";
import { PageHeader } from "@/components/shared/layout/page-header";
import { EntityStatusBadge, ReviewStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EvidenceList } from "@/features/graph/components/evidence-list";
import { browserApi } from "@/lib/api/client";
import { formatDateTime } from "@/lib/formatting/dates";
import { entityKindLabels, humanize, labelOf, reviewRuleLabels } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { useReviewActions } from "../hooks/use-review-actions";
import { reviewItemQuery } from "../queries";
import { QuestionFacts, reasonsOf, scalarText } from "./question-facts";

const HIDDEN_COLUMNS = new Set(["id", "kind", "name", "status"]);
const INSTITUTION_LINKS = new Set(["institution_id", "parent_institution_id"]);

export function ReviewItemDetail({ id, timeZone }: { id: string; timeZone: string }) {
  const { data: item } = useSuspenseQuery(reviewItemQuery(browserApi, id));
  const actions = useReviewActions();
  const open = item.status === "open";
  const mergeable = item.entity_kind === "institution" || item.entity_kind === "place";
  const entityHref = item.entity_kind === "institution" ? paths.institution(item.entity_id) : null;

  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            {entityHref ? (
              <Link href={entityHref} className="hover:underline">
                {item.label}
              </Link>
            ) : (
              item.label
            )}
            <ReviewStatusBadge status={item.status} />
          </span>
        }
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span>{entityKindLabels[item.entity_kind]}</span>
            <span>·</span>
            <span>{labelOf(reviewRuleLabels, item.rule)}</span>
            {item.kind && (
              <Badge variant="outline" className="font-mono text-[10px]">
                {item.kind}
              </Badge>
            )}
          </span>
        }
      >
        {open && (
          <>
            <Button onClick={() => actions.approve(item)}>Approve</Button>
            {mergeable && (
              <Button variant="outline" onClick={() => actions.merge(item)}>
                Merge
              </Button>
            )}
            <Button variant="destructive" onClick={() => actions.reject(item)}>
              Reject
            </Button>
          </>
        )}
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>The question</CardTitle>
            <CardDescription>
              Why the entity was sent to review, once per time it was.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
              {reasonsOf(item.question).map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
            <QuestionFacts question={item.question} />
            {item.note && (
              <p className="rounded-md bg-muted p-3 text-sm">
                <span className="text-muted-foreground">Note: </span>
                {item.note}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>The entity</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="flex flex-col gap-3 text-sm">
              <Detail label="Status">
                {isEntityStatus(item.entity_status) ? (
                  <EntityStatusBadge status={item.entity_status} />
                ) : (
                  item.entity_status
                )}
              </Detail>
              <Detail label="Names">{item.names.join(", ")}</Detail>
              {Object.entries(item.entity)
                .filter(([key, value]) => !HIDDEN_COLUMNS.has(key) && value !== null)
                .map(([key, value]) => (
                  <Detail key={key} label={humanize(key)}>
                    <EntityValue column={key} value={value} />
                  </Detail>
                ))}
              <Detail label="Raised by">
                {item.raised_by_assignment_id && (
                  <Link
                    href={paths.assignment(item.raised_by_assignment_id)}
                    className="font-mono text-xs hover:underline"
                  >
                    {item.raised_by_assignment_id}
                  </Link>
                )}
              </Detail>
              <Detail label="Decided">{formatDateTime(item.decided_at, timeZone)}</Detail>
            </dl>
          </CardContent>
        </Card>
      </div>

      <section className="mt-8 flex flex-col gap-4">
        <h3 className="text-lg font-semibold">Evidence</h3>
        <Card>
          <CardContent>
            <EvidenceList evidence={item.evidence} />
          </CardContent>
        </Card>
      </section>
      {actions.dialog}
    </>
  );
}

function isEntityStatus(
  value: string,
): value is "candidate" | "verified" | "rejected" | "needs_review" {
  return ["candidate", "verified", "rejected", "needs_review"].includes(value);
}

function EntityValue({ column, value }: { column: string; value: unknown }): ReactNode {
  if (typeof value === "string" && INSTITUTION_LINKS.has(column)) {
    return (
      <Link href={paths.institution(value)} className="font-mono text-xs hover:underline">
        {value}
      </Link>
    );
  }
  if (typeof value === "string" && /^https?:\/\//.test(value)) {
    return <ExternalLink href={value} />;
  }
  if (typeof value === "string" && column.endsWith("_id")) {
    return <span className="font-mono text-xs">{value}</span>;
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return scalarText(value);
}
