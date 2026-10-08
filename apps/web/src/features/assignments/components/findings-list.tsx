"use client";

import type { FindingOutput } from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { DownloadIcon } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/shared/empty-state";
import { ExternalLink } from "@/components/shared/external-link";
import { EntityStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { browserApi } from "@/lib/api/client";
import { entityKindLabels, humanize } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { assignmentFindingsQuery } from "../queries";

const REFRESH_MS = 5_000;

/** What the assignment saved, with the quote behind each save and its stored page. */
export function FindingsList({ assignmentId, live }: { assignmentId: string; live: boolean }) {
  const { data: findings } = useSuspenseQuery({
    ...assignmentFindingsQuery(browserApi, assignmentId),
    refetchInterval: live ? REFRESH_MS : false,
  });
  if (findings.length === 0) {
    return <EmptyState boxed>Nothing saved yet.</EmptyState>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border bg-card shadow-xs">
      <Table>
        <TableHeader className="bg-muted/50">
          <TableRow className="hover:bg-transparent">
            <TableHead>Saved</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Quote</TableHead>
            <TableHead>Read on</TableHead>
            <TableHead className="w-0">Snapshot</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {findings.map((finding) => {
            const { title, url } = splitLabel(finding.label);
            return (
              <TableRow key={finding.evidence_id}>
                <TableCell className="min-w-56 max-w-xs py-3 align-top whitespace-normal">
                  <div className="flex flex-col gap-1.5">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <Badge variant="outline">{entityKindLabels[finding.entity_kind]}</Badge>
                      <FindingLabel finding={finding}>{title}</FindingLabel>
                    </div>
                    {url && url !== finding.page_url && (
                      <span className="font-mono text-xs wrap-anywhere text-muted-foreground">
                        {url}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="py-3 align-top">
                  <EntityStatusBadge status={finding.entity_status} />
                </TableCell>
                <TableCell className="min-w-72 max-w-md py-3 align-top whitespace-normal">
                  <blockquote className="line-clamp-3 text-muted-foreground" title={finding.quote}>
                    “{finding.quote}”
                  </blockquote>
                </TableCell>
                <TableCell className="max-w-56 py-3 align-top">
                  <ExternalLink href={finding.page_url} className="text-xs" />
                </TableCell>
                <TableCell className="py-3 align-top">
                  {finding.snapshot_url ? (
                    <a
                      href={finding.snapshot_url}
                      className="inline-flex items-center gap-1 text-xs hover:underline"
                      aria-label="Download the snapshot"
                    >
                      <DownloadIcon className="size-3.5" /> Download
                    </a>
                  ) : (
                    <span className="text-xs text-muted-foreground">Pruned</span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

const TYPED_URL = /^(\w+) (https?:\/\/\S+)$/;

/**
 * The API labels a saved source "type url"; split so the type reads as a
 * name and the URL as a second line. Any other label is the name as given.
 */
function splitLabel(label: string): { title: string; url: string | null } {
  const match = TYPED_URL.exec(label);
  if (!match) return { title: label, url: null };
  return { title: humanize(match[1]!), url: match[2]! };
}

function FindingLabel({ finding, children }: { finding: FindingOutput; children: string }) {
  const institutionId =
    finding.entity_kind === "institution" ? finding.entity_id : finding.institution_id;
  if (!institutionId) {
    return <span className="font-medium wrap-anywhere">{children}</span>;
  }
  return (
    <Link
      href={paths.institution(institutionId)}
      className="font-medium wrap-anywhere hover:underline"
    >
      {children}
    </Link>
  );
}
