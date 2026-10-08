import { ExternalLink } from "@/components/shared/external-link";
import { JsonView } from "@/components/shared/json-view";
import { Badge } from "@/components/ui/badge";
import { humanize } from "@/lib/labels";

/**
 * The facts a question carries besides its reasons, as rows: a URL as a link,
 * a list of words as chips, anything else nested as JSON. `hidden` leaves out
 * facts shown elsewhere, such as the ids of entities set beside the item.
 */
export function QuestionFacts({
  question,
  hidden,
}: {
  question: Record<string, unknown>;
  hidden?: ReadonlySet<string>;
}) {
  const rows = Object.entries(question).filter(
    ([key, value]) => key !== "reasons" && !hidden?.has(key) && value !== null,
  );
  if (rows.length === 0) return null;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
      {rows.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-muted-foreground">{humanize(key)}</dt>
          <dd className="min-w-0 break-words">
            <FactValue value={value} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function FactValue({ value }: { value: unknown }) {
  if (value === undefined) return <span className="text-muted-foreground">–</span>;
  if (typeof value === "string" && /^https?:\/\//.test(value)) {
    return <ExternalLink href={value} />;
  }
  if (Array.isArray(value) && value.every((one) => typeof one === "string")) {
    return (
      <span className="flex flex-wrap gap-1">
        {value.map((one) => (
          <Badge key={one} variant="outline">
            {humanize(one)}
          </Badge>
        ))}
      </span>
    );
  }
  if (typeof value === "object") return <JsonView value={value} className="max-h-40" />;
  return scalarText(value);
}

export function reasonsOf(question: Record<string, unknown>): string[] {
  const reasons = question["reasons"];
  return Array.isArray(reasons) ? reasons.map(String) : [];
}

/** A JSON scalar as text. */
export function scalarText(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}
