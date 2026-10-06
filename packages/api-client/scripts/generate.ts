// Exports the OpenAPI schema from apps/server and generates TypeScript types
// from it. Run from the package root: `vp run generate` (or `--check` to
// verify the committed files are current, as CI does).
//
// Both outputs are committed so consumers never need Python installed, and
// schema changes show up in code review.

import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";

const packageRoot = new URL("../", import.meta.url);
const schemaPath = new URL("openapi.json", packageRoot);
const typesPath = new URL("src/generated/schema.ts", packageRoot);

const check = process.argv.includes("--check");

// `uv run` finds the workspace from the cwd, so this works from any directory
// inside the repository.
const schema = execFileSync(
  "uv",
  ["run", "--package", "public-atlas-server", "python", "-m", "public_atlas.openapi"],
  { encoding: "utf8", stdio: ["ignore", "pipe", "inherit"] },
);

const ast = await openapiTS(JSON.parse(schema), {
  // Component schemas also as top-level aliases (`Health`, not only
  // `components["schemas"]["Health"]`).
  rootTypes: true,
  rootTypesNoSchemaPrefix: true,
});
const types = astToString(ast);

const outputs = [
  [schemaPath, schema],
  [typesPath, types],
] as const;

if (check) {
  const stale = outputs.filter(([path, contents]) => {
    try {
      return readFileSync(path, "utf8") !== contents;
    } catch {
      return true;
    }
  });
  if (stale.length > 0) {
    for (const [path] of stale) {
      console.error(`stale: ${fileURLToPath(path)}`);
    }
    console.error("Run `vp run generate` in packages/api-client and commit the result.");
    process.exit(1);
  }
  console.log("Generated files are up to date.");
} else {
  for (const [path, contents] of outputs) {
    writeFileSync(path, contents);
    console.log(`wrote ${fileURLToPath(path)}`);
  }
}
