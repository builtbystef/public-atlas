import type { PlaceDetail as PlaceDetailOutput } from "@public-atlas/api-client";
import Link from "next/link";
import type { ReactNode } from "react";

import { Detail } from "@/components/shared/detail-list";
import { PageHeader } from "@/components/shared/layout/page-header";
import { EntityStatusBadge } from "@/components/shared/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { formatDateTime } from "@/lib/formatting/dates";
import { enteredByLabels, humanize } from "@/lib/labels";
import { paths } from "@/lib/routes";

import { Population } from "./population";

/**
 * One place: where it sits, its population and government, and below, the
 * places under it and the institutions in it, which the page streams in.
 */
export function PlaceDetail({
  place,
  timeZone,
  actions,
  children,
}: {
  place: PlaceDetailOutput;
  timeZone: string;
  /** Buttons beside the name: the page's link into the graph view. */
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            {place.name}
            <EntityStatusBadge status={place.status} />
          </span>
        }
        description={
          <span>
            {humanize(place.administrative_level)}
            {place.parents.length > 0 && " in "}
            {place.parents.map((parent, index) => (
              <span key={parent.id}>
                {index > 0 && " › "}
                <Link href={paths.place(parent.id)} className="hover:underline">
                  {parent.name}
                </Link>
              </span>
            ))}
          </span>
        }
      >
        {actions}
      </PageHeader>
      <Card className="mb-8">
        <CardContent>
          <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <Detail label="Population">
              {place.population !== null && <Population value={place.population} />}
            </Detail>
            <Detail label="Government">
              {place.government && (
                <Link href={paths.institution(place.government.id)} className="hover:underline">
                  {place.government.name}
                </Link>
              )}
            </Detail>
            <Detail label="Country">{place.country_code}</Detail>
            <Detail label="Level">{humanize(place.administrative_level)}</Detail>
            <Detail label="Entered by">{enteredByLabels[place.entered_by]}</Detail>
            <Detail label="Created">{formatDateTime(place.created_at, timeZone)}</Detail>
          </dl>
        </CardContent>
      </Card>
      <div className="flex flex-col gap-10">{children}</div>
    </>
  );
}
