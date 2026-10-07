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
import { Skeleton } from "@/components/ui/skeleton";
import { getDatabase } from "@/lib/api/server";
import { paths } from "@/lib/routes";

import { DatabaseSwitch } from "./database-switch";
import { NavMenu, NavMenuFallback } from "./nav-menu";

/**
 * The sidebar is a Server Component: the nav highlight and the database
 * switch depend on the request, and each streams in behind its own
 * <Suspense> so the rest of the shell is prerendered.
 */
export function AppSidebar() {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link href={paths.home} />}>
              <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Logo className="size-5" />
              </div>
              <div className="flex flex-col gap-0.5 leading-none">
                <span className="font-semibold">Public Atlas</span>
                <span className="text-xs text-muted-foreground">Console</span>
              </div>
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
      <SidebarFooter>
        <Suspense fallback={<Skeleton className="h-8 w-full rounded-lg" />}>
          <CurrentDatabaseSwitch />
        </Suspense>
      </SidebarFooter>
    </Sidebar>
  );
}

async function CurrentDatabaseSwitch() {
  return <DatabaseSwitch database={await getDatabase()} />;
}
