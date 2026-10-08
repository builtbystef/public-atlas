"use client";

import type {
  CountryOutput,
  EntityKind,
  EntityStatus,
  GraphNode,
  GraphOutput,
  InstitutionTypeInput,
} from "@public-atlas/api-client";
import {
  keepPreviousData,
  useQueries,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { Loader2Icon, MaximizeIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { EntityCombobox } from "@/components/shared/entity-combobox";
import { TableToolbar } from "@/components/shared/table-toolbar";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { entityKindLabels, entityStatusLabels, entityStatuses, humanize } from "@/lib/labels";
import { cn } from "@/lib/utils";

import {
  combine,
  emptyGraph,
  graphKinds,
  kindsParam,
  parseKinds,
  withPositions,
  type GraphData,
} from "../graph-data";
import {
  graphQuery,
  graphViewFilters,
  institutionQuery,
  placeOptionQuery,
  placePickerQuery,
  subjectOptionQuery,
  subjectPickerQuery,
  type GraphViewFilters,
} from "../queries";
import { parseGraphSearch, type GraphSearch } from "../schemas";
import { GraphCanvas, type GraphCamera } from "./graph-canvas";
import { GraphPanel } from "./graph-panel";

/** A node the user opened up: a place shows what is directly under it, an institution its web. */
interface Expansion {
  id: string;
  kind: "place" | "institution";
}

const kindDot: Record<EntityKind, string> = {
  place: "bg-graph-place",
  institution: "bg-graph-institution",
  homepage: "bg-graph-homepage",
  source: "bg-graph-source",
  domain: "bg-graph-domain",
};

/**
 * The graph view: the picture under a root place with the filters above it,
 * a panel beside it for the clicked node, and the URL kept in step so a view
 * can be shared. Expansions are queries of their own, refetched with the
 * filters, and the canvas keeps its positions through all of it.
 */
export function GraphView({
  initialSearch,
  countries,
  institutionTypes,
  timeZone,
}: {
  initialSearch: GraphSearch;
  countries: CountryOutput[];
  institutionTypes: InstitutionTypeInput[];
  timeZone: string;
}) {
  const queryClient = useQueryClient();
  const [rootId, setRootId] = useState(initialSearch.place_id ?? "");
  const [kinds, setKinds] = useState<EntityKind[]>(parseKinds(initialSearch.kinds));
  const [status, setStatus] = useState<EntityStatus | "">(initialSearch.status ?? "");
  const [level, setLevel] = useState(initialSearch.administrative_level ?? "");
  const [type, setType] = useState(initialSearch.institution_type ?? "");
  const [platforms, setPlatforms] = useState(initialSearch.platforms === "1");
  const [selected, setSelected] = useState(initialSearch.node);
  const [expansions, setExpansions] = useState<Expansion[]>([]);
  // The node the camera flies to: the URL's on arrival, then whatever the search finds.
  const [focus, setFocus] = useState<{ id: string; key: number } | null>(
    initialSearch.node ? { id: initialSearch.node, key: 0 } : null,
  );
  const [goto, setGoto] = useState("");
  const camera = useRef<GraphCamera>(null);

  const chosen = {
    place_id: rootId || undefined,
    country_code: initialSearch.country_code,
    kinds: kindsParam(kinds),
    status: status || undefined,
    administrative_level: level || undefined,
    institution_type: type || undefined,
    platforms: platforms ? ("1" as const) : undefined,
    node: selected,
  };
  const { deferred, isStale } = useUrlFilters(chosen, parseGraphSearch);
  const filters = graphViewFilters(deferred);

  const base = useQuery({
    ...graphQuery(browserApi, filters),
    placeholderData: keepPreviousData,
  });
  const expanded = useQueries({
    queries: expansions.map((expansion) => ({
      ...graphQuery(browserApi, expansionFilters(filters, expansion)),
      placeholderData: keepPreviousData,
    })),
    combine: combineExpansions,
  });
  const fetching = base.isFetching || expanded.fetching;

  const picture = useMemo(
    () => combine([base.data, ...expanded.data].filter((payload) => payload !== undefined)),
    [base.data, expanded.data],
  );

  // The canvas's data: the node objects survive each payload (see graph-data.ts).
  const [data, setData] = useState<GraphData>(emptyGraph);
  useEffect(() => {
    setData((previous) => withPositions(previous, picture.nodes, picture.edges));
  }, [picture]);

  const byId = useMemo(() => new Map(picture.nodes.map((node) => [node.id, node])), [picture]);
  const selectedNode = selected ? byId.get(selected) : undefined;
  const owner = useMemo(() => {
    if (!selectedNode || (selectedNode.kind !== "homepage" && selectedNode.kind !== "source")) {
      return undefined;
    }
    const edge = picture.edges.find(
      (e) => e.source === selectedNode.id && (e.relation === "homepage" || e.relation === "source"),
    );
    return edge ? byId.get(edge.target) : undefined;
  }, [selectedNode, picture, byId]);

  const expand = (node: GraphNode) => {
    if (node.kind !== "place" && node.kind !== "institution") return;
    const expansion: Expansion = { id: node.id, kind: node.kind };
    setExpansions((current) =>
      current.some((e) => e.id === node.id) ? current : [...current, expansion],
    );
  };

  const changeRoot = (id: string) => {
    setRootId(id);
    setExpansions([]);
  };

  /** The search's pick: fly to it, re-rooting the picture first when it is not in it. */
  const visit = async (id: string) => {
    setGoto("");
    if (!id) return;
    setSelected(id);
    if (byId.has(id)) {
      setFocus((current) => ({ id, key: (current?.key ?? 0) + 1 }));
      return;
    }
    const place = await browserApi.GET("/places/{place_id}", {
      params: { path: { place_id: id } },
    });
    if (place.response.ok && place.data) {
      changeRoot(place.data.id);
    } else {
      const institution = await queryClient.fetchQuery(institutionQuery(browserApi, id));
      changeRoot(institution.place.id);
    }
    setFocus((current) => ({ id, key: (current?.key ?? 0) + 1 }));
  };

  const levelOptions = [
    ...new Set(
      countries.flatMap((c) =>
        c.administrative_levels.toSorted((a, b) => a.rank - b.rank).map((l) => l.name),
      ),
    ),
  ];
  const filtered =
    kinds.length < graphKinds.length || status !== "" || level !== "" || type !== "" || platforms;
  const clear = () => {
    setKinds([...graphKinds]);
    setStatus("");
    setLevel("");
    setType("");
    setPlatforms(false);
  };
  const toggleKind = (kind: EntityKind) =>
    setKinds((current) =>
      current.includes(kind) ? current.filter((k) => k !== kind) : [...current, kind],
    );

  const count = `${picture.nodes.length} ${picture.nodes.length === 1 ? "node" : "nodes"} · ${picture.edges.length} ${picture.edges.length === 1 ? "edge" : "edges"}`;

  return (
    <div className="flex flex-col gap-4">
      <TableToolbar
        search={
          <EntityCombobox
            id="graph-search"
            name="goto"
            value={goto}
            onValueChange={(id) => void visit(id)}
            placeholder="Find a place or institution"
            search={(text) => subjectPickerQuery(browserApi, text)}
            resolve={(id) => subjectOptionQuery(browserApi, id)}
          />
        }
        filters={
          <>
            <div className="w-56">
              <EntityCombobox
                id="graph-root"
                name="place_id"
                value={rootId}
                onValueChange={changeRoot}
                placeholder="Rooted at the country"
                search={(text) => placePickerQuery(browserApi, text)}
                resolve={(id) => placeOptionQuery(browserApi, id)}
              />
            </div>
            <div
              role="group"
              aria-label="Kinds shown"
              className="flex flex-wrap items-center gap-1"
            >
              {graphKinds.map((kind) => {
                const on = kinds.includes(kind);
                return (
                  <Button
                    key={kind}
                    variant={on ? "secondary" : "ghost"}
                    size="sm"
                    aria-pressed={on}
                    onClick={() => toggleKind(kind)}
                    className={cn("gap-1.5", !on && "text-muted-foreground")}
                  >
                    <span
                      aria-hidden="true"
                      className={cn("size-2.5 rounded-full", kindDot[kind], !on && "opacity-40")}
                    />
                    {entityKindLabels[kind]}
                  </Button>
                );
              })}
            </div>
            <NativeSelect
              value={status}
              onChange={(event) => setStatus(event.target.value as EntityStatus | "")}
              aria-label="Filter by status"
            >
              <NativeSelectOption value="">Any status but rejected</NativeSelectOption>
              {entityStatuses.map((value) => (
                <NativeSelectOption key={value} value={value}>
                  {entityStatusLabels[value]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <NativeSelect
              value={level}
              onChange={(event) => setLevel(event.target.value)}
              aria-label="Filter by administrative level"
            >
              <NativeSelectOption value="">Any level</NativeSelectOption>
              {levelOptions.map((name) => (
                <NativeSelectOption key={name} value={name}>
                  {humanize(name)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <NativeSelect
              value={type}
              onChange={(event) => setType(event.target.value)}
              aria-label="Filter by institution type"
            >
              <NativeSelectOption value="">Any type</NativeSelectOption>
              {institutionTypes.map((t) => (
                <NativeSelectOption key={t.name} value={t.name}>
                  {humanize(t.name)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <label className="flex items-center gap-2 text-sm whitespace-nowrap">
              <Checkbox
                checked={platforms}
                onCheckedChange={(checked) => setPlatforms(checked === true)}
              />
              Platform domains
            </label>
          </>
        }
        count={
          <span className="flex items-center gap-2">
            {fetching && <Loader2Icon className="size-3.5 animate-spin" aria-label="Loading" />}
            {count}
            {base.data?.truncated && (
              <span className="text-warning">· places and governments only</span>
            )}
          </span>
        }
        actions={
          <Button variant="outline" onClick={() => camera.current?.fit()} aria-label="Fit to view">
            <MaximizeIcon /> Fit
          </Button>
        }
        onClear={filtered ? clear : undefined}
      />
      <div className="flex flex-col gap-4 lg:flex-row lg:items-stretch">
        <div
          className={cn(
            "relative h-[max(28rem,calc(100svh-16rem))] min-w-0 flex-1 overflow-hidden rounded-lg border bg-card transition-opacity",
            isStale && "opacity-60",
          )}
        >
          <GraphCanvas
            data={data}
            rootId={base.data?.root_id}
            selectedId={selected}
            focus={focus}
            onSelect={setSelected}
            onExpand={expand}
            cameraRef={camera}
          />
          {base.isError && (
            <p className="absolute inset-x-0 top-1/2 -translate-y-1/2 px-6 text-center text-sm text-destructive">
              {errorMessage(base.error)}
            </p>
          )}
          {base.data && picture.nodes.length === 0 && (
            <p className="absolute inset-x-0 top-1/2 -translate-y-1/2 px-6 text-center text-sm text-muted-foreground">
              Nothing matches these filters.
            </p>
          )}
          <p className="pointer-events-none absolute right-3 bottom-2 left-3 text-right text-xs text-muted-foreground/70">
            {base.data?.truncated
              ? "Too many nodes for one picture: double-click a place to expand it."
              : "Scroll to zoom, drag to pan. Click a node for its details, double-click to expand it."}
          </p>
        </div>
        {selectedNode && (
          <div className="shrink-0 lg:h-[max(28rem,calc(100svh-16rem))] lg:w-[34rem] lg:overflow-y-auto xl:w-[40rem]">
            <GraphPanel
              node={selectedNode}
              owner={owner}
              timeZone={timeZone}
              onClose={() => setSelected(undefined)}
              onExpand={expand}
              onSelect={(id) => void visit(id)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * The expansions' results as one value. A named function, so the result is
 * structurally shared across renders and the picture is rebuilt only when a
 * payload changes.
 */
function combineExpansions(results: UseQueryResult<GraphOutput>[]) {
  return {
    data: results.map((result) => result.data),
    fetching: results.some((result) => result.isFetching),
  };
}

/** What an expansion asks for, under the filters in force: a place one level down, an institution's web. */
function expansionFilters(filters: GraphViewFilters, expansion: Expansion): GraphViewFilters {
  const { place_id: _root, country_code: _country, ...rest } = filters;
  return expansion.kind === "place"
    ? { ...rest, place_id: expansion.id, depth: 1 }
    : { ...rest, institution_id: expansion.id };
}
