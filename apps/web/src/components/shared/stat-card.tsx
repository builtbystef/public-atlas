import { ArrowUpRightIcon } from "lucide-react";
import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** One number with its name, linking to the list it counts. */
export function StatCard({
  label,
  value,
  detail,
  icon,
  tone = "primary",
  href,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  icon?: ReactNode;
  /** Which of the palette's colours tints the icon. */
  tone?: "primary" | "warning" | "plum" | "success";
  href: ComponentProps<typeof Link>["href"];
}) {
  const tones = {
    primary: "bg-primary/10 text-primary",
    warning: "bg-warning/12 text-warning",
    plum: "bg-plum/10 text-plum",
    success: "bg-success/10 text-success",
  };
  return (
    <Link
      href={href}
      className="group/stat block rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <Card className="h-full transition-[box-shadow,transform] group-hover/stat:shadow-md group-hover/stat:ring-primary/30">
        <CardHeader className="grid-cols-[1fr_auto]">
          <div className="flex flex-col gap-1">
            <CardDescription>{label}</CardDescription>
            <CardTitle className="text-3xl font-semibold tracking-tight tabular-nums">
              {value}
            </CardTitle>
          </div>
          {icon && (
            <div
              className={cn(
                "row-span-2 flex size-9 items-center justify-center rounded-lg [&_svg]:size-4.5",
                tones[tone],
              )}
            >
              {icon}
            </div>
          )}
        </CardHeader>
        <CardContent className="flex items-end justify-between gap-2 text-sm text-muted-foreground">
          <span className="min-w-0 truncate">{detail}</span>
          <ArrowUpRightIcon className="size-4 shrink-0 opacity-0 transition-opacity group-hover/stat:opacity-100" />
        </CardContent>
      </Card>
    </Link>
  );
}
