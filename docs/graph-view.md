# Graph view

A canvas that shows places, institutions, homepages, sources and domains as
nodes and the links between them as edges, in the style of Obsidian's graph
view. The user zooms, drags, searches and filters; clicking a node opens the
thing it stands for. Feasibility: high. About two to four days of work. Every
link the view needs already exists in the database.

## What the graph is

The nodes are the five entity kinds. The edges are the foreign keys that
already relate them:

| Edge                         | From the column                             |
| ---------------------------- | ------------------------------------------- |
| place → parent place         | `places.parent_place_id`                    |
| place → its government       | `places.government_institution_id`          |
| institution → place          | `institutions.place_id`                     |
| institution → parent body    | `institutions.parent_institution_id`        |
| institution → homepage       | `institutions.homepage_id`                  |
| homepage → institution       | `homepages.institution_id`                  |
| source → institution         | `sources.institution_id`                    |
| homepage or source → domain  | `webpages.domain_id` through `webpage_id`   |
| institution → served place   | `institution_served_places`                 |

Ontario alone is about 454 places, as many governments, and then their
institutions, homepages, sources and domains: several thousand nodes. The
canvas can draw that many, but the whole province at once reads as a
hairball. The view therefore starts at one place and grows outward.

## Server

One new endpoint, `GET /graph`, in `modules/graph`. It takes a root place
(`place_id`, default the country), the filters the tables already have
(`administrative_level`, `institution_type`, `status`) and which kinds
to include, and returns one payload:

```json
{
  "nodes": [{ "id": "…", "kind": "institution", "label": "…", "status": "verified", "population": 12000 }],
  "edges": [{ "source": "…", "target": "…", "relation": "place" }]
}
```

The root admits the place and every place under it, as the list endpoints
already do. The service walks the place subtree, then the institutions in
it, then their homepages, sources and domains, in four queries. The payload
is capped at a few thousand nodes; above that the endpoint returns the
places and governments only; the user centres the graph lower down to see more.

The list endpoints are not the right fit: they page at 500 rows and return
one kind per call, so a graph of one region would take many round trips.

## Web

The console has no visualization library. Two fit:

- **react-force-graph-2d**: d3-force physics drawn on a canvas, a React
  component, handles a few thousand nodes without effort. The simplest path.
- **sigma.js with graphology**: WebGL, scales to tens of thousands of nodes,
  more setup. Worth it only if the view must show a whole country at once.

Start with react-force-graph-2d. The feature goes in `features/graph` beside
the tables, with a route at `(console)/graph` and a link from each place and
institution page that opens the view rooted at that row.

What the view does:

- **Lays the hierarchy out as rings.** The root is pinned in the middle and
  each place is pulled to a ring by its depth; institutions sit just outside
  their place, pages outside their institution, domains past their pages. A
  region reads as a region without a label in sight.
- **Starts simple.** A "Show" select picks the detail: Places (the places
  and their governments, the API's `governments` flag), Institutions (every
  institution too) or Everything (the homepages, sources and domains as
  well).
- **Colour says one thing at a time.** Kind (the default), Coverage (a place
  with a government online, an institution with a verified homepage; partial
  and missing in amber and red), Status, or Shared domains, which lights the
  domains that carry pages of more than one institution and sets the rest
  aside.
- **Size** places by population and institutions by their number of sources.
- **Breadcrumb** of the root's ancestors above the canvas, with "Up to
  parent", and a line of counts: levels, places, institutions, web.
- **Hover** shows a tooltip and lights the node's neighbours, dimming the
  rest.
- **Click** opens a compact panel: the node's facts, Open page, and its
  connections grouped by what they are to it (parent place, places within,
  government, institutions, homepage, sources, domain), each a step that
  flies the camera there. The groups fold; the long ones (places within,
  institutions, sources) start folded. On a phone the panel is a sheet.
- **Keys**: Esc clears the selection; the arrow keys walk the connections
  (left and right step through them, up goes to the parent, down into the
  first).
- **Search** is the entity combobox drawn as a search bar; it flies the
  camera to the match, re-rooting first when it is not in the picture. A
  second picker centres the graph on a place.
- **Filters** (status, level, type, platform domains) sit behind a Filters
  popover with a count. Changing one refetches the payload; the layout keeps
  the positions of nodes that stay, so the graph settles instead of jumping.
  A change of root starts a fresh layout.
- **Zoom** buttons and Fit in the canvas corner; a legend and a one-line hint
  of the interactions under it.
- **Theme** reads the colors from the CSS tokens so both modes match the
  rest of the console.
- **URL state**: `place_id`, `detail`, `overlay`, the filters and `node`.

## Steps

1. The endpoint, its schema and the service query, with a test on a small
   fixture: a region, two municipalities, their governments, one homepage,
   one source, one domain. Each node carries what lies beneath it
   (`child_count`, `institution_count`, `homepage_count`, `source_count`) and
   its coverage (`governed`, `online`, `has_homepage`); the payload carries
   the root's `ancestors`.
2. Regenerate the API client.
3. The route, the query options and the canvas with physics, color and
   size. No interaction yet.
4. Hover, click and the side panel.
5. Search, filters, URL state so a view can be shared.
6. The links from the place and institution pages.

## Risks

- **Too many nodes.** Mitigated by the root place and the cap. The demo
  starts at a region, not the province.
- **Layout jitter** on every refetch. Keep node positions across payloads
  and only let new nodes settle.
- **Domains as hubs.** A platform domain such as a hosting service links
  to hundreds of homepages and pulls the layout toward it. Hide platform
  domains by default; show official ones.
