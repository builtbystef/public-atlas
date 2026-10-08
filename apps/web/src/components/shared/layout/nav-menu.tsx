"use client";

import { useQuery } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { assignmentListQuery } from "@/features/assignments/queries";
import { reviewListQuery } from "@/features/review/queries";
import { browserApi } from "@/lib/api/client";
import { paths } from "@/lib/routes";
import { cn } from "@/lib/utils";

import {
  AssignmentsIcon,
  CountriesIcon,
  EvalsIcon,
  GraphIcon,
  InstitutionsIcon,
  PlacesIcon,
  ReviewIcon,
  RunsIcon,
  SavedListsIcon,
  SettingsIcon,
  type NavIcon,
} from "./nav-icons";

/** What a badge counts: assignments running, or review items open. */
type Count = "running" | "open";

type Counts = { [K in Count]?: number | undefined };

interface NavItem {
  href: Route;
  label: string;
  icon: NavIcon;
  count?: Count;
}

/**
 * The console's pages, grouped by what they are for: the graph and the lists
 * of it kept in this browser, the work in progress that builds it, and how
 * well it builds it. The configuration the rules are built from and the
 * console's own settings sit apart in the sidebar footer.
 */
const sections: { label?: string; items: NavItem[] }[] = [
  {
    label: "Data",
    items: [
      { href: paths.lists, label: "Saved lists", icon: SavedListsIcon },
      { href: paths.institutions, label: "Institutions", icon: InstitutionsIcon },
      { href: paths.places, label: "Places", icon: PlacesIcon },
      { href: paths.graph, label: "Graph", icon: GraphIcon },
    ],
  },
  {
    label: "Pipeline",
    items: [
      { href: paths.runs, label: "Runs", icon: RunsIcon },
      { href: paths.assignments, label: "Assignments", icon: AssignmentsIcon, count: "running" },
      { href: paths.review, label: "Review queue", icon: ReviewIcon, count: "open" },
    ],
  },
  { label: "Quality", items: [{ href: paths.evals, label: "Evals", icon: EvalsIcon }] },
];

const footer: NavItem[] = [
  { href: paths.countries, label: "Country config", icon: CountriesIcon },
  { href: paths.settings, label: "Settings", icon: SettingsIcon },
];

type Menu = "main" | "footer";

const REFRESH_MS = 15_000;
const ONE = { limit: 1, offset: 0 };

/** The badge counts, polled like the pages that list them; mutations there refresh them too. */
function useCounts(): Counts {
  const running = useQuery({
    ...assignmentListQuery(browserApi, { ...ONE, status: "running" }),
    refetchInterval: REFRESH_MS,
    select: (page) => page.total,
  });
  const open = useQuery({
    ...reviewListQuery(browserApi, { ...ONE, status: "open" }),
    refetchInterval: REFRESH_MS,
    select: (page) => page.total,
  });
  return { running: running.data, open: open.data };
}

/** The nav with the current section highlighted and its counts; needs the URL, so it streams. */
export function NavMenu({ menu = "main" }: { menu?: Menu }) {
  return <NavLinks menu={menu} pathname={usePathname()} counts={useCounts()} />;
}

/** The same links without a highlight or counts: what the static shell shows. */
export function NavMenuFallback({ menu = "main" }: { menu?: Menu }) {
  return <NavLinks menu={menu} pathname={null} counts={{}} />;
}

function NavLinks({
  menu,
  pathname,
  counts,
}: {
  menu: Menu;
  pathname: string | null;
  counts: Counts;
}) {
  if (menu === "footer") {
    return <NavItems items={footer} pathname={pathname} counts={counts} />;
  }
  return sections.map(({ label, items }) => (
    <SidebarGroup key={label ?? "home"} className="py-1 first:pt-2">
      {label && <SidebarGroupLabel className="h-7 text-sidebar-muted">{label}</SidebarGroupLabel>}
      <SidebarGroupContent>
        <NavItems items={items} pathname={pathname} counts={counts} />
      </SidebarGroupContent>
    </SidebarGroup>
  ));
}

function NavItems({
  items,
  pathname,
  counts,
}: {
  items: NavItem[];
  pathname: string | null;
  counts: Counts;
}) {
  const { setOpenMobile } = useSidebar();
  return (
    <SidebarMenu className="gap-0.5">
      {items.map(({ href, label, icon: Icon, count }) => {
        const active = pathname !== null && pathname.startsWith(href);
        const n = count === undefined ? 0 : (counts[count] ?? 0);
        // Open review items wait on a person, so they are amber; running assignments are news.
        const urgent = count === "open";
        return (
          <SidebarMenuItem key={href}>
            <SidebarMenuButton
              isActive={active}
              tooltip={n > 0 ? `${label} · ${n} ${count}` : label}
              className={cn(
                // The icons are drawn finer than lucide's, so they run a size up; the rail's padding makes room.
                "relative h-9 gap-2.5 text-sidebar-foreground/85 group-data-[collapsible=icon]:p-1.5! [&_svg]:size-5 [&_svg]:text-sidebar-muted",
                "hover:bg-sidebar-accent/60 hover:[&_svg]:text-sidebar-foreground",
                "data-active:bg-sidebar-primary/14 data-active:hover:bg-sidebar-primary/14 data-active:[&_svg]:text-sidebar-primary data-active:[--nav-icon-tint:0.4]",
                "before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-r-full before:bg-sidebar-primary before:opacity-0 before:transition-opacity data-active:before:opacity-100",
                n > 0 && "pr-10",
              )}
              render={<Link href={href} onClick={() => setOpenMobile(false)} />}
            >
              <Icon />
              <span>{label}</span>
            </SidebarMenuButton>
            {n > 0 && (
              <SidebarMenuBadge
                className={cn(
                  "right-1.5 rounded-full px-1.5 text-[11px] peer-data-[size=default]/menu-button:top-2",
                  urgent
                    ? "bg-sidebar-warning/15 text-sidebar-warning peer-hover/menu-button:text-sidebar-warning peer-data-active/menu-button:text-sidebar-warning"
                    : "bg-sidebar-accent text-sidebar-foreground/85",
                )}
              >
                {n > 999 ? "999+" : n}
              </SidebarMenuBadge>
            )}
            {n > 0 && urgent && (
              <span
                aria-hidden="true"
                className="pointer-events-none absolute top-1.5 right-1.5 hidden size-1.5 rounded-full bg-sidebar-warning group-data-[collapsible=icon]:block"
              />
            )}
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  );
}
