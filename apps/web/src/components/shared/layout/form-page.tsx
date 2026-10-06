import type { ReactNode } from "react";

/** The column a create or edit form sits in: narrower than the main area, and centred in it. */
export function FormPage({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full max-w-2xl">{children}</div>;
}
