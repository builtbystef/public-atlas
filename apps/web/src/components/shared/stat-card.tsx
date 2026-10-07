import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** One number with its name, linking to the list it counts. */
export function StatCard({
  label,
  value,
  detail,
  href,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  href: ComponentProps<typeof Link>["href"];
}) {
  return (
    <Link href={href} className="block rounded-xl transition-colors hover:bg-muted/40">
      <Card className="h-full">
        <CardHeader>
          <CardDescription>{label}</CardDescription>
          <CardTitle className="text-3xl font-semibold tabular-nums">{value}</CardTitle>
        </CardHeader>
        {detail && <CardContent className="text-sm text-muted-foreground">{detail}</CardContent>}
      </Card>
    </Link>
  );
}
