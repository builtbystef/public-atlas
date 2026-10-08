"use client";

import type { ReviewRow } from "@public-atlas/api-client";
import Link from "next/link";

import { formatDateTime } from "@/lib/formatting/dates";
import { entityKindLabels } from "@/lib/labels";
import { paths } from "@/lib/routes";

import type { useReviewActions } from "../hooks/use-review-actions";
import { QuestionFacts } from "./question-facts";
import { ItemActions } from "./review-columns";

/**
 * The items of a row that decides several, under it: each can still be
 * opened, or decided on its own when it is the exception.
 */
export function ReviewMembers({
  row,
  timeZone,
  actions,
}: {
  row: ReviewRow;
  timeZone: string;
  actions: ReturnType<typeof useReviewActions>;
}) {
  const hidden = row.count - row.members.length;
  return (
    <div className="flex flex-col gap-3 border-l-2 border-l-primary bg-muted/30 px-4 py-3 pl-12">
      <QuestionFacts question={row.question} />
      <ul className="flex flex-col divide-y rounded-md border bg-card">
        {row.members.map((member) => (
          <li
            key={member.id}
            className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-sm"
          >
            <span className="flex min-w-48 flex-1 flex-col gap-0.5">
              <Link
                href={paths.reviewItem(member.id)}
                className="font-medium break-all hover:underline"
              >
                {member.label}
              </Link>
              <span className="text-xs text-muted-foreground">
                {entityKindLabels[member.entity_kind]}
                {member.country_code && ` · ${member.country_code}`}
                {` · raised ${formatDateTime(member.raised_at, timeZone)}`}
              </span>
            </span>
            {member.reasons.length > 0 && (
              <span className="line-clamp-2 min-w-48 flex-1 text-xs text-muted-foreground">
                {member.reasons.join(" · ")}
              </span>
            )}
            {row.status === "open" && (
              <ItemActions item={{ ...member, kind: row.kind }} actions={actions} size="xs" />
            )}
          </li>
        ))}
      </ul>
      {hidden > 0 && (
        <p className="text-xs text-muted-foreground">
          {`Showing the first ${row.members.length} of ${row.count}. A decision on the row covers all ${row.count}; search to narrow them.`}
        </p>
      )}
    </div>
  );
}
