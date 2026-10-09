"use client";

import type { GraphNode } from "@public-atlas/api-client";
import { ChevronRightIcon, ExternalLinkIcon, XIcon } from "lucide-react";
import Link from "next/link";

import { Detail } from "@/components/shared/detail-list";
import { ExternalLink } from "@/components/shared/external-link";
import { EntityStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { formatCount } from "@/lib/formatting/money";
import { entityKindLabels, entityStatusLabels, humanize } from "@/lib/labels";
import { paths } from "@/lib/routes";
import { cn } from "@/lib/utils";

import { shortLabel, type Connection } from "../graph-data";
import { Population } from "./population";

export const kindDot: Record<GraphNode["kind"], string> = {
  place: "bg-graph-place",
  institution: "bg-graph-institution",
  homepage: "bg-graph-homepage",
  source: "bg-graph-source",
  domain: "bg-graph-domain",
};

/** The connection groups that can run long; they start folded so the short ones stay in view. */
const FOLDED = new Set(["Places within", "Institutions", "Sources"]);

/**
 * The panel beside the canvas for the clicked node: what the graph knows of
 * it in a few lines, a link to its page, and its connections grouped by what
 * they are to it, each a step to take in the picture.
 */
export function GraphPanel({
  node,
  connections,
  onClose,
  onSelect,
}: {
  node: GraphNode;
  connections: Connection[];
  onClose: () => void;
  onSelect: (id: string) => void;
}) {
  const page =
    node.kind === "place"
      ? paths.place(node.id)
      : node.kind === "institution"
        ? paths.institution(node.id)
        : null;
  return (
    <aside className="flex flex-col gap-4" aria-label={`${entityKindLabels[node.kind]} details`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="secondary">{entityKindLabels[node.kind]}</Badge>
            <EntityStatusBadge status={node.status} />
          </div>
          <h2 className="font-heading text-base font-medium wrap-anywhere">
            {node.kind === "homepage" || node.kind === "source" ? shortLabel(node) : node.label}
          </h2>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close panel">
          <XIcon />
        </Button>
      </div>
      <dl className="flex flex-col gap-2 text-sm">
        <Facts node={node} />
      </dl>
      {page && (
        <div>
          <Button variant="outline" size="sm" nativeButton={false} render={<Link href={page} />}>
            <ExternalLinkIcon /> Open page
          </Button>
        </div>
      )}
      {/* Keyed by the node, so each one's groups start in their default fold. */}
      <section key={node.id} className="flex flex-col gap-3" aria-label="Connections">
        {connections.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing connected to it is in the picture.
          </p>
        ) : (
          connections.map((group) => (
            <Collapsible
              key={group.label}
              defaultOpen={!FOLDED.has(group.label)}
              className="flex flex-col gap-1"
            >
              <CollapsibleTrigger className="group/fold flex items-center gap-1 rounded-md text-left text-xs font-medium text-muted-foreground hover:text-foreground">
                <ChevronRightIcon
                  className="size-3.5 transition-transform group-data-panel-open/fold:rotate-90"
                  aria-hidden="true"
                />
                {group.label}
                <span className="tabular-nums">({group.nodes.length})</span>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <ul className="flex flex-col">
                  {group.nodes.map((other) => (
                    <li key={other.id}>
                      <button
                        type="button"
                        onClick={() => onSelect(other.id)}
                        className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-sm hover:bg-muted"
                      >
                        <span
                          aria-hidden="true"
                          className={cn("size-2 shrink-0 rounded-full", kindDot[other.kind])}
                        />
                        <span className="min-w-0 flex-1 truncate">{shortLabel(other)}</span>
                        {other.status !== "verified" && (
                          <span className="shrink-0 text-xs text-muted-foreground">
                            {entityStatusLabels[other.status]}
                          </span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </CollapsibleContent>
            </Collapsible>
          ))
        )}
      </section>
    </aside>
  );
}

/** The few facts the graph carries about a node, by kind. */
function Facts({ node }: { node: GraphNode }) {
  switch (node.kind) {
    case "place":
      return (
        <>
          {node.administrative_level && (
            <Detail label="Level">{humanize(node.administrative_level)}</Detail>
          )}
          <Detail label="Population">
            <Population value={node.population} />
          </Detail>
          <Detail label="Beneath">
            {formatCount(node.child_count ?? 0)} {node.child_count === 1 ? "place" : "places"},{" "}
            {formatCount(node.institution_count ?? 0)}{" "}
            {node.institution_count === 1 ? "institution" : "institutions"}
          </Detail>
          <Detail label="Government">
            {node.online ? (
              <span className="text-success">Online</span>
            ) : node.governed ? (
              <span className="text-warning">No verified homepage</span>
            ) : (
              <span className="text-destructive">None</span>
            )}
          </Detail>
        </>
      );
    case "institution":
      return (
        <>
          {node.institution_type && <Detail label="Type">{humanize(node.institution_type)}</Detail>}
          <Detail label="Homepage">
            {node.has_homepage ? (
              <span className="text-success">Verified</span>
            ) : (node.homepage_count ?? 0) > 0 ? (
              <span className="text-warning">
                {node.homepage_count} {node.homepage_count === 1 ? "claim" : "claims"} awaiting
                review
              </span>
            ) : (
              <span className="text-destructive">None</span>
            )}
          </Detail>
          <Detail label="Sources">{formatCount(node.source_count ?? 0)}</Detail>
        </>
      );
    case "homepage":
    case "source":
      return (
        <>
          <Detail label="URL">
            <ExternalLink href={node.label} />
          </Detail>
          {node.source_type && <Detail label="Type">{humanize(node.source_type)}</Detail>}
        </>
      );
    case "domain":
      return (
        <>
          <Detail label="Domain">
            <ExternalLink href={`https://${node.label}/`}>{node.label}</ExternalLink>
          </Detail>
          {node.domain_kind && (
            <Detail label="Kind">
              {node.domain_kind === "official"
                ? "Official: trusted once verified"
                : "Platform: anyone can publish on it"}
            </Detail>
          )}
        </>
      );
  }
}
