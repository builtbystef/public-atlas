"use client";

import type { EvidenceOutput } from "@public-atlas/api-client";
import { useQuery } from "@tanstack/react-query";
import { DownloadIcon, Loader2Icon } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { EmptyState } from "@/components/shared/empty-state";
import { ExternalLink } from "@/components/shared/external-link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { humanize } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { evidenceContextQuery } from "../queries";

/**
 * Every quote behind an entity, with the page it was read on, the stored
 * snapshot to download, and the quote shown in place in the stored text.
 */
export function EvidenceList({
  evidence,
  labels = {},
  mark,
}: {
  evidence: EvidenceOutput[];
  /** A badge for the quotes to set apart, such as those the item under review was raised on. */
  mark?: (item: EvidenceOutput) => ReactNode;
  /** What each `entity_id` is, for lists that mix an institution with its homepages and sources. */
  labels?: Record<string, ReactNode>;
}) {
  if (evidence.length === 0) {
    return <EmptyState>No evidence recorded.</EmptyState>;
  }
  return (
    <ol className="flex flex-col divide-y">
      {evidence.map((item) => (
        <li key={item.id} className="flex flex-col gap-2 py-4 first:pt-0 last:pb-0">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline">{humanize(item.kind)}</Badge>
            {mark?.(item)}
            {labels[item.entity_id] && (
              <span className="text-foreground">{labels[item.entity_id]}</span>
            )}
            <span>by {item.entered_by}</span>
            {item.assignment_id && (
              <Link href={paths.assignment(item.assignment_id)} className="hover:underline">
                assignment
              </Link>
            )}
            {item.locator !== null && <span>page {item.locator}</span>}
          </div>
          <blockquote className="border-l-2 pl-3 text-sm whitespace-pre-wrap">
            “{item.quote}”
          </blockquote>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
            <ExternalLink href={item.page_url} className="max-w-md" />
            {item.link_url && (
              <span className="inline-flex max-w-md items-center gap-1 text-muted-foreground">
                links to <ExternalLink href={item.link_url} />
              </span>
            )}
            {item.snapshot_url ? (
              <a
                href={item.snapshot_url}
                className="inline-flex items-center gap-1 hover:underline"
              >
                <DownloadIcon className="size-3.5" /> Snapshot
              </a>
            ) : (
              <span className="text-muted-foreground">Snapshot pruned</span>
            )}
            <QuoteContext evidenceId={item.id} />
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Loads the stored text around the quote on demand and highlights it. */
function QuoteContext({ evidenceId }: { evidenceId: string }) {
  const [open, setOpen] = useState(false);
  const context = useQuery({ ...evidenceContextQuery(browserApi, evidenceId), enabled: open });
  return (
    <>
      <Button variant="link" size="xs" className="px-0" onClick={() => setOpen(!open)}>
        {open ? "Hide the page" : "Show on the page"}
      </Button>
      {open && (
        <div className="basis-full">
          {context.isPending ? (
            <p className="inline-flex items-center gap-1 text-muted-foreground">
              <Loader2Icon className="size-3 animate-spin" /> Reading the stored text…
            </p>
          ) : context.isError ? (
            <p className="text-destructive">{errorMessage(context.error)}</p>
          ) : (
            <div className="flex flex-col gap-1">
              {!context.data.found && (
                <p className="text-muted-foreground">
                  The quote is not in the stored text as written; the page may have changed before
                  it was stored.
                </p>
              )}
              <p className="rounded-md bg-muted p-3 text-sm leading-relaxed break-words">
                {context.data.before}
                <mark className="rounded-sm bg-warning/30 px-0.5 text-foreground dark:bg-warning/35">
                  {context.data.quote}
                </mark>
                {context.data.after}
              </p>
              {context.data.page !== null && (
                <p className="text-muted-foreground">Page {context.data.page} of the file.</p>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}
