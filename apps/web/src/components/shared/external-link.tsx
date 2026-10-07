import { ExternalLinkIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/** A link out of the console (a homepage, a source, a snapshot) that opens in a new tab. */
export function ExternalLink({
  href,
  children,
  className,
}: {
  href: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "inline-flex max-w-full items-center gap-1 break-all hover:underline [&_svg]:size-3 [&_svg]:shrink-0 [&_svg]:text-muted-foreground",
        className,
      )}
    >
      <span className="min-w-0 truncate">{children ?? href}</span>
      <ExternalLinkIcon />
    </a>
  );
}
