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
import { entityKindLabels } from "@/lib/labels";
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
    return <EmptyState>Nothing saved yet.</EmptyState>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Saved</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Quote</TableHead>
            <TableHead>Page</TableHead>
            <TableHead className="w-0">Snapshot</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {findings.map((finding) => (
            <TableRow key={finding.evidence_id}>
              <TableCell className="max-w-72">
                <div className="flex flex-col gap-1">
                  <FindingLabel finding={finding} />
                  <Badge variant="outline" className="w-fit">
                    {entityKindLabels[finding.entity_kind]}
                  </Badge>
                </div>
              </TableCell>
              <TableCell>
                <EntityStatusBadge status={finding.entity_status} />
              </TableCell>
              <TableCell className="max-w-md">
                <blockquote className="line-clamp-3 text-sm whitespace-pre-wrap text-muted-foreground">
                  “{finding.quote}”
                </blockquote>
              </TableCell>
              <TableCell className="max-w-56">
                <ExternalLink href={finding.page_url} className="text-xs" />
              </TableCell>
              <TableCell>
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
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function FindingLabel({ finding }: { finding: FindingOutput }) {
  const institutionId =
    finding.entity_kind === "institution" ? finding.entity_id : finding.institution_id;
  if (!institutionId) {
    return <span className="break-all">{finding.label}</span>;
  }
  return (
    <Link href={paths.institution(institutionId)} className="font-medium break-all hover:underline">
      {finding.label}
    </Link>
  );
}
