import { JsonView } from "@/components/shared/json-view";
import { humanize } from "@/lib/labels";

/** The facts a question carries besides its reasons, as rows; anything nested as JSON. */
export function QuestionFacts({ question }: { question: Record<string, unknown> }) {
  const rows = Object.entries(question).filter(([key]) => key !== "reasons");
  if (rows.length === 0) return null;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      {rows.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-muted-foreground">{humanize(key)}</dt>
          <dd className="min-w-0 break-words">
            {value === null || value === undefined ? (
              <span className="text-muted-foreground">–</span>
            ) : typeof value === "object" ? (
              <JsonView value={value} className="max-h-40" />
            ) : (
              scalarText(value)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function reasonsOf(question: Record<string, unknown>): string[] {
  const reasons = question["reasons"];
  return Array.isArray(reasons) ? reasons.map(String) : [];
}

/** A JSON scalar as text. */
export function scalarText(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}
