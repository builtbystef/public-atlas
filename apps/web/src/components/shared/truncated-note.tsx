/** For lists that show one large page of everything: says when there was more. */
export function TruncatedNote({
  shown,
  total,
  noun,
}: {
  shown: number;
  total: number;
  noun: string;
}) {
  if (total <= shown) return null;
  return (
    <p className="text-xs text-muted-foreground">
      Showing {shown} of {total} {noun}.
    </p>
  );
}
