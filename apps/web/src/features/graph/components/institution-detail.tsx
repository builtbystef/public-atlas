import type { InstitutionDetail as InstitutionDetailOutput } from "@public-atlas/api-client";
import Link from "next/link";
import type { ReactNode } from "react";

import { Detail } from "@/components/shared/detail-list";
import { EmptyState } from "@/components/shared/empty-state";
import { ExternalLink } from "@/components/shared/external-link";
import { PageHeader } from "@/components/shared/layout/page-header";
import { EntityStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/formatting/dates";
import { enteredByLabels, humanize, sourceAccessLabels } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { EvidenceList } from "./evidence-list";

/**
 * One institution as the graph holds it (spec section 4): its names and
 * codes, where it sits, its homepage with the domain's trust, its sources by
 * type, and the quote behind every one of those claims.
 */
export function InstitutionDetail({
  institution,
  timeZone,
  children,
}: {
  institution: InstitutionDetailOutput;
  timeZone: string;
  /** The assignments section, which the page streams separately. */
  children?: ReactNode;
}) {
  const labels: Record<string, ReactNode> = { [institution.id]: "Institution" };
  for (const homepage of institution.homepages) labels[homepage.id] = `Homepage ${homepage.url}`;
  for (const source of institution.sources) {
    labels[source.id] = `${humanize(source.source_type)} ${source.url}`;
  }
  const sourcesByType = new Map<string, InstitutionDetailOutput["sources"]>();
  for (const source of institution.sources) {
    const list = sourcesByType.get(source.source_type) ?? [];
    list.push(source);
    sourcesByType.set(source.source_type, list);
  }

  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            {institution.name}
            <EntityStatusBadge status={institution.status} />
          </span>
        }
        description={
          <span>
            {humanize(institution.institution_type)}
            {institution.suggested_type && ` (suggested: ${institution.suggested_type})`} ·{" "}
            {institution.places.map((place, index) => (
              <span key={place.id}>
                {index > 0 && " › "}
                <Link href={paths.place(place.id)} className="hover:underline">
                  {place.name}
                </Link>
              </span>
            ))}
          </span>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="flex flex-col gap-3 text-sm">
              <Detail label="Homepage">
                {institution.homepage_url && <ExternalLink href={institution.homepage_url} />}
              </Detail>
              <Detail label="Parent">
                {institution.parent && (
                  <Link href={paths.institution(institution.parent.id)} className="hover:underline">
                    {institution.parent.name}
                  </Link>
                )}
              </Detail>
              <Detail label="Procurement">
                {institution.procurement_handled_by === "parent"
                  ? "Handled by the parent"
                  : "Handled by itself"}
              </Detail>
              <Detail label="Level">{humanize(institution.place.administrative_level)}</Detail>
              <Detail label="Entered by">{enteredByLabels[institution.entered_by]}</Detail>
              <Detail label="Created">{formatDateTime(institution.created_at, timeZone)}</Detail>
              <Detail label="Serves">
                {institution.served_places.length > 0 &&
                  institution.served_places.map((place, index) => (
                    <span key={place.id}>
                      {index > 0 && ", "}
                      <Link href={paths.place(place.id)} className="hover:underline">
                        {place.name}
                      </Link>
                    </span>
                  ))}
              </Detail>
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Names and codes</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 text-sm">
            <div className="flex flex-col gap-2">
              <h4 className="text-xs font-medium text-muted-foreground uppercase">Aliases</h4>
              {institution.aliases.length === 0 ? (
                <EmptyState>None.</EmptyState>
              ) : (
                <ul className="flex flex-wrap gap-1.5">
                  {institution.aliases.map((alias) => (
                    <li key={`${alias.text}-${alias.language}`}>
                      <Badge variant="secondary" className="font-normal">
                        {alias.text}
                        <span className="text-muted-foreground">
                          {alias.language}
                          {alias.is_acronym && " · acronym"}
                        </span>
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="flex flex-col gap-2">
              <h4 className="text-xs font-medium text-muted-foreground uppercase">Identifiers</h4>
              {institution.identifiers.length === 0 ? (
                <EmptyState>None.</EmptyState>
              ) : (
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                  {institution.identifiers.map((identifier) => (
                    <div key={`${identifier.scheme}-${identifier.value}`} className="contents">
                      <dt className="text-muted-foreground">{identifier.scheme}</dt>
                      <dd className="font-mono text-xs">{identifier.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
            <div className="flex flex-col gap-2">
              <h4 className="text-xs font-medium text-muted-foreground uppercase">Metrics</h4>
              {institution.metrics.length === 0 ? (
                <EmptyState>None.</EmptyState>
              ) : (
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                  {institution.metrics.map((metric) => (
                    <div key={`${metric.name}-${metric.year}`} className="contents">
                      <dt className="text-muted-foreground">
                        {humanize(metric.name)} ({metric.year})
                      </dt>
                      <dd className="tabular-nums">{metric.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Bodies under it</CardTitle>
          </CardHeader>
          <CardContent>
            {institution.children.length === 0 ? (
              <EmptyState>None.</EmptyState>
            ) : (
              <ul className="flex flex-col gap-2 text-sm">
                {institution.children.map((child) => (
                  <li key={child.id} className="flex flex-wrap items-center gap-2">
                    <Link href={paths.institution(child.id)} className="hover:underline">
                      {child.name}
                    </Link>
                    <span className="text-xs text-muted-foreground">
                      {humanize(child.institution_type)}
                    </span>
                    <EntityStatusBadge status={child.status} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <section className="mt-8 flex flex-col gap-4">
        <h3 className="text-lg font-semibold">Homepages</h3>
        {institution.homepages.length === 0 ? (
          <EmptyState boxed>No homepage claimed yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>URL</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Domain</TableHead>
                  <TableHead>Found on</TableHead>
                  <TableHead>Entered by</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {institution.homepages.map((homepage) => (
                  <TableRow key={homepage.id}>
                    <TableCell className="max-w-72">
                      <ExternalLink href={homepage.url} />
                      {homepage.trusted_path && (
                        <p className="text-xs text-muted-foreground">
                          trusted path {homepage.trusted_path}
                        </p>
                      )}
                      {homepage.rejected_reason && (
                        <p className="text-xs text-destructive">{homepage.rejected_reason}</p>
                      )}
                    </TableCell>
                    <TableCell>
                      <EntityStatusBadge status={homepage.status} />
                    </TableCell>
                    <TableCell>
                      <span className="flex flex-wrap items-center gap-2">
                        {homepage.domain}
                        {homepage.domain_status && (
                          <EntityStatusBadge status={homepage.domain_status} />
                        )}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-56">
                      {homepage.found_on_url && (
                        <ExternalLink href={homepage.found_on_url} className="text-xs" />
                      )}
                    </TableCell>
                    <TableCell>{enteredByLabels[homepage.entered_by]}</TableCell>
                    <TableCell className="whitespace-nowrap">
                      {formatDateTime(homepage.created_at, timeZone)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <section className="mt-8 flex flex-col gap-4">
        <h3 className="text-lg font-semibold">Sources</h3>
        {sourcesByType.size === 0 ? (
          <EmptyState boxed>No sources saved yet.</EmptyState>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {[...sourcesByType.entries()].map(([sourceType, sources]) => (
              <Card key={sourceType}>
                <CardHeader>
                  <CardTitle>{humanize(sourceType)}</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="flex flex-col gap-3 text-sm">
                    {sources.map((source) => (
                      <li key={source.id} className="flex flex-col gap-1">
                        <ExternalLink href={source.url} />
                        <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <EntityStatusBadge status={source.status} />
                          {sourceAccessLabels[source.access]} · {enteredByLabels[source.entered_by]}
                        </span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="mt-8 flex flex-col gap-4">
        <h3 className="text-lg font-semibold">Evidence</h3>
        <Card>
          <CardContent>
            <EvidenceList evidence={institution.evidence} labels={labels} />
          </CardContent>
        </Card>
      </section>

      {children}
    </>
  );
}
