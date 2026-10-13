import { expect, test } from "vite-plus/test";

import {
  optionalEmail,
  optionalId,
  optionalNotes,
  optionalText,
  optionalWebsite,
  requiredText,
} from "./validation";

test("required text is trimmed and bounded", () => {
  expect(requiredText("Name", 5).parse("  Ada ")).toBe("Ada");
  expect(requiredText("Name", 5).safeParse("   ").error?.issues[0]?.message).toBe(
    "Name is required",
  );
  expect(requiredText("Name", 5).safeParse("Augusta").error?.issues[0]?.message).toBe(
    "Name must be at most 5 characters",
  );
});

test("optional fields turn an empty input into null", () => {
  expect(optionalText(10).parse("  ")).toBeNull();
  expect(optionalText(10).parse(" x ")).toBe("x");
  expect(optionalText(3).safeParse("long").error?.issues[0]?.message).toBe(
    "Must be at most 3 characters",
  );
  expect(optionalNotes.parse("")).toBeNull();
  expect(optionalEmail.parse("")).toBeNull();
  expect(optionalEmail.parse("ada@example.com")).toBe("ada@example.com");
  expect(optionalEmail.safeParse("ada").error?.issues[0]?.message).toBe(
    "Enter a valid email address",
  );
  expect(optionalWebsite.parse("")).toBeNull();
  expect(optionalWebsite.parse("https://acme.test")).toBe("https://acme.test");
  expect(optionalWebsite.safeParse("acme.test").error?.issues[0]?.message).toBe(
    "Enter a URL starting with http:// or https://",
  );
  expect(optionalWebsite.safeParse("ftp://acme.test").error?.issues[0]?.message).toBe(
    "Enter a URL starting with http:// or https://",
  );
  expect(optionalId.parse("")).toBeNull();
  expect(optionalId.parse("0199a4a8-6f2e-7c4e-9d0c-0f4a1c3b2a10")).toBe(
    "0199a4a8-6f2e-7c4e-9d0c-0f4a1c3b2a10",
  );
  expect(optionalId.safeParse("nope").error?.issues[0]?.message).toBe("Choose an option");
});
