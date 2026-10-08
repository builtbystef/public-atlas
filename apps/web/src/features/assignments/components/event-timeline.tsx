"use client";

import type { EventOutput } from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { ChevronRightIcon } from "lucide-react";

import { CollapsibleText } from "@/components/shared/collapsible-text";
import { EmptyState } from "@/components/shared/empty-state";
import { JsonView } from "@/components/shared/json-view";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { browserApi } from "@/lib/api/client";
import { formatBytes } from "@/lib/formatting/bytes";
import { formatDateTime, formatDuration } from "@/lib/formatting/dates";
import { eventKindLabels } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { assignmentEventsQuery } from "../queries";

const REFRESH_MS = 5_000;

/**
 * Everything the agent saw, said and did, session by session: the prompt,
 * the model's words, each tool call with its result, and the recorded video
 * when the run asked for one. A session can run to hundreds of events, so
 * each is folded until opened; the latest starts open.
 */
export function EventTimeline({
  assignmentId,
  live,
  timeZone,
}: {
  assignmentId: string;
  /** While the assignment runs, the list is re-read as sessions end. */
  live: boolean;
  timeZone: string;
}) {
  const { data: events } = useSuspenseQuery({
    ...assignmentEventsQuery(browserApi, assignmentId),
    refetchInterval: live ? REFRESH_MS : false,
  });
  if (events.length === 0) {
    return (
      <EmptyState boxed>
        {live
          ? "Events are written when a session ends; none has yet."
          : "No events. They were purged, or the assignment never ran."}
      </EmptyState>
    );
  }
  const sessions = new Map<number, EventOutput[]>();
  for (const event of events) {
    const list = sessions.get(event.session) ?? [];
    list.push(event);
    sessions.set(event.session, list);
  }
  const entries = [...sessions.entries()];
  return (
    <div className="flex flex-col gap-3">
      {entries.map(([session, list], index) => (
        <SessionCard
          key={session}
          session={session}
          events={list}
          timeZone={timeZone}
          defaultOpen={index === entries.length - 1}
        />
      ))}
    </div>
  );
}

function SessionCard({
  session,
  events,
  timeZone,
  defaultOpen,
}: {
  session: number;
  events: EventOutput[];
  timeZone: string;
  defaultOpen: boolean;
}) {
  const first = events[0]?.at;
  const last = events.at(-1)?.at;
  const duration = formatDuration(first, last);
  return (
    <Card className="gap-0 py-0">
      <Collapsible defaultOpen={defaultOpen}>
        <CollapsibleTrigger className="group/session flex w-full items-center gap-3 px-4 py-3 text-left transition-colors outline-none hover:bg-muted/40 focus-visible:bg-muted/40">
          <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground transition-transform group-data-panel-open/session:rotate-90" />
          <span className="flex min-w-0 flex-1 flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-3">
            <span className="font-medium">Session {session}</span>
            <span className="text-xs text-muted-foreground">
              {events.length} {events.length === 1 ? "event" : "events"}
              {" · "}
              {formatDateTime(first, timeZone)}
              {duration && ` · ${duration}`}
            </span>
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent className="border-t">
          <ol className="flex flex-col divide-y px-4">
            {events.map((event) => (
              <li key={event.id} className="flex flex-col gap-2 py-3">
                <EventRow event={event} timeZone={timeZone} />
              </li>
            ))}
          </ol>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}

const KIND_VARIANT = {
  prompt: "outline",
  text: "info",
  tool_call: "secondary",
  tool_result: "secondary",
  video: "plum",
} as const;

function EventRow({ event, timeZone }: { event: EventOutput; timeZone: string }) {
  const content = event.content;
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Badge variant={KIND_VARIANT[event.kind]}>{eventKindLabels[event.kind]}</Badge>
        {event.tool && <code className="font-mono text-foreground">{event.tool}</code>}
        {event.kind === "prompt" && typeof content["role"] === "string" && (
          <span>{content["role"]}</span>
        )}
        {"retry" in content && <Badge variant="destructive">Retry</Badge>}
        <span className="ml-auto tabular-nums">{formatDateTime(event.at, timeZone)}</span>
      </div>
      <EventContent event={event} />
    </>
  );
}

function EventContent({ event }: { event: EventOutput }) {
  const content = event.content;
  switch (event.kind) {
    case "prompt": {
      const text = content["text"];
      return typeof text === "string" ? (
        <CollapsibleText text={text} className="text-muted-foreground" />
      ) : (
        <JsonView value={text ?? content} />
      );
    }
    case "text": {
      const text = content["text"];
      return typeof text === "string" ? (
        <p className="text-sm break-words whitespace-pre-wrap">{text}</p>
      ) : (
        <JsonView value={content} />
      );
    }
    case "tool_call":
      return <JsonView value={content["args"] ?? content} />;
    case "tool_result": {
      const value = "retry" in content ? content["retry"] : (content["content"] ?? content);
      return typeof value === "string" ? (
        <CollapsibleText text={value} className={cn("retry" in content && "text-destructive")} />
      ) : (
        <JsonView value={value} />
      );
    }
    case "video":
      return <VideoEvent event={event} />;
    default:
      return <JsonView value={content} />;
  }
}

function VideoEvent({ event }: { event: EventOutput }) {
  const size = event.content["size"];
  if (!event.video_url) {
    return (
      <p className="text-sm text-muted-foreground">
        The recording was purged; recordings are kept for a limited time after an assignment
        finishes.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <video
        controls
        preload="metadata"
        src={event.video_url}
        className="max-h-96 w-full rounded-md bg-black"
      >
        <track kind="captions" />
      </video>
      <p className="text-xs text-muted-foreground">
        {typeof size === "number" ? formatBytes(size) : null}{" "}
        <a href={event.video_url} className="hover:underline" download>
          Download
        </a>
      </p>
    </div>
  );
}
