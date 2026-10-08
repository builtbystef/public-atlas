/**
 * The console reads one of two databases: the live graph, or the separate
 * database the eval harness fills (spec section 10). The choice is a cookie
 * that both API clients turn into the API's `X-Database` header, so every
 * page works against either without a second deployment.
 */

export const DATABASE_COOKIE = "db";
export const DATABASE_HEADER = "X-Database";

export const databases = ["main", "eval"] as const;

export type Database = (typeof databases)[number];

export const databaseLabels: Record<Database, string> = {
  main: "Live database",
  eval: "Eval database",
};

/** What each database holds, for the settings page. */
export const databaseDescriptions: Record<Database, string> = {
  main: "The real graph: the places, institutions, sources and runs the console is for. Eval scores are kept here too.",
  eval: "The graph the last eval run built, reset by each run. Read it to see why an eval scored as it did.",
};

export function isDatabase(value: string): value is Database {
  return (databases as readonly string[]).includes(value);
}

/** The database a cookie value names; the live one when it names nothing. */
export function parseDatabase(value: string | undefined | null): Database {
  return value !== undefined && value !== null && isDatabase(value) ? value : "main";
}

/** The database chosen in a `document.cookie` string. */
export function readDatabaseCookie(cookie: string): Database {
  const pair = cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${DATABASE_COOKIE}=`));
  return parseDatabase(pair?.slice(DATABASE_COOKIE.length + 1));
}

/** The `Set-Cookie` string that chooses `database` for a year. */
export function databaseCookie(database: Database): string {
  return `${DATABASE_COOKIE}=${database}; path=/; max-age=31536000; samesite=lax`;
}
