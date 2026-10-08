import Link from "next/link";
import { Suspense } from "react";

import { Logo } from "@/components/shared/logo";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { paths } from "@/lib/routes";

import { NavMenu, NavMenuFallback } from "./nav-menu";

/**
 * The sidebar is a Server Component: the nav highlight depends on the
 * request, so each menu streams in behind its own <Suspense> and the rest of
 * the shell is prerendered.
 */
export function AppSidebar() {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="p-2 pt-3">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              className="gap-3 px-2.5 hover:bg-sidebar-accent/60"
              render={<Link href={paths.home} />}
            >
              <Logo className="size-7! shrink-0 text-white" />
              <span className="text-lg font-semibold tracking-tight">Public Atlas</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <Suspense fallback={<NavMenuFallback />}>
              <NavMenu />
            </Suspense>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="border-t border-sidebar-border">
        <Suspense fallback={<NavMenuFallback menu="footer" />}>
          <NavMenu menu="footer" />
        </Suspense>
      </SidebarFooter>
    </Sidebar>
  );
}
