"use client";

import { PanelLeftCloseIcon, PanelLeftOpenIcon } from "lucide-react";
import { useSyncExternalStore } from "react";

import { LogoTile } from "@/components/shared/logo";
import { useSidebar } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * Collapses and expands the sidebar from inside its header. Collapsed, the
 * button is the rail's logo and turns into the expand icon under the pointer
 * or keyboard focus, so the narrow rail needs no second button at its top.
 */
export function SidebarToggle() {
  const { open, openMobile, isMobile, toggleSidebar } = useSidebar();
  const expanded = isMobile ? openMobile : open;
  const label = isMobile ? "Close sidebar" : expanded ? "Collapse sidebar" : "Expand sidebar";

  return (
    <Tooltip>
      <TooltipTrigger
        onClick={toggleSidebar}
        aria-label={label}
        className="group/toggle flex size-8 shrink-0 items-center justify-center rounded-md text-sidebar-muted ring-sidebar-ring outline-hidden transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2"
      >
        {expanded ? (
          <PanelLeftCloseIcon className="size-4" />
        ) : (
          <>
            <LogoTile className="group-hover/toggle:hidden group-focus-visible/toggle:hidden" />
            <PanelLeftOpenIcon className="hidden size-4 group-hover/toggle:block group-focus-visible/toggle:block" />
          </>
        )}
      </TooltipTrigger>
      <TooltipContent side="right" hidden={isMobile}>
        {label}
        <ShortcutKeys />
      </TooltipContent>
    </Tooltip>
  );
}

const subscribeNever = () => () => {};

/** The sidebar's shortcut, ⌘B or Ctrl B; the server cannot know the platform, so it says Ctrl. */
function ShortcutKeys() {
  const modifier = useSyncExternalStore(
    subscribeNever,
    () => (/Mac|iPhone|iPad/.test(navigator.userAgent) ? "⌘" : "Ctrl"),
    () => "Ctrl",
  );
  return (
    <kbd data-slot="kbd" className="bg-background/15 px-1 py-px font-sans text-[11px]">
      {modifier} B
    </kbd>
  );
}
