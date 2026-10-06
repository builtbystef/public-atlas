import type { ReactNode } from "react";

/**
 * The row above a page's content. The page title itself lives in the shell
 * header (see <PageTitle>); this holds the actions and, on record pages, the
 * record's name and details.
 */
export function PageHeader({
  title,
  description,
  children,
}: {
  title?: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      {title !== undefined && (
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
      )}
      {children && <div className="ml-auto flex shrink-0 items-center gap-2">{children}</div>}
    </div>
  );
}
