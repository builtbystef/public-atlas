import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * One pass through the console as a person sees it: the list pages render from the API, a
 * page past the end keeps a way back, and a run's page opens its release dialog. Each page
 * is asserted by what the person reads, never by the markup.
 */

// Set by playwright.config.ts: the smoke's own API, never the development one.
const API_URL = process.env["API_URL"]!;

test("the runs page lists the runs", async ({ page }) => {
  await page.goto("/runs");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Runs");
  await expect(page.getByRole("button", { name: "New run" })).toBeVisible();
  // Rows when there are runs; the invitation when there are none. Never an error. The
  // invitation is itself a row, so both can match: `first()` takes either.
  await expect(
    page.getByRole("table").getByRole("row").nth(1).or(page.getByText("No runs yet.")).first(),
  ).toBeVisible();
});

test("the review queue renders", async ({ page }) => {
  await page.goto("/review");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Review queue");
  // Rows when items are open; the empty queue says so, in a row of its own.
  await expect(
    page
      .getByRole("table")
      .getByRole("row")
      .nth(1)
      .or(page.getByText("The queue is empty."))
      .first(),
  ).toBeVisible();
});

test("page 2 of the institutions keeps a way back", async ({ page }) => {
  await page.goto("/institutions?page=2");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Institutions");
  // A seeded database has fewer than fifty institutions, so page 2 is past the end and says
  // so; a full one has rows. Either way the pager is there and leads back.
  await expect(page.getByText(/^Page 2 of \d+$/)).toBeVisible();
  const previous = page.getByRole("button", { name: "Previous" });
  await expect(previous).toBeEnabled();
  await previous.click();
  await expect(page).toHaveURL(/\/institutions$/);
  await expect(page.getByText(/^Page 2 of \d+$/)).toBeHidden();
});

test.describe("a step run", () => {
  let api: APIRequestContext;
  let runId: string;

  test.beforeAll(async ({ playwright }) => {
    api = await playwright.request.newContext({ baseURL: API_URL });
    // The seeded country's government is owed one piece of work (a homepage search, or a
    // sources search once it has a homepage); in step mode it is held until released.
    const places = await api.get("/places", {
      params: { country_code: "CA", administrative_level: "country", limit: 1 },
    });
    expect(places.ok(), await places.text()).toBe(true);
    const [canada] = (await places.json()).items as { government_institution_id: string }[];
    const created = await api.post("/runs", {
      data: {
        name: `Console smoke ${new Date().toISOString()}`,
        country_code: "CA",
        mode: "step",
        filter: {
          administrative_levels: [],
          institution_types: [],
          assignment_types: [],
          subject_ids: [canada!.government_institution_id],
        },
        record_video: false,
      },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const run = (await created.json()) as {
      id: string;
      progress: { by_status: Record<string, number> };
    };
    expect(run.progress.by_status).toEqual({ held: 1 });
    runId = run.id;
  });

  test.afterAll(async () => {
    // Nothing is left waiting for a worker.
    const stopped = await api.post(`/runs/${runId}/stop`);
    expect(stopped.ok(), await stopped.text()).toBe(true);
    await api.dispose();
  });

  test("its page opens the release dialog for its held assignment", async ({ page }) => {
    await page.goto(`/runs/${runId}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Run");
    await page.getByRole("button", { name: "Release held (1)" }).click();
    const dialog = page.getByRole("dialog", { name: "Release held assignments" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("One assignment is held.");
    await expect(dialog.getByLabel("How many")).toHaveValue("1");
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toBeHidden();
  });
});
