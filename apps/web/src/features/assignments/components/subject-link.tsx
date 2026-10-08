import type { SubjectOutput } from "@public-atlas/api-client";
import Link from "next/link";

import { entityKindLabels } from "@/lib/labels";
import { paths } from "@/lib/routes";

/** The subject's name, linking to its institution or place page. */
export function SubjectLink({
  subject,
  subjectId,
  showKind = false,
}: {
  subject: SubjectOutput | null | undefined;
  subjectId: string;
  showKind?: boolean;
}) {
  if (!subject) {
    return <span className="font-mono text-xs text-muted-foreground">{subjectId}</span>;
  }
  const href =
    subject.kind === "institution" ? paths.institution(subject.id) : paths.place(subject.id);
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5">
      <Link href={href} className="font-medium hover:underline">
        {subject.name}
      </Link>
      {showKind && (
        <span className="text-xs text-muted-foreground">{entityKindLabels[subject.kind]}</span>
      )}
    </span>
  );
}
