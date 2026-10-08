"use client";

import type { EntityRefOutput, EntitySummaryOutput } from "@public-atlas/api-client";
import Link from "next/link";
import type { ReactNode } from "react";

import { ExternalLink } from "@/components/shared/external-link";
import { EntityStatusBadge } from "@/components/shared/status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { entityKindLabels, humanize } from "@/lib/labels";
import { paths } from "@/lib/routes";
import { cn } from "@/lib/utils";

/** An entity's page in the console; null for the kinds without one. */
export function entityHref(ref: Pick<EntityRefOutput, "id" | "entity_kind">) {
  switch (ref.entity_kind) {
    case "institution":
      return paths.institution(ref.id);
    case "place":
      return paths.place(ref.id);
    default:
      return null;
  }
}

/** A reference as a link to its page, or as text for a kind without one. */
export function EntityRefLink({ entity }: { entity: EntityRefOutput }) {
  const href = entityHref(entity);
  return href ? (
    <Link href={href} className="hover:underline">
      {entity.label}
    </Link>
  ) : (
    entity.label
  );
}

/** The entity's name, linked to its page, or out to its page on the web. */
function EntityName({ entity }: { entity: EntitySummaryOutput }) {
  const href = entityHref(entity);
  if (href) {
    return (
      <Link href={href} className="font-medium hover:underline">
        {entity.label}
      </Link>
    );
  }
  const url = entity.url ?? (entity.entity_kind === "domain" ? `https://${entity.label}` : null);
  return url ? (
    <ExternalLink href={url} className="font-medium">
      {entity.label}
    </ExternalLink>
  ) : (
    <span className="font-medium">{entity.label}</span>
  );
}

/** A URL without its scheme or a bare trailing slash: "www.oakville.ca/library". */
export function shortUrl(url: string): string {
  return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
}

function typeOf(entity: EntitySummaryOutput): ReactNode {
  if (!entity.institution_type) return null;
  const type = humanize(entity.institution_type);
  return entity.suggested_type ? `${type} (suggested: ${entity.suggested_type})` : type;
}

interface Field {
  label: string;
  value: (entity: EntitySummaryOutput) => ReactNode;
  /** The text two columns are compared by; the value's own when absent. */
  text?: (entity: EntitySummaryOutput) => string | null;
  /** False for a field whose difference says nothing about sameness, such as the status. */
  compare?: boolean;
}

const FIELDS: Field[] = [
  {
    label: "Status",
    value: (entity) => <EntityStatusBadge status={entity.status} />,
    compare: false,
  },
  {
    label: "Kind",
    value: (entity) => entityKindLabels[entity.entity_kind],
    compare: false,
  },
  {
    label: "Also called",
    value: (entity) => entity.names.filter((name) => name !== entity.label).join(", ") || null,
    compare: false,
  },
  { label: "Type", value: typeOf, text: (entity) => entity.institution_type },
  {
    label: "Level",
    value: (entity) => (entity.administrative_level ? humanize(entity.administrative_level) : null),
  },
  {
    label: "Place",
    value: (entity) => entity.place && <EntityRefLink entity={entity.place} />,
    text: (entity) => entity.place?.id ?? null,
  },
  {
    label: "Part of",
    value: (entity) => entity.parent && <EntityRefLink entity={entity.parent} />,
    text: (entity) => entity.parent?.id ?? null,
  },
  {
    label: "Belongs to",
    value: (entity) => entity.owner && <EntityRefLink entity={entity.owner} />,
    text: (entity) => entity.owner?.id ?? null,
  },
  {
    label: "Homepage",
    value: (entity) =>
      entity.homepage_url && (
        <ExternalLink href={entity.homepage_url}>{shortUrl(entity.homepage_url)}</ExternalLink>
      ),
    text: (entity) => entity.homepage_url,
  },
  {
    label: "Page",
    value: (entity) =>
      entity.entity_kind === "source" && entity.url ? (
        <ExternalLink href={entity.url}>{shortUrl(entity.url)}</ExternalLink>
      ) : null,
    text: (entity) => (entity.entity_kind === "source" ? entity.url : null),
  },
  { label: "Country", value: (entity) => entity.country_code },
  {
    label: "Evidence",
    value: (entity) =>
      `${entity.evidence_count} ${entity.evidence_count === 1 ? "quote" : "quotes"}`,
    compare: false,
  },
];

function textOf(field: Field, entity: EntitySummaryOutput): string | null {
  if (field.text) return field.text(entity);
  const value = field.value(entity);
  return typeof value === "string" ? value : null;
}

export interface ComparedEntity {
  entity: EntitySummaryOutput;
  /** What the column is, above the name: "This institution", "Possible match". */
  heading: string;
  /** Under the column, such as "Merge into this". */
  action?: ReactNode;
}

/**
 * The item's entity in the first column and each entity its question names
 * beside it, field by field. A field shows when any column has it; a value
 * that differs from the first column's is set apart, so a duplicate's
 * differences stand out.
 */
export function EntityComparison({ columns }: { columns: ComparedEntity[] }) {
  const [first] = columns;
  if (!first) return null;
  const kinds = new Set(columns.map((column) => column.entity.entity_kind));
  const fields = FIELDS.filter(
    (field) =>
      (field.label !== "Kind" || kinds.size > 1) &&
      columns.some((column) => {
        const value = field.value(column.entity);
        return value !== null && value !== undefined && value !== false;
      }),
  );
  const compared = columns.length > 1;
  return (
    <div className="overflow-x-auto">
      {/* Equal columns, each wide enough to read; past the page's width the table scrolls. */}
      <Table className="table-fixed" style={{ minWidth: `${7 + columns.length * 11}rem` }}>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-28">
              <span className="sr-only">Field</span>
            </TableHead>
            {columns.map((column) => (
              <TableHead key={column.entity.id} className="h-auto py-2 align-top whitespace-normal">
                <span className="flex flex-col gap-0.5">
                  <span className="text-xs font-normal text-muted-foreground">
                    {column.heading}
                  </span>
                  <span className="break-words">
                    <EntityName entity={column.entity} />
                  </span>
                </span>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {fields.map((field) => (
            <TableRow key={field.label} className="hover:bg-transparent">
              <TableCell className="align-top text-muted-foreground">{field.label}</TableCell>
              {columns.map((column, index) => {
                const value = field.value(column.entity);
                const differs =
                  compared &&
                  index > 0 &&
                  field.compare !== false &&
                  textOf(field, column.entity) !== textOf(field, first.entity);
                return (
                  <TableCell
                    key={column.entity.id}
                    className={cn(
                      "align-top break-words whitespace-normal",
                      differs && "bg-warning/8 dark:bg-warning/10",
                    )}
                  >
                    {value ?? <span className="text-muted-foreground">–</span>}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
          {columns.some((column) => column.action) && (
            <TableRow className="hover:bg-transparent">
              <TableCell />
              {columns.map((column) => (
                <TableCell key={column.entity.id}>{column.action}</TableCell>
              ))}
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
