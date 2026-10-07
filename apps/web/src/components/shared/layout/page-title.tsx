"use client";

import { usePathname } from "next/navigation";

import { titleFor } from "@/lib/page-titles";

/**
 * The title of the current page, shown in the shell header. It is derived from
 * the URL, which is only known at request time, so it streams in behind a
 * <Suspense> while the rest of the shell is prerendered.
 */
export function PageTitle() {
  const title = titleFor(usePathname());
  return title ? <h1 className="truncate text-sm font-medium">{title}</h1> : null;
}
