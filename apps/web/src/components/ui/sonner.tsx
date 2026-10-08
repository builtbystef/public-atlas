"use client";

import { useTheme } from "next-themes";
import { Toaster as Sonner, type ToasterProps } from "sonner";
import {
  CircleCheckIcon,
  InfoIcon,
  TriangleAlertIcon,
  OctagonXIcon,
  Loader2Icon,
  XIcon,
} from "lucide-react";

/**
 * Sonner's toasts, unstyled and drawn with the theme's tokens: a card with
 * the type's icon on a tinted disc, the message beside it and a close button
 * that shows on hover. Sonner still stacks, animates and swipes them.
 */
const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme();

  return (
    <Sonner
      theme={theme as "light" | "dark" | "system"}
      className="toaster group"
      closeButton
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
        close: <XIcon className="size-3.5" />,
      }}
      toastOptions={{
        unstyled: true,
        classNames: {
          toast: [
            "group/toast flex w-(--width) items-start gap-3 rounded-xl border bg-popover p-3 pr-10 font-sans text-popover-foreground shadow-lg shadow-black/8 dark:shadow-black/40",
            "data-[type=error]:border-destructive/30",
            // Sonner hides the content of the toasts stacked behind the front one only
            // when it styles them itself.
            "data-[expanded=false]:data-[front=false]:*:opacity-0",
          ].join(" "),
          icon: [
            "flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground",
            "group-data-[type=success]/toast:bg-success/12 group-data-[type=success]/toast:text-success",
            "group-data-[type=error]/toast:bg-destructive/12 group-data-[type=error]/toast:text-destructive",
            "group-data-[type=warning]/toast:bg-warning/15 group-data-[type=warning]/toast:text-warning",
            "group-data-[type=info]/toast:bg-primary/10 group-data-[type=info]/toast:text-primary",
          ].join(" "),
          // Centred on the icon for a one-line message, from the top for a longer one.
          content: "flex min-h-7 min-w-0 flex-1 flex-col justify-center gap-0.5",
          title: "text-sm leading-5 font-medium",
          description: "text-sm leading-5 text-muted-foreground",
          actionButton:
            "inline-flex h-7 shrink-0 cursor-pointer items-center self-center rounded-md bg-primary px-2.5 text-xs font-medium text-primary-foreground transition-colors outline-none hover:bg-primary/85 focus-visible:ring-3 focus-visible:ring-ring/50",
          cancelButton:
            "inline-flex h-7 shrink-0 cursor-pointer items-center self-center rounded-md bg-muted px-2.5 text-xs font-medium transition-colors outline-none hover:bg-muted/70 focus-visible:ring-3 focus-visible:ring-ring/50",
          closeButton:
            "absolute top-2.5 right-2.5 flex size-6 cursor-pointer items-center justify-center rounded-md text-muted-foreground opacity-0 transition-[opacity,background-color,color] outline-none group-hover/toast:opacity-100 hover:bg-muted hover:text-foreground focus-visible:opacity-100 focus-visible:ring-3 focus-visible:ring-ring/50 [@media(hover:none)]:opacity-100",
        },
      }}
      {...props}
    />
  );
};

export { Toaster };
