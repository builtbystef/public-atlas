import Link from "next/link";

import { Button } from "@/components/ui/button";
import { toSearchString } from "@/lib/lists";
import { paths } from "@/lib/routes";

import { GraphIcon } from "./layout/nav-icons";

/** A button into the graph view, rooted at a place and, when given, with a node's panel open. */
export function GraphLink({ search }: { search: { place_id: string; node?: string } }) {
  return (
    <Button
      variant="outline"
      nativeButton={false}
      render={<Link href={paths.graphWhere(toSearchString(search))} />}
    >
      <GraphIcon className="size-4" /> Graph
    </Button>
  );
}
