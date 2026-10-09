"use client";

import type {
  CountryOutput,
  EntityStatus,
  GraphNode,
  InstitutionTypeInput,
} from "@public-atlas/api-client";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpIcon,
  ChevronRightIcon,
  Loader2Icon,
  SearchIcon,
  SlidersHorizontalIcon,
} from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";

import { EntityCombobox } from "@/components/shared/entity-combobox";
import { TableToolbar } from "@/components/shared/table-toolbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import { useUrlFilters } from "@/hooks/use-url-filters";
import { browserApi } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { entityKindLabels, entityStatusLabels, entityStatuses, humanize } from "@/lib/labels";
import { cn } from "@/lib/utils";

import {
  combine,
  connections,
  coverageLabels,
  emptyGraph,
  graphDetailLabels,
  graphDetails,
  graphKinds,
  graphOverlayLabels,
  graphOverlays,
  rings,
  sharedDomainEmphasis,
  sharedDomains,
  withPositions,
  type GraphData,
  type GraphDetail,
  type GraphOverlay,
} from "../graph-data";
import {
  graphQuery,
  graphViewFilters,
  institutionQuery,
  placeOptionQuery,
  placePickerQuery,
  subjectOptionQuery,
  subjectPickerQuery,
} from "../queries";
import { parseGraphSearch, type GraphSearch } from "../schemas";
import { GraphCanvas } from "./graph-canvas";
import { GraphPanel, kindDot } from "./graph-panel";

/** The connection groups that lead up the hierarchy, from any kind. */
const UPWARD = new Set(["Parent place", "Place", "Institution", "Pages"]);

/**
 * The graph view: the picture under a root place with the controls above it,
 * a panel beside it for the clicked node, and the URL kept in step so a view
 * can be shared. The canvas keeps its positions through every refetch.
 */
export function GraphView({
  initialSearch,
  countries,
  institutionTypes,
}: {
  initialSearch: GraphSearch;
  countries: CountryOutput[];
  institutionTypes: InstitutionTypeInput[];
}) {
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();
  const [rootId, setRootId] = useState(initialSearch.place_id ?? "");
  const [detail, setDetail] = useState<GraphDetail>(initialSearch.detail ?? "hierarchy");
  const [overlay, setOverlay] = useState<GraphOverlay>(initialSearch.overlay ?? "kind");
  const [status, setStatus] = useState<EntityStatus | "">(initialSearch.status ?? "");
  const [level, setLevel] = useState(initialSearch.administrative_level ?? "");
  const [type, setType] = useState(initialSearch.institution_type ?? "");
  const [platforms, setPlatforms] = useState(initialSearch.platforms === "1");
  const [selected, setSelected] = useState(initialSearch.node);
  // The node the camera flies to: the URL's on arrival, then whatever the search finds.
  const [focus, setFocus] = useState<{ id: string; key: number } | null>(
    initialSearch.node ? { id: initialSearch.node, key: 0 } : null,
  );
  // Where the arrow keys are: the node whose connections they step through, and which one.
  const [step, setStep] = useState<{ anchor: string; index: number } | null>(null);
  const [goto, setGoto] = useState("");

  const chosen = {
    place_id: rootId || undefined,
    country_code: initialSearch.country_code,
    detail: detail === "hierarchy" ? undefined : detail,
    overlay: overlay === "kind" ? undefined : overlay,
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
  const picture = useMemo(() => combine(base.data ? [base.data] : []), [base.data]);
  const root = base.data?.root_id;

  // The canvas's data: the node objects survive each payload (see graph-data.ts), except
  // across a change of root, where the picture is a new one and gets a fresh layout.
  const [data, setData] = useState<{ root: string | undefined; graph: GraphData }>({
    root: undefined,
    graph: emptyGraph,
  });
  useEffect(() => {
    setData((previous) => ({
      root,
      graph: withPositions(
        previous.root === root ? previous.graph : emptyGraph,
        picture.nodes,
        picture.edges,
      ),
    }));
  }, [picture, root]);

  const byId = useMemo(() => new Map(picture.nodes.map((node) => [node.id, node])), [picture]);
  const ring = useMemo(() => rings(root, picture.nodes, picture.edges), [root, picture]);
  const shared = useMemo(
    () => (overlay === "domains" ? sharedDomains(picture.nodes, picture.edges) : null),
    [overlay, picture],
  );
  const emphasis = useMemo(
    () => (shared ? sharedDomainEmphasis(shared, picture.edges) : null),
    [shared, picture],
  );
  const selectedNode = selected ? byId.get(selected) : undefined;
  const connected = useMemo(
    () => (selectedNode ? connections(selectedNode, byId, picture.edges) : []),
    [selectedNode, byId, picture],
  );

  const select = (id: string | undefined) => {
    setSelected(id);
    setStep(null);
  };

  const changeRoot = (id: string) => {
    setRootId(id);
    setStep(null);
  };

  const flyTo = (id: string) => setFocus((current) => ({ id, key: (current?.key ?? 0) + 1 }));

  /** The search's pick: fly to it, re-rooting the picture first when it is not in it. */
  const visit = async (id: string) => {
    setGoto("");
    if (!id) return;
    select(id);
    if (byId.has(id)) {
      flyTo(id);
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
    flyTo(id);
  };

  // The keys: Esc clears, the arrows walk the connections of the selected node.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (
        target?.closest("input, textarea, select, [contenteditable], [role=dialog], [role=listbox]")
      ) {
        return;
      }
      if (event.key === "Escape") {
        select(undefined);
        return;
      }
      if (!selectedNode) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        const anchorId = step?.anchor ?? selectedNode.id;
        const anchor = byId.get(anchorId);
        const steps = anchor
          ? connections(anchor, byId, picture.edges).flatMap((group) => group.nodes)
          : [];
        if (steps.length === 0) return;
        event.preventDefault();
        const direction = event.key === "ArrowRight" ? 1 : -1;
        const index = step
          ? (step.index + direction + steps.length) % steps.length
          : direction > 0
            ? 0
            : steps.length - 1;
        const next = steps[index]!;
        setStep({ anchor: anchorId, index });
        setSelected(next.id);
        flyTo(next.id);
      } else if (event.key === "ArrowUp") {
        const up = connected.find((group) => UPWARD.has(group.label))?.nodes[0];
        if (!up) return;
        event.preventDefault();
        select(up.id);
        flyTo(up.id);
      } else if (event.key === "ArrowDown") {
        const down = connected.find((group) => !UPWARD.has(group.label))?.nodes[0];
        if (!down) return;
        event.preventDefault();
        const all = connected.flatMap((group) => group.nodes);
        setStep({ anchor: selectedNode.id, index: all.findIndex((node) => node.id === down.id) });
        setSelected(down.id);
        flyTo(down.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedNode, connected, step, byId, picture]);

  const chooseOverlay = (value: GraphOverlay) => {
    setOverlay(value);
    // Shared domains are in the web; the picture opens up to show them.
    if (value === "domains") {
      setDetail("web");
      setPlatforms(true);
    }
  };

  const levelOptions = [
    ...new Set(
      countries.flatMap((c) =>
        c.administrative_levels.toSorted((a, b) => a.rank - b.rank).map((l) => l.name),
      ),
    ),
  ];
  const filterCount = [status, level, type].filter(Boolean).length + (platforms ? 1 : 0);
  const clear = () => {
    setStatus("");
    setLevel("");
    setType("");
    setPlatforms(false);
  };

  const ancestors = base.data?.ancestors ?? [];
  const parent = ancestors.at(-1);
  const rootNode = root ? byId.get(root) : undefined;
  const counts = { place: 0, institution: 0, web: 0, levels: 0 };
  for (const node of picture.nodes) {
    if (node.kind === "place") {
      counts.place++;
      counts.levels = Math.max(counts.levels, ring.get(node.id) ?? 0);
    } else if (node.kind === "institution") {
      counts.institution++;
    } else {
      counts.web++;
    }
  }
  const stats = [
    `${counts.levels} ${counts.levels === 1 ? "level" : "levels"} deep`,
    `${counts.place} ${counts.place === 1 ? "place" : "places"}`,
    `${counts.institution} ${counts.institution === 1 ? "institution" : "institutions"}`,
    ...(counts.web > 0 ? [`${counts.web} on the web`] : []),
  ].join(" · ");

  const panel = selectedNode && (
    <GraphPanel
      node={selectedNode}
      connections={connected}
      onClose={() => select(undefined)}
      onSelect={(id) => void visit(id)}
    />
  );

  return (
    <div className="flex flex-col gap-4">
      <TableToolbar
        search={
          <EntityCombobox
            id="graph-search"
            name="goto"
            value={goto}
            onValueChange={(id) => void visit(id)}
            placeholder="Search places and institutions"
            icon={<SearchIcon />}
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
                placeholder="Centre the graph on a place"
                search={(text) => placePickerQuery(browserApi, text)}
                resolve={(id) => placeOptionQuery(browserApi, id)}
              />
            </div>
            <Select
              value={detail}
              onValueChange={(value) => setDetail(value as GraphDetail)}
              items={graphDetailLabels}
            >
              <SelectTrigger aria-label="How much to draw">
                <span className="text-muted-foreground">Show</span>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {graphDetails.map((value) => (
                  <SelectItem key={value} value={value}>
                    {graphDetailLabels[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={overlay}
              onValueChange={(value) => chooseOverlay(value as GraphOverlay)}
              items={graphOverlayLabels}
            >
              <SelectTrigger aria-label="What the colour shows">
                <span className="text-muted-foreground">Colour</span>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {graphOverlays.map((value) => (
                  <SelectItem key={value} value={value}>
                    {graphOverlayLabels[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Popover>
              <PopoverTrigger render={<Button variant="outline" />}>
                <SlidersHorizontalIcon /> Filters
                {filterCount > 0 && (
                  <Badge variant="secondary" className="tabular-nums">
                    {filterCount}
                  </Badge>
                )}
              </PopoverTrigger>
              <PopoverContent className="flex w-72 flex-col gap-3">
                <PopoverTitle>Filters</PopoverTitle>
                <Label className="flex flex-col items-start gap-1">
                  Status
                  <NativeSelect
                    value={status}
                    onChange={(event) => setStatus(event.target.value as EntityStatus | "")}
                    className="w-full"
                  >
                    <NativeSelectOption value="">Any status but rejected</NativeSelectOption>
                    {entityStatuses.map((value) => (
                      <NativeSelectOption key={value} value={value}>
                        {entityStatusLabels[value]}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Label>
                <Label className="flex flex-col items-start gap-1">
                  Administrative level
                  <NativeSelect
                    value={level}
                    onChange={(event) => setLevel(event.target.value)}
                    className="w-full"
                  >
                    <NativeSelectOption value="">Any level</NativeSelectOption>
                    {levelOptions.map((name) => (
                      <NativeSelectOption key={name} value={name}>
                        {humanize(name)}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Label>
                <Label className="flex flex-col items-start gap-1">
                  Institution type
                  <NativeSelect
                    value={type}
                    onChange={(event) => setType(event.target.value)}
                    className="w-full"
                    disabled={detail === "hierarchy"}
                  >
                    <NativeSelectOption value="">Any type</NativeSelectOption>
                    {institutionTypes.map((t) => (
                      <NativeSelectOption key={t.name} value={t.name}>
                        {humanize(t.name)}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                  {detail === "hierarchy" && (
                    <span className="text-xs font-normal text-muted-foreground">
                      The hierarchy shows governments alone.
                    </span>
                  )}
                </Label>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={platforms}
                    onCheckedChange={(checked) => setPlatforms(checked === true)}
                  />
                  Platform domains
                </label>
                {filterCount > 0 && (
                  <Button variant="ghost" size="sm" onClick={clear} className="self-start">
                    Clear filters
                  </Button>
                )}
              </PopoverContent>
            </Popover>
          </>
        }
        count={
          base.isFetching && <Loader2Icon className="size-3.5 animate-spin" aria-label="Loading" />
        }
        onClear={filterCount > 0 ? clear : undefined}
      />
      {base.data?.truncated && (
        <p className="text-sm text-warning">
          Over the cap: showing the places and their governments alone. Centre the graph on a
          smaller place to see everything beneath it.
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-sm">
        <nav aria-label="Root" className="flex min-w-0 flex-wrap items-center gap-1">
          {ancestors.map((ancestor) => (
            <Fragment key={ancestor.id}>
              <button
                type="button"
                onClick={() => changeRoot(ancestor.id)}
                className="text-muted-foreground hover:text-foreground hover:underline"
              >
                {ancestor.label}
              </button>
              <ChevronRightIcon className="size-3.5 text-muted-foreground/60" aria-hidden="true" />
            </Fragment>
          ))}
          <span className="font-medium">{rootNode?.label ?? "…"}</span>
          {parent && (
            <Button
              variant="ghost"
              size="xs"
              onClick={() => changeRoot(parent.id)}
              className="ml-1 text-muted-foreground"
            >
              <ArrowUpIcon /> Up to {parent.label}
            </Button>
          )}
        </nav>
        {rootNode && <p className="text-muted-foreground tabular-nums">{stats}</p>}
      </div>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-stretch">
        <div
          className={cn(
            "relative h-[max(28rem,calc(100svh-18rem))] min-w-0 flex-1 overflow-hidden rounded-lg border bg-card transition-opacity",
            isStale && "opacity-60",
          )}
        >
          <GraphCanvas
            data={data.graph}
            rootId={root}
            selectedId={selected}
            focus={focus}
            overlay={overlay}
            emphasis={emphasis}
            onSelect={select}
          />
          {base.isPending && (
            <p className="absolute inset-x-0 top-1/2 flex -translate-y-1/2 items-center justify-center gap-2 px-6 text-center text-sm text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin" aria-hidden="true" /> Drawing the
              picture…
            </p>
          )}
          {base.isError && (
            <div className="absolute inset-x-0 top-1/2 flex -translate-y-1/2 flex-col gap-1 px-6 text-center text-sm">
              <p className="text-destructive">{errorMessage(base.error)}</p>
              <p className="text-muted-foreground">
                Pick a root place above, or search for a place or an institution.
              </p>
            </div>
          )}
          {shared?.size === 0 && picture.nodes.length > 0 && (
            <p className="pointer-events-none absolute inset-x-0 top-3 px-6 text-center text-sm text-muted-foreground">
              No domain here carries pages of more than one institution.
            </p>
          )}
          {base.data && picture.nodes.length === 0 && (
            <p className="absolute inset-x-0 top-1/2 -translate-y-1/2 px-6 text-center text-sm text-muted-foreground">
              Nothing matches these filters.
            </p>
          )}
        </div>
        {!isMobile && panel && (
          <div className="shrink-0 lg:h-[max(28rem,calc(100svh-18rem))] lg:w-80 lg:overflow-y-auto xl:w-96">
            {panel}
          </div>
        )}
        <Sheet
          open={isMobile && selectedNode !== undefined}
          onOpenChange={(open) => !open && select(undefined)}
        >
          <SheetContent
            side="bottom"
            showCloseButton={false}
            className="max-h-[75svh] overflow-y-auto p-4"
          >
            <SheetTitle className="sr-only">
              {selectedNode ? `${entityKindLabels[selectedNode.kind]} details` : "Details"}
            </SheetTitle>
            {panel}
          </SheetContent>
        </Sheet>
      </div>
      <div className="flex flex-col gap-1 text-xs text-muted-foreground">
        <Legend overlay={overlay} present={picture.nodes} shared={shared?.size ?? 0} />
        <p>
          Click a node for its connections · scroll to zoom, drag to pan · arrow keys walk the
          connections, Esc clears
        </p>
      </div>
    </div>
  );
}

/** What the colours mean under the overlay in force. */
function Legend({
  overlay,
  present,
  shared,
}: {
  overlay: GraphOverlay;
  present: readonly GraphNode[];
  shared: number;
}) {
  const kinds = new Set(present.map((node) => node.kind));
  const entries: { className: string; label: string }[] =
    overlay === "kind"
      ? graphKinds
          .filter((kind) => kinds.has(kind))
          .map((kind) => ({ className: kindDot[kind], label: entityKindLabels[kind] }))
      : overlay === "status"
        ? [
            { className: "bg-success", label: entityStatusLabels.verified },
            { className: "bg-muted-foreground", label: entityStatusLabels.candidate },
            { className: "bg-warning", label: entityStatusLabels.needs_review },
            { className: "bg-destructive", label: entityStatusLabels.rejected },
          ]
        : overlay === "coverage"
          ? [
              {
                className: "bg-success",
                label: `${coverageLabels.covered}: a government online, a verified homepage`,
              },
              {
                className: "bg-warning",
                label: `${coverageLabels.partial}: a government without a homepage, a claim pending`,
              },
              {
                className: "bg-destructive",
                label: `${coverageLabels.missing}: no government, no homepage`,
              },
            ]
          : [
              { className: kindDot.domain, label: "Shared domain" },
              { className: kindDot.institution, label: "Institution on one" },
              { className: "bg-muted-foreground/40", label: "Everything else" },
            ];
  return (
    <ul className="flex flex-wrap items-center gap-x-3 gap-y-1" aria-label="Legend">
      {overlay === "domains" && (
        <li className="tabular-nums">
          {shared} shared {shared === 1 ? "domain" : "domains"}
        </li>
      )}
      {entries.map((entry) => (
        <li key={entry.label} className="flex items-center gap-1.5">
          <span aria-hidden="true" className={cn("size-2.5 rounded-full", entry.className)} />
          {entry.label}
        </li>
      ))}
    </ul>
  );
}
