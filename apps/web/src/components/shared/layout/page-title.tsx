"use client";

import { ChevronRightIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import { crumbsFor } from "@/lib/page-titles";

/**
 * Where the current page sits, shown in the shell header: the section, and on
 * a record page the section as a link back to its list. It is derived from
 * the URL, which is only known at request time, so it streams in behind a
 * <Suspense> while the rest of the shell is prerendered.
 */
export function PageTitle() {
  const crumbs = crumbsFor(usePathname());
  if (!crumbs) return null;
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1;
          return (
            <Fragment key={crumb.label}>
              {index > 0 && (
                <ChevronRightIcon
                  className="size-3.5 shrink-0 text-muted-foreground/60"
                  aria-hidden="true"
                />
              )}
              <li className="min-w-0">
                {crumb.href && !last ? (
                  <Link
                    href={crumb.href}
                    className="text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {crumb.label}
                  </Link>
                ) : (
                  <h1 className="truncate font-medium" aria-current="page">
                    {crumb.label}
                  </h1>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
