import { paths, type Paths } from "./routes";

/** The console's list pages: the paths that are strings, not functions of an id. */
type ListPath = Extract<Paths[keyof Paths], string>;

/** One step of the shell header's breadcrumb; the last step has no `href`. */
export interface Crumb {
  label: string;
  href?: ListPath;
}

/**
 * The section each top-level path belongs to, with the title of a record page
 * under it. The header shows the section as a link back to its list and the
 * record title after it.
 */
const sections: Record<string, { label: string; href: ListPath; record: string }> = {
  lists: { label: "Saved lists", href: paths.lists, record: "Saved list" },
  runs: { label: "Runs", href: paths.runs, record: "Run" },
  assignments: { label: "Assignments", href: paths.assignments, record: "Assignment" },
  institutions: { label: "Institutions", href: paths.institutions, record: "Institution" },
  places: { label: "Places", href: paths.places, record: "Place" },
  review: { label: "Review queue", href: paths.review, record: "Review item" },
  countries: { label: "Country config", href: paths.countries, record: "Country" },
  evals: { label: "Evals", href: paths.evals, record: "Eval run" },
  settings: { label: "Settings", href: paths.settings, record: "Settings" },
};

/** The breadcrumb the shell header shows for a pathname; null outside the console's pages. */
export function crumbsFor(pathname: string): Crumb[] | null {
  const [section, id] = pathname.split("/").filter(Boolean);
  if (section === undefined) return null;
  const known = sections[section];
  if (!known) return null;
  if (!id) return [{ label: known.label }];
  const record = section === "runs" && id === "new" ? "New run" : known.record;
  return [{ label: known.label, href: known.href }, { label: record }];
}

/** The title the shell header shows for a pathname: the breadcrumb's last step. */
export function titleFor(pathname: string): string | null {
  const crumbs = crumbsFor(pathname);
  return crumbs?.at(-1)?.label ?? null;
}
