"use client";

import type { EntityKind, ReviewRow } from "@public-atlas/api-client";
import { useSuspenseQuery } from "@tanstack/react-query";
import { SearchIcon, XIcon } from "lucide-react";
import { useState } from "react";

import { OptionSelect } from "@/components/shared/option-select";
import { DataTable } from "@/components/shared/data-table";
import { TableToolbar } from "@/components/shared/table-toolbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useListState } from "@/hooks/use-list-state";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { browserApi } from "@/lib/api/client";
import {
  entityKindLabels,
  entityKinds,
  reviewRuleLabels,
  reviewRules,
  reviewStatusLabels,
  reviewStatuses,
  type ReviewRule,
} from "@/lib/labels";
import { cn } from "@/lib/utils";

import type { useReviewActions } from "../hooks/use-review-actions";
import { isGroup, questionText } from "../question";
import { reviewListQuery } from "../queries";
import {
  parseReviewSearch,
  reviewFilters,
  type ReviewAffects,
  type ReviewSearch,
} from "../schemas";
import { reviewColumns } from "./review-columns";
import { ReviewMembers } from "./review-members";

const REFRESH_MS = 15_000;
const SEARCH_DEBOUNCE_MS = 250;

/**
 * The queue as one table. An item is a row of its own, except the items that
 * ask the same question: they share a row, set apart and counted in
 * "Affects", which expands to them and approves or rejects them all at once.
 */
export function ReviewTable({
  initialFilters,
  countries,
  timeZone,
  actions,
}: {
  initialFilters: ReviewSearch;
  /** The countries to filter by; the filter shows when there is more than one. */
  countries: { code: string; name: string }[];
  timeZone: string;
  actions: ReturnType<typeof useReviewActions>;
}) {
  const [input, setInput] = useState(initialFilters.q ?? "");
  const q = useDebouncedValue(input.trim(), SEARCH_DEBOUNCE_MS);
  const [status, setStatus] = useState<NonNullable<ReviewSearch["status"]>>(
    initialFilters.status ?? "open",
  );
  const [rule, setRule] = useState<ReviewRule | "">(initialFilters.rule ?? "");
  // Set by a link from an item's page; cleared, not chosen, here.
  const [kind, setKind] = useState(initialFilters.kind ?? "");
  const [entityKind, setEntityKind] = useState<EntityKind | "">(initialFilters.entity_kind ?? "");
  const [countryCode, setCountryCode] = useState(initialFilters.country_code ?? "");
  const [affects, setAffects] = useState<ReviewAffects | "">(initialFilters.affects ?? "");
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  // What the controls choose; open items are the default and stay out of the URL.
  const chosen = {
    q: q || undefined,
    status: status === "open" ? undefined : status,
    rule: rule || undefined,
    kind: kind || undefined,
    entity_kind: entityKind || undefined,
    country_code: countryCode || undefined,
    affects: affects || undefined,
  };
  const list = useListState({
    filterKey: JSON.stringify(chosen),
    initial: initialFilters,
    defaultSort: { sort: "count", order: "desc" },
  });
  const { deferred, isStale } = useUrlFilters({ ...chosen, ...list.search }, parseReviewSearch);
  const { data: rows } = useSuspenseQuery({
    ...reviewListQuery(browserApi, reviewFilters(deferred)),
    refetchInterval: REFRESH_MS,
  });

  const filtered = Object.values(chosen).some((value) => value !== undefined);
  const clear = () => {
    setInput("");
    setStatus("open");
    setRule("");
    setKind("");
    setEntityKind("");
    setCountryCode("");
    setAffects("");
  };
  const toggle = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  return (
    <div className="flex flex-col gap-4">
      <TableToolbar
        search={
          <InputGroup>
            <InputGroupAddon>
              <SearchIcon />
            </InputGroupAddon>
            <InputGroupInput
              type="search"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Name, URL or reason"
              aria-label="Search the queue"
            />
          </InputGroup>
        }
        filters={
          <>
            {kind && (
              <Badge variant="info" className="h-8 max-w-full gap-1 pr-1">
                <span className="truncate">
                  {(rows.items[0] && questionText(rows.items[0].rule, rows.items[0].question)) ??
                    "One question"}
                </span>
                <Button
                  size="icon-xs"
                  variant="ghost"
                  onClick={() => setKind("")}
                  aria-label="Show every question"
                >
                  <XIcon />
                </Button>
              </Badge>
            )}
            <OptionSelect<NonNullable<ReviewSearch["status"]>>
              value={status}
              onValueChange={setStatus}
              aria-label="Filter by status"
              options={[
                ...reviewStatuses.map((value) => ({ value, label: reviewStatusLabels[value] })),
                { value: "all", label: "Any status" },
              ]}
            />
            <OptionSelect<ReviewRule | "">
              value={rule}
              onValueChange={setRule}
              aria-label="Filter by reason"
              options={[
                { value: "", label: "Any reason" },
                ...reviewRules.map((value) => ({ value, label: reviewRuleLabels[value] })),
              ]}
            />
            <OptionSelect<EntityKind | "">
              value={entityKind}
              onValueChange={setEntityKind}
              aria-label="Filter by entity"
              options={[
                { value: "", label: "Any entity" },
                ...entityKinds.map((value) => ({ value, label: entityKindLabels[value] })),
              ]}
            />
            {countries.length > 1 && (
              <OptionSelect
                value={countryCode}
                onValueChange={setCountryCode}
                aria-label="Filter by country"
                options={[
                  { value: "", label: "Any country" },
                  ...countries.map((country) => ({ value: country.code, label: country.name })),
                ]}
              />
            )}
            <OptionSelect<ReviewAffects | "">
              value={affects}
              onValueChange={setAffects}
              aria-label="Filter by how many entities a row affects"
              options={[
                { value: "", label: "Any size" },
                { value: "several", label: "Affects several" },
                { value: "one", label: "Affects one" },
              ]}
            />
          </>
        }
        count={`${rows.total} ${rows.total === 1 ? "row" : "rows"}`}
        onClear={filtered ? clear : undefined}
      />
      <DataTable<ReviewRow>
        columns={reviewColumns({ timeZone, actions, expanded, onToggle: toggle })}
        data={rows.items}
        total={rows.total}
        page={list.page}
        onPageChange={list.setPage}
        sorting={list.sorting}
        onSortingChange={list.setSorting}
        rowClassName={(row) =>
          isGroup(row)
            ? "bg-primary/[0.03] [&>td:first-child]:shadow-[inset_2px_0_0_var(--color-primary)]"
            : undefined
        }
        renderSubRow={(row) =>
          isGroup(row) && expanded.has(row.id) ? (
            <ReviewMembers row={row} timeZone={timeZone} actions={actions} />
          ) : null
        }
        emptyMessage={filtered ? "Nothing matches these filters." : "The queue is empty."}
        className={cn(isStale && "opacity-60 transition-opacity")}
      />
    </div>
  );
}
