"use client";

import {
  BuildingIcon,
  FlaskConicalIcon,
  GlobeIcon,
  LayoutDashboardIcon,
  ListChecksIcon,
  PlayIcon,
  SettingsIcon,
  ShieldQuestionIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { paths } from "@/lib/routes";

/**
 * The console's pages, in the order spec section 11 lists them, and the
 * settings page apart in the sidebar footer.
 */
const menus = {
  main: [
    { href: paths.home, label: "Overview", icon: LayoutDashboardIcon },
    { href: paths.runs, label: "Runs", icon: PlayIcon },
    { href: paths.assignments, label: "Assignments", icon: ListChecksIcon },
    { href: paths.institutions, label: "Institutions", icon: BuildingIcon },
    { href: paths.review, label: "Review queue", icon: ShieldQuestionIcon },
    { href: paths.countries, label: "Countries", icon: GlobeIcon },
    { href: paths.evals, label: "Evals", icon: FlaskConicalIcon },
  ],
  footer: [{ href: paths.settings, label: "Settings", icon: SettingsIcon }],
} as const;

type Menu = keyof typeof menus;

/** The nav with the current section highlighted; needs the URL, so it streams. */
export function NavMenu({ menu = "main" }: { menu?: Menu }) {
  return <NavLinks menu={menu} pathname={usePathname()} />;
}

/** The same links without a highlight: what the static shell shows. */
export function NavMenuFallback({ menu = "main" }: { menu?: Menu }) {
  return <NavLinks menu={menu} pathname={null} />;
}

function NavLinks({ menu, pathname }: { menu: Menu; pathname: string | null }) {
  return (
    <SidebarMenu className="gap-0.5">
      {menus[menu].map(({ href, label, icon: Icon }) => {
        const active =
          pathname !== null &&
          (href === paths.home ? pathname === href : pathname.startsWith(href));
        return (
          <SidebarMenuItem key={href}>
            <SidebarMenuButton
              isActive={active}
              tooltip={label}
              className="text-sidebar-foreground/85 [&_svg]:text-sidebar-muted hover:[&_svg]:text-sidebar-foreground data-active:[&_svg]:text-sidebar-primary"
              render={<Link href={href} />}
            >
              <Icon />
              <span>{label}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  );
}
