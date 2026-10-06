import type { ReactNode } from "react";

/** One label and value row in a record's details card; the value shows a dash when empty. */
export function Detail({
  icon,
  label,
  children,
}: {
  icon?: ReactNode;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="grid grid-cols-[7rem_1fr] items-start gap-2">
      <dt className="flex items-center gap-1.5 text-muted-foreground [&_svg]:size-3.5">
        {icon}
        {label}
      </dt>
      <dd className="min-w-0 break-words">
        {children || <span className="text-muted-foreground">–</span>}
      </dd>
    </div>
  );
}
