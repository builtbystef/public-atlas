import { z } from "zod";

import { listSearch, parseSearch, type SearchParams } from "@/lib/lists";

const evalSearchSchema = z.object({ ...listSearch(["started_at"]) });

export type EvalSearch = z.output<typeof evalSearchSchema>;

export function parseEvalSearch(params: SearchParams | URLSearchParams): EvalSearch {
  return parseSearch(evalSearchSchema, params);
}
