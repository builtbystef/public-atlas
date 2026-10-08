"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CircleAlertIcon,
  CircleCheckIcon,
  CirclePauseIcon,
  CirclePlayIcon,
  CircleXIcon,
  MergeIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";

import { describeEffects } from "../effects";
import { decisionPreviewQuery, type PreviewRequest } from "../queries";
import type { DecisionTone } from "./decision-frame";

const CHANGE_ICONS: Record<DecisionTone, ReactNode> = {
  approve: <CircleCheckIcon className="text-success" />,
  merge: <MergeIcon className="text-primary" />,
  reject: <CircleXIcon className="text-destructive" />,
};

const DEBOUNCE_MS = 300;

function Line({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <li className="flex items-start gap-2 [&>svg]:mt-0.5 [&>svg]:size-4 [&>svg]:shrink-0">
      {icon}
      <span className="min-w-0 break-words">{children}</span>
    </li>
  );
}

/**
 * "What this does": the decision's preview in plain sentences, from the
 * server making the decision and rolling it back. `request` is null until
 * the dialog has what the preview needs, such as the entity to merge into;
 * `extra` adds what the dialog itself knows, such as the type it sets;
 * `tone` marks the changes as the decision's own.
 */
export function DecisionEffects({
  request,
  tone,
  merged,
  extra = [],
}: {
  request: PreviewRequest | null;
  tone: DecisionTone;
  merged?: { id: string; into: string } | undefined;
  extra?: string[];
}) {
  // The request as text, so a dialog that renders a new but equal request (as typing a note
  // does) neither restarts the wait nor asks again.
  const wanted = JSON.stringify(request);
  const settled = useDebouncedValue(wanted, DEBOUNCE_MS);
  const asked = JSON.parse(settled) as PreviewRequest | null;
  const preview = useQuery({
    ...decisionPreviewQuery(browserApi, asked ?? { decision: "reject", id: "", body: {} }),
    enabled: asked !== null,
  });
  if (request === null) return null;

  let body: ReactNode;
  let footer: ReactNode = null;
  if (preview.isPending || settled !== wanted) {
    body = (
      <div className="flex flex-col gap-2 py-0.5" aria-label="Working out what this does">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    );
  } else if (preview.isError) {
    body = (
      <p className="flex items-start gap-2 text-destructive">
        <CircleAlertIcon className="mt-0.5 size-4 shrink-0" />
        <span className="min-w-0 break-words">
          This would be refused: {errorMessage(preview.error)}
        </span>
      </p>
    );
  } else {
    const effects = describeEffects(preview.data, merged);
    const changes = [...extra, ...effects.changes];
    const nothing = changes.length + effects.starts.length + effects.held.length === 0;
    body = nothing ? (
      <p className="text-muted-foreground">Closes the item; nothing else changes.</p>
    ) : (
      <ul className="flex flex-col gap-1.5">
        {changes.map((change) => (
          <Line key={change} icon={CHANGE_ICONS[tone]}>
            {change}
          </Line>
        ))}
        {effects.starts.map((work) => (
          <Line key={work} icon={<CirclePlayIcon className="text-primary" />}>
            Starts {work}
          </Line>
        ))}
        {effects.held.map((work) => (
          <Line key={work} icon={<CirclePauseIcon className="text-muted-foreground" />}>
            <span className="text-muted-foreground">{work}</span>
          </Line>
        ))}
      </ul>
    );
    if (effects.starts.length > 0 && preview.data.run) {
      footer = <>The work starts in the run “{preview.data.run.name}”.</>;
    }
  }
  return (
    <section className="overflow-hidden rounded-lg border bg-muted/30 text-sm">
      <h3 className="border-b px-3 py-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
        What this does
      </h3>
      <div className="px-3 py-2.5">{body}</div>
      {footer && <p className="border-t px-3 py-1.5 text-xs text-muted-foreground">{footer}</p>}
    </section>
  );
}
