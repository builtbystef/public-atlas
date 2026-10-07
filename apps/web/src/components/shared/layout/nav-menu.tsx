"use client";

import {
  BuildingIcon,
  FlaskConicalIcon,
  GlobeIcon,
  LayoutDashboardIcon,
  ListChecksIcon,
  PlayIcon,
  ShieldQuestionIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { paths } from "@/lib/routes";

/** The console's pages, in the order spec section 11 lists them. */
const items = [
  { href: paths.home, label: "Overview", icon: LayoutDashboardIcon },
  { href: paths.runs, label: "Runs", icon: PlayIcon },
  { href: paths.assignments, label: "Assignments", icon: ListChecksIcon },
  { href: paths.institutions, label: "Institutions", icon: BuildingIcon },
  { href: paths.review, label: "Review queue", icon: ShieldQuestionIcon },
  { href: paths.countries, label: "Countries", icon: GlobeIcon },
  { href: paths.evals, label: "Evals", icon: FlaskConicalIcon },
] as const;

/** The nav with the current section highlighted; needs the URL, so it streams. */
export function NavMenu() {
  return <NavLinks pathname={usePathname()} />;
}

/** The same links without a highlight: what the static shell shows. */
export function NavMenuFallback() {
  return <NavLinks pathname={null} />;
}

function NavLinks({ pathname }: { pathname: string | null }) {
  return (
    <SidebarMenu>
      {items.map(({ href, label, icon: Icon }) => {
        const active =
          pathname !== null &&
          (href === paths.home ? pathname === href : pathname.startsWith(href));
        return (
          <SidebarMenuItem key={href}>
            <SidebarMenuButton isActive={active} tooltip={label} render={<Link href={href} />}>
              <Icon />
              <span>{label}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  );
}
