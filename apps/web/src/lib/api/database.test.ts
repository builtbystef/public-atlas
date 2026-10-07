import { expect, test } from "vite-plus/test";

import { databaseCookie, parseDatabase, readDatabaseCookie } from "./database";

test("the live database is the default and the fallback", () => {
  expect(parseDatabase(undefined)).toBe("main");
  expect(parseDatabase("staging")).toBe("main");
  expect(parseDatabase("eval")).toBe("eval");
});

test("the database cookie is read out of document.cookie", () => {
  expect(readDatabaseCookie("")).toBe("main");
  expect(readDatabaseCookie("tz=Europe%2FBerlin; db=eval; sidebar_state=true")).toBe("eval");
  expect(readDatabaseCookie("db=nonsense")).toBe("main");
});

test("the cookie string names the database", () => {
  expect(databaseCookie("eval")).toMatch(/^db=eval; path=\/;/);
});
