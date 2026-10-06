"use client";

import { useEffect } from "react";

/**
 * Sets the tab title from a component that renders after the page's own
 * metadata has streamed. The not-found boundaries need it: they appear inside
 * a page that already announced its title (Dashboard, Contact, …) before the
 * lookup failed, and nothing else replaces that title.
 */
export function DocumentTitle({ title }: { title: string }) {
  useEffect(() => {
    document.title = title;
  }, [title]);
  return null;
}
