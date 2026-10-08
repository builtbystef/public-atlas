"use client";

import type { EvidenceOutput, ReviewItemDetail as Item } from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { ArrowRightIcon, ChevronRightIcon, LayersIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { CollapsibleText } from "@/components/shared/collapsible-text";
import { Detail } from "@/components/shared/detail-list";
import { ExternalLink } from "@/components/shared/external-link";
import { JsonView } from "@/components/shared/json-view";
import { PageHeader } from "@/components/shared/layout/page-header";
import { ReviewStatusBadge } from "@/components/shared/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { EvidenceList } from "@/features/graph/components/evidence-list";
import { browserApi } from "@/lib/api/client";
import { formatDateTime } from "@/lib/formatting/dates";
import { entityKindLabels, humanize, labelOf, reviewRuleLabels } from "@/lib/labels";
import { toSearchString } from "@/lib/lists";
import { paths } from "@/lib/routes";

import { useReviewActions } from "../hooks/use-review-actions";
import { itemTitle, othersAsking } from "../question";
import { reviewItemQuery } from "../queries";
import {
  EntityComparison,
  EntityRefLink,
  shortUrl,
  type ComparedEntity,
} from "./entity-comparison";
import { QuestionFacts, reasonsOf, scalarText } from "./question-facts";
import { ReviewHistory } from "./review-history";

const INSTITUTION_LINKS = new Set(["institution_id", "parent_institution_id"]);
const ISO_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;

/** What a column of the comparison is, by the fact of the question that names it. */
const FACT_HEADINGS: Record<string, string> = {
  duplicate_of: "Possible match",
  homepage_id: "The homepage claim",
  institution_id: "The institution",
};

/**
 * One review item, in one column: the question as a sentence with the
 * decision beside it, the entity set beside the ones its question names,
 * why it was raised and the evidence under it, and what happened to it.
 */
export function ReviewItemDetail({ id, timeZone }: { id: string; timeZone: string }) {
  const { data: item } = useSuspenseQuery(reviewItemQuery(browserApi, id));
  const actions = useReviewActions();
  const open = item.status === "open";
  const mergeable = item.entity_kind === "institution" || item.entity_kind === "place";
  const reasons = reasonsOf(item.question);
  const next = item.next_open_id;

  const columns: ComparedEntity[] = [
    { entity: item.subject, heading: `This ${entityKindLabels[item.entity_kind].toLowerCase()}` },
    ...item.related.map((related) => ({
      entity: related.entity,
      heading: FACT_HEADINGS[related.fact] ?? humanize(related.fact),
      action:
        open &&
        mergeable &&
        related.fact === "duplicate_of" &&
        related.entity.entity_kind === item.entity_kind ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => actions.merge(item, related.entity.id)}
          >
            Merge into this
          </Button>
        ) : undefined,
    })),
  ];
  const duplicate = item.related.some((related) => related.fact === "duplicate_of");
  // Set beside other entities, the comparison leads the page; alone, the entity follows the evidence.
  const compared = item.related.length > 0;
  const entityCard = (
    <Card>
      <CardHeader>
        <CardTitle>
          {duplicate ? "Compare" : compared ? "What the question is about" : "The entity"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <EntityComparison columns={columns} />
      </CardContent>
    </Card>
  );

  return (
    <>
      <PageHeader
        title={<span className="block max-w-3xl text-balance">{itemTitle(item)}</span>}
        description={
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <ReviewStatusBadge status={item.status} />
            <span>{labelOf(reviewRuleLabels, item.rule)}</span>
            <span aria-hidden>·</span>
            <span>
              {entityKindLabels[item.entity_kind]} <SubjectLink item={item} />
            </span>
            {item.subject.country_code && (
              <>
                <span aria-hidden>·</span>
                <span>{item.subject.country_code}</span>
              </>
            )}
          </span>
        }
      >
        {open ? (
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
            {next && (
              <Button
                variant="ghost"
                nativeButton={false}
                render={<Link href={paths.reviewItem(next)} />}
              >
                Skip <ArrowRightIcon />
              </Button>
            )}
          </>
        ) : (
          next && (
            <Button nativeButton={false} render={<Link href={paths.reviewItem(next)} />}>
              Next open item <ArrowRightIcon />
            </Button>
          )
        )}
      </PageHeader>

      <div className="mb-6 flex flex-col gap-3 empty:hidden">
        {!open && <DecidedNotice item={item} timeZone={timeZone} />}
        {item.same_kind_open > 0 && item.kind && (
          <Alert>
            <LayersIcon />
            <AlertTitle>{othersAsking(item.same_kind_open, item.entity_kind, open)}</AlertTitle>
            <AlertDescription>
              <Link href={paths.reviewWhere(toSearchString({ kind: item.kind }))}>
                {open ? "Decide them together in the queue" : "See them in the queue"}
              </Link>
            </AlertDescription>
          </Alert>
        )}
      </div>

      <div className="flex flex-col gap-6">
        {compared && entityCard}

        <Card>
          <CardHeader>
            <CardTitle>
              {item.rule === "agent" ? "What the agent asked" : "Why it was raised"}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {reasons.length > 0 && (
              <ul className="flex flex-col gap-2 text-sm">
                {reasons.map((reason) => (
                  <li key={reason} className="border-l-2 pl-3">
                    <CollapsibleText text={reason} limit={1000} />
                  </li>
                ))}
              </ul>
            )}
            <QuestionFacts
              question={item.question}
              hidden={new Set(item.related.map((related) => related.fact))}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              Evidence{" "}
              <span className="font-normal text-muted-foreground tabular-nums">
                {item.evidence.length}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <EvidenceList
              evidence={raisedFirst(item.evidence, item.raised_by_assignment_id)}
              mark={(quote) =>
                item.raised_by_assignment_id &&
                quote.assignment_id === item.raised_by_assignment_id && (
                  <Badge variant="warning">Found by the raising assignment</Badge>
                )
              }
            />
          </CardContent>
        </Card>

        {!compared && entityCard}

        <Card>
          <CardHeader>
            <CardTitle>History</CardTitle>
          </CardHeader>
          <CardContent>
            <ReviewHistory item={item} timeZone={timeZone} />
          </CardContent>
        </Card>

        <RawData item={item} timeZone={timeZone} />
      </div>
      {actions.dialog}
    </>
  );
}

/** The item's entity: its page, else its page on the web, shortened. */
function SubjectLink({ item }: { item: Item }) {
  const { subject } = item;
  if (subject.url) {
    return (
      <ExternalLink href={subject.url} className="max-w-md align-bottom">
        {shortUrl(subject.url)}
      </ExternalLink>
    );
  }
  return <EntityRefLink entity={subject} />;
}

/** The quotes the raising assignment entered first, each group oldest first. */
function raisedFirst(evidence: EvidenceOutput[], assignmentId: string | null): EvidenceOutput[] {
  if (!assignmentId) return evidence;
  return [
    ...evidence.filter((quote) => quote.assignment_id === assignmentId),
    ...evidence.filter((quote) => quote.assignment_id !== assignmentId),
  ];
}

function DecidedNotice({ item, timeZone }: { item: Item; timeZone: string }) {
  const verb = { approved: "Approved", rejected: "Rejected", merged: "Merged", open: "" }[
    item.status
  ];
  return (
    <Alert>
      <AlertTitle>
        {verb} {formatDateTime(item.decided_at, timeZone)}
      </AlertTitle>
      <AlertDescription>
        {item.note ?? "No note was left."}
        {!item.next_open_id && " The queue has no other open items."}
      </AlertDescription>
    </Alert>
  );
}

/** The entity's columns and the question as stored, for when the summary is not enough. */
function RawData({ item, timeZone }: { item: Item; timeZone: string }) {
  return (
    <Collapsible>
      <CollapsibleTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            className="group/raw w-fit text-muted-foreground [&_svg]:transition-transform data-[panel-open]:[&_svg]:rotate-90"
          />
        }
      >
        <ChevronRightIcon /> Raw data
      </CollapsibleTrigger>
      <CollapsibleContent>
        <Card className="mt-2">
          <CardContent className="flex flex-col gap-4">
            <dl className="flex flex-col gap-2 text-sm">
              {Object.entries(item.entity)
                .filter(([, value]) => value !== null)
                .map(([key, value]) => (
                  <Detail key={key} label={humanize(key)}>
                    <EntityValue column={key} value={value} timeZone={timeZone} />
                  </Detail>
                ))}
            </dl>
            <div className="flex flex-col gap-1">
              <span className="text-sm text-muted-foreground">Question</span>
              <JsonView value={item.question} className="max-h-64" />
            </div>
          </CardContent>
        </Card>
      </CollapsibleContent>
    </Collapsible>
  );
}

function EntityValue({
  column,
  value,
  timeZone,
}: {
  column: string;
  value: unknown;
  timeZone: string;
}): ReactNode {
  if (typeof value === "string" && ISO_INSTANT.test(value)) {
    return formatDateTime(value, timeZone);
  }
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
