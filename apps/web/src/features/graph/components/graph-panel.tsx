"use client";

import type { GraphNode } from "@public-atlas/api-client";
import { useQuery } from "@tanstack/react-query";
import { ExpandIcon, ExternalLinkIcon, XIcon } from "lucide-react";
import Link from "next/link";

import { Detail } from "@/components/shared/detail-list";
import { EmptyState } from "@/components/shared/empty-state";
import { ExternalLink } from "@/components/shared/external-link";
import { DetailSkeleton } from "@/components/shared/skeletons";
import { EntityStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { entityKindLabels, humanize } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { institutionQuery, placeQuery } from "../queries";
import { InstitutionDetail } from "./institution-detail";
import { PlaceDetail } from "./place-detail";

/**
 * The panel beside the canvas for the clicked node: a place or an institution
 * as its own page shows it, with a link to that page; a homepage, a source or
 * a domain as a short card, with the institution it belongs to.
 */
export function GraphPanel({
  node,
  owner,
  timeZone,
  onClose,
  onExpand,
  onSelect,
}: {
  node: GraphNode;
  /** For a homepage or a source: the institution it belongs to, when it is in the picture. */
  owner: GraphNode | undefined;
  timeZone: string;
  onClose: () => void;
  onExpand: (node: GraphNode) => void;
  onSelect: (id: string) => void;
}) {
  const page =
    node.kind === "place"
      ? paths.place(node.id)
      : node.kind === "institution"
        ? paths.institution(node.id)
        : null;
  const actions = (
    <>
      {(node.kind === "place" || node.kind === "institution") && (
        <Button variant="outline" onClick={() => onExpand(node)}>
          <ExpandIcon /> Expand
        </Button>
      )}
      {page && (
        <Button variant="outline" nativeButton={false} render={<Link href={page} />}>
          <ExternalLinkIcon /> Open page
        </Button>
      )}
      <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close panel">
        <XIcon />
      </Button>
    </>
  );
  return (
    <aside className="flex flex-col gap-4" aria-label={`${entityKindLabels[node.kind]} details`}>
      <div className="flex items-center justify-between gap-2">
        <Badge variant="secondary">{entityKindLabels[node.kind]}</Badge>
        <div className="flex items-center gap-2">{actions}</div>
      </div>
      {node.kind === "place" ? (
        <PlacePanel id={node.id} timeZone={timeZone} />
      ) : node.kind === "institution" ? (
        <InstitutionPanel id={node.id} timeZone={timeZone} />
      ) : (
        <WebPanel node={node} owner={owner} onSelect={onSelect} />
      )}
    </aside>
  );
}

function PlacePanel({ id, timeZone }: { id: string; timeZone: string }) {
  const place = useQuery(placeQuery(browserApi, id));
  if (place.isPending) return <DetailSkeleton />;
  if (place.isError) return <EmptyState boxed>{errorMessage(place.error)}</EmptyState>;
  return <PlaceDetail place={place.data} timeZone={timeZone} />;
}

function InstitutionPanel({ id, timeZone }: { id: string; timeZone: string }) {
  const institution = useQuery(institutionQuery(browserApi, id));
  if (institution.isPending) return <DetailSkeleton />;
  if (institution.isError) {
    return <EmptyState boxed>{errorMessage(institution.error)}</EmptyState>;
  }
  return <InstitutionDetail institution={institution.data} timeZone={timeZone} />;
}

/** A homepage, a source or a domain: what the graph itself knows of it. */
function WebPanel({
  node,
  owner,
  onSelect,
}: {
  node: GraphNode;
  owner: GraphNode | undefined;
  onSelect: (id: string) => void;
}) {
  return (
    <Card>
      <CardContent>
        <dl className="flex flex-col gap-3 text-sm">
          <Detail label={node.kind === "domain" ? "Domain" : "URL"}>
            {node.kind === "domain" ? (
              <ExternalLink href={`https://${node.label}/`}>{node.label}</ExternalLink>
            ) : (
              <ExternalLink href={node.label} />
            )}
          </Detail>
          <Detail label="Status">
            <EntityStatusBadge status={node.status} />
          </Detail>
          {node.source_type && <Detail label="Type">{humanize(node.source_type)}</Detail>}
          {node.domain_kind && (
            <Detail label="Kind">
              {node.domain_kind === "official"
                ? "Official: trusted once verified"
                : "Platform: anyone can publish on it"}
            </Detail>
          )}
          {node.kind !== "domain" && (
            <Detail label="Institution">
              {owner && (
                <span className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => onSelect(owner.id)}
                    className="text-left hover:underline"
                  >
                    {owner.label}
                  </button>
                  <Link
                    href={paths.institution(owner.id)}
                    className="text-xs text-muted-foreground hover:underline"
                  >
                    Open page
                  </Link>
                </span>
              )}
            </Detail>
          )}
        </dl>
      </CardContent>
    </Card>
  );
}
