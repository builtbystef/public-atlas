import Link from "next/link";
import { Suspense } from "react";

import { LogoTile } from "@/components/shared/logo";
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader } from "@/components/ui/sidebar";
import { paths } from "@/lib/routes";

import { NavMenu, NavMenuFallback } from "./nav-menu";
import { SidebarToggle } from "./sidebar-toggle";

/**
 * The sidebar is a Server Component: the nav highlight depends on the
 * request, so each menu streams in behind its own <Suspense> and the rest of
 * the shell is prerendered. Its header is as tall as the page header,
 * so the two borders meet in one line.
 */
export function AppSidebar() {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="h-14 flex-row items-center gap-1 border-b border-sidebar-border px-2 py-0">
        <Link
          href={paths.lists}
          className="flex h-9 min-w-0 flex-1 items-center gap-2.5 rounded-md px-0.5 text-sidebar-accent-foreground ring-sidebar-ring outline-hidden focus-visible:ring-2 group-data-[collapsible=icon]:hidden"
        >
          <LogoTile />
          <span className="truncate text-base font-semibold tracking-tight">Public Atlas</span>
        </Link>
        <SidebarToggle />
      </SidebarHeader>
      <SidebarContent>
        <Suspense fallback={<NavMenuFallback />}>
          <NavMenu />
        </Suspense>
      </SidebarContent>
      <SidebarFooter className="border-t border-sidebar-border">
        <Suspense fallback={<NavMenuFallback menu="footer" />}>
          <NavMenu menu="footer" />
        </Suspense>
      </SidebarFooter>
    </Sidebar>
  );
}
