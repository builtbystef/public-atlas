"use client";

import { useSuspenseQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { browserApi } from "@/lib/api/client";
import { humanize, labelOf, reviewRuleLabels } from "@/lib/labels";

import type { useReviewActions } from "../hooks/use-review-actions";
import { reviewKindsQuery } from "../queries";
import { QuestionFacts } from "./question-facts";

const REFRESH_MS = 15_000;

/** The shared questions: one card each, decided for every item at once. */
export function ReviewKinds({ actions }: { actions: ReturnType<typeof useReviewActions> }) {
  const { data: kinds } = useSuspenseQuery({
    ...reviewKindsQuery(browserApi),
    refetchInterval: REFRESH_MS,
  });
  if (kinds.length === 0) {
    return <EmptyState boxed>No shared questions are open.</EmptyState>;
  }
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {kinds.map((kind) => (
        <Card key={kind.kind}>
          <CardHeader>
            <CardTitle>{labelOf(reviewRuleLabels, kind.rule)}</CardTitle>
            <CardDescription>{kindQuestion(kind.rule, kind.question)}</CardDescription>
            <CardAction>
              <Badge variant="secondary">{kind.count}</Badge>
            </CardAction>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <QuestionFacts question={kind.question} />
            <p className="text-sm text-muted-foreground">
              {kind.names.join(", ")}
              {kind.count > kind.names.length && `, and ${kind.count - kind.names.length} more`}
            </p>
          </CardContent>
          <CardFooter className="gap-2">
            <Button onClick={() => actions.approveKind(kind)}>Approve all</Button>
            <Button variant="destructive" onClick={() => actions.rejectKind(kind)}>
              Reject all
            </Button>
          </CardFooter>
        </Card>
      ))}
    </div>
  );
}

function kindQuestion(rule: string, question: Record<string, unknown>): string {
  const type = question["institution_type"];
  const level = question["level"];
  const suggested = question["suggested_type"];
  if (rule === "type_level" && typeof type === "string" && typeof level === "string") {
    return `Does a ${humanize(type).toLowerCase()} belong under a ${humanize(level).toLowerCase()}?`;
  }
  if (rule === "new_type" && typeof suggested === "string") {
    return `Is “${suggested}” a type the country should have?`;
  }
  return "Decide once for every item that asks this.";
}
