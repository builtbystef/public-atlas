import { cn } from "@/lib/utils";

/** A JSON document the API passes through as is (a tool's arguments, a review question). */
export function JsonView({ value, className }: { value: unknown; className?: string }) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <pre
      className={cn(
        "max-h-96 overflow-auto rounded-md bg-muted p-3 font-mono text-xs break-words whitespace-pre-wrap",
        className,
      )}
    >
      {text}
    </pre>
  );
}
