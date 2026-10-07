/** The title the shell header shows for a pathname; null outside the console's pages. */
export function titleFor(pathname: string): string | null {
  const [section, id] = pathname.split("/").filter(Boolean);
  switch (section) {
    case undefined:
      return "Overview";
    case "runs":
      if (!id) return "Runs";
      return id === "new" ? "New run" : "Run";
    case "assignments":
      return id ? "Assignment" : "Assignments";
    case "institutions":
      return id ? "Institution" : "Institutions";
    case "review":
      return id ? "Review item" : "Review queue";
    case "countries":
      return id ? "Country" : "Countries";
    case "evals":
      return id ? "Eval run" : "Evals";
    default:
      return null;
  }
}
