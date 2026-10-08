/**
 * The cookie that remembers whether the sidebar is open. The sidebar writes it
 * when toggled; the console layout reads it so a reload keeps the choice. It
 * lives here, outside the client-only sidebar module, so the server can read
 * its name.
 */
export const SIDEBAR_COOKIE_NAME = "sidebar_state";
export const SIDEBAR_COOKIE_MAX_AGE = 60 * 60 * 24 * 7;

/** Whether a cookie value says the sidebar is open; open when there is none. */
export function sidebarOpenFromCookie(value: string | undefined): boolean {
  return value !== "false";
}
