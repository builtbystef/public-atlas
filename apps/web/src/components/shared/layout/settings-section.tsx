import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** The blocks of a settings page, with a rule between them. */
export function SettingsSections({ children }: { children: ReactNode }) {
  return <div className="flex flex-col divide-y">{children}</div>;
}

/**
 * One block of a settings page: heading in the left column, the form or control
 * in the right. `wide` stacks the heading above content that needs the full
 * width, such as a table.
 */
export function SettingsSection({
  id,
  title,
  actions,
  wide = false,
  children,
}: {
  /** For a link to the section; it scrolls in below the sticky headers. */
  id?: string;
  title: ReactNode;
  actions?: ReactNode;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className={cn(
        "grid scroll-mt-20 gap-4 py-8 first:pt-0 last:pb-0",
        !wide && "md:grid-cols-[minmax(0,16rem)_minmax(0,1fr)] md:gap-x-12",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h2 className="text-base font-medium">{title}</h2>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      <div className={cn("flex min-w-0 flex-col gap-6", !wide && "md:max-w-xl")}>{children}</div>
    </section>
  );
}
