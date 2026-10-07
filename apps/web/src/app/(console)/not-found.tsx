import Link from "next/link";

import { DocumentTitle } from "@/components/shared/layout/document-title";
import { Logo } from "@/components/shared/logo";
import { Button } from "@/components/ui/button";
import { paths } from "@/lib/routes";

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-lg flex-col items-start gap-3">
      <DocumentTitle title="Not found · Public Atlas" />
      <Logo className="size-10 text-muted-foreground" />
      <h1 className="text-2xl font-semibold tracking-tight">Not found</h1>
      <p className="text-muted-foreground">
        This record does not exist in the database the console is reading.
      </p>
      <Button variant="outline" nativeButton={false} render={<Link href={paths.home} />}>
        Back to the overview
      </Button>
    </div>
  );
}
