"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

// Generic, as `<Link>` is: a bare `Route` takes no path with an id in it.
export interface SidebarPage<T extends string = string> {
  href: Route<T>;
  label: string;
  count?: number;
}

/**
 * A record's pages, listed beside the one being shown. The list stays in view
 * as the page scrolls; on a narrow screen it sits above the page as a row
 * that scrolls sideways.
 */
export function SectionSidebar<T extends string>({
  pages,
  children,
}: {
  pages: readonly SidebarPage<T>[];
  children: ReactNode;
}) {
  const pathname = usePathname();
  return (
    <div className="grid gap-6 lg:grid-cols-[11rem_minmax(0,1fr)] lg:gap-12">
      <nav aria-label="Pages" className="lg:sticky lg:top-22 lg:self-start">
        <ul className="-mx-1 flex gap-1 overflow-x-auto px-1 [scrollbar-width:none] lg:mx-0 lg:flex-col lg:overflow-visible lg:px-0">
          {pages.map((page) => {
            const current = page.href === pathname;
            return (
              <li key={page.href} className="shrink-0">
                <Link
                  href={page.href}
                  aria-current={current ? "page" : undefined}
                  className={cn(
                    "flex h-8 items-center gap-2 rounded-md px-2.5 text-sm whitespace-nowrap transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                    current
                      ? "bg-muted font-medium text-foreground"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                  )}
                >
                  {page.label}
                  {page.count !== undefined && (
                    <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                      {page.count}
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
