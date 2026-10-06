import { Skeleton } from "@/components/ui/skeleton";

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3">
      <Skeleton className="h-8 w-64" />
      <div className="flex flex-col gap-2 rounded-lg border p-3">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    </div>
  );
}

export function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-8 w-72" />
      <div className="grid gap-6 md:grid-cols-2">
        <Skeleton className="h-48" />
        <Skeleton className="h-48" />
      </div>
    </div>
  );
}

export function FormSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-8">
      {Array.from({ length: 2 }, (_, i) => (
        <div key={i} className="flex flex-col gap-4">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-14 w-full" />
          <div className="grid gap-5 sm:grid-cols-2">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        </div>
      ))}
    </div>
  );
}
