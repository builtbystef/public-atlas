// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vite-plus/test";

import { createDataTableColumnHelper, DataTable } from "./data-table";

interface Row {
  id: string;
  name: string;
}

const helper = createDataTableColumnHelper<Row>();
const columns = [helper.accessor("name", { header: "Name" })];

const rows = (n: number, from = 1): Row[] =>
  Array.from({ length: n }, (_, i) => ({ id: `r${from + i}`, name: `Row ${from + i}` }));

function pager() {
  return {
    previous: screen.getByRole("button", { name: "Previous" }) as HTMLButtonElement,
    next: screen.getByRole("button", { name: "Next" }) as HTMLButtonElement,
  };
}

test("an emptied last page keeps a way back", () => {
  const onPageChange = vi.fn<(page: number) => void>();
  // Three rows were deleted from page 2 of a 53-row list, leaving 50 rows on one page.
  render(<DataTable columns={columns} data={[]} total={50} page={2} onPageChange={onPageChange} />);
  expect(screen.getByText("Nothing on this page.")).toBeDefined();
  expect(screen.getByText("0 of 50")).toBeDefined();
  expect(screen.getByText("Page 2 of 1")).toBeDefined();
  const { previous, next } = pager();
  expect(previous.disabled).toBe(false);
  expect(next.disabled).toBe(true);
  previous.click();
  expect(onPageChange).toHaveBeenCalledWith(1);
});

test("a list that fits on one page has no pager", () => {
  render(
    <DataTable
      columns={columns}
      data={rows(3)}
      total={3}
      page={1}
      onPageChange={vi.fn<(page: number) => void>()}
    />,
  );
  expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
  expect(screen.getAllByRole("row")).toHaveLength(4);
});

test("a middle page counts its rows and can go either way", () => {
  const onPageChange = vi.fn<(page: number) => void>();
  render(
    <DataTable
      columns={columns}
      data={rows(50, 51)}
      total={120}
      page={2}
      onPageChange={onPageChange}
    />,
  );
  expect(screen.getByText("51–100 of 120")).toBeDefined();
  expect(screen.getByText("Page 2 of 3")).toBeDefined();
  const { previous, next } = pager();
  expect(previous.disabled).toBe(false);
  expect(next.disabled).toBe(false);
  next.click();
  expect(onPageChange).toHaveBeenLastCalledWith(3);
});

test("an empty list shows the owner's message, not the page's", () => {
  render(
    <DataTable
      columns={columns}
      data={[]}
      total={0}
      page={1}
      onPageChange={vi.fn<(page: number) => void>()}
      emptyMessage="No runs yet."
    />,
  );
  expect(screen.getByText("No runs yet.")).toBeDefined();
  expect(screen.queryByText("Nothing on this page.")).toBeNull();
});
