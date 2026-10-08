import { cookies } from "next/headers";
import { Suspense, type ReactNode } from "react";

import { AppSidebar } from "@/components/shared/layout/app-sidebar";
import { EvalDatabaseBanner } from "@/components/shared/layout/database-switch";
import { PageTitle } from "@/components/shared/layout/page-title";
import { TimeZoneSync } from "@/components/shared/time-zone-sync";
import { Separator } from "@/components/ui/separator";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { getDatabase } from "@/lib/api/server";
import { SIDEBAR_COOKIE_NAME, sidebarOpenFromCookie } from "@/lib/sidebar-cookie";
import { getTimeZone } from "@/lib/time-zone/server";

/**
 * The shell around every console page. Whether the sidebar starts open is a
 * cookie, so the shell streams in behind one <Suspense> with a silhouette of
 * itself as the fallback; the page title, the nav highlight, the eval
 * database banner and the time zone each stream behind their own.
 */
export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<ShellFallback />}>
      <Shell>{children}</Shell>
    </Suspense>
  );
}

async function Shell({ children }: { children: ReactNode }) {
  const sidebarOpen = sidebarOpenFromCookie((await cookies()).get(SIDEBAR_COOKIE_NAME)?.value);
  return (
    <SidebarProvider defaultOpen={sidebarOpen}>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/85 px-4 backdrop-blur-sm md:px-6">
          {/* On a phone the sidebar is a sheet, so it needs a way in from the page. */}
          <SidebarTrigger className="-ml-1 text-muted-foreground md:hidden" />
          <Separator
            orientation="vertical"
            className="mr-1 data-[orientation=vertical]:h-4 md:hidden"
          />
          <Suspense>
            <PageTitle />
          </Suspense>
        </header>
        <Suspense>
          <CurrentDatabaseBanner />
        </Suspense>
        <main className="mx-auto w-full max-w-7xl flex-1 p-6 md:px-8 md:py-8">{children}</main>
      </SidebarInset>
      <Suspense>
        <CurrentTimeZone />
      </Suspense>
    </SidebarProvider>
  );
}

/** The shell's shape with nothing in it, for the instant before the cookie is read. */
function ShellFallback() {
  return (
    <div className="flex min-h-svh w-full">
      <div className="hidden w-64 shrink-0 bg-sidebar md:block">
        <div className="h-14 border-b border-sidebar-border" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col bg-background">
        <div className="h-14 shrink-0 border-b" />
      </div>
    </div>
  );
}

async function CurrentDatabaseBanner() {
  return (await getDatabase()) === "eval" ? <EvalDatabaseBanner /> : null;
}

async function CurrentTimeZone() {
  return <TimeZoneSync serverTimeZone={await getTimeZone()} />;
}
