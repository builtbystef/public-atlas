# Map view

A map the user drills into: the country shows its provinces, a province its
regions, a region its municipalities, and each shape is shaded by what the
atlas knows about it. Clicking a shape zooms in and lists the institutions
at that level. Feasibility: medium. About four to seven days, and the
geographic data is the uncertain part: the model has no coordinates or
boundaries today.

## Where the shapes come from

Every Ontario place carries a Statistics Canada code in `identifiers`
(scheme `statcan_sgc`): regions have the census division code and
municipalities the census subdivision code, as `imports/lists/ontario_places.py`
assigns them. Statistics Canada publishes free 2021 cartographic boundary
files keyed by those same codes, one per level:

| Level              | Boundary file       | Join key |
| ------------------ | ------------------- | -------- |
| province_territory | Provinces           | `PRUID`  |
| region             | Census divisions    | `CDUID`  |
| municipality       | Census subdivisions | `CSDUID` |

So a place's shape is a join on its identifier. No lookup service, no API
key.

Institutions have no location of their own. They belong to a place, so the
map shows them as counts on the place's shape and as a list when the user
reaches a municipality, not as pins.

## Preparing the boundaries, once

A script in `tools/` downloads the three shapefiles, keeps Ontario, simplifies
the geometry with mapshaper (the raw files are tens of megabytes; a few
hundred kilobytes per level is enough on screen), and writes one TopoJSON
file per level with the code as each feature's id. The files are static:
they go in `apps/web/public/boundaries/` or in the object store, and are
loaded by the web app directly, never through the API.

The script then checks coverage: every place at a level must have exactly
one feature and every feature one place. Expect a handful of gaps to settle
by hand:

- The loader's overrides, about twenty places, may carry codes that differ
  from the census file.
- Territorial districts are regions without a government; they have shapes
  and should show, just unshaded.
- Separated municipalities sit inside a county's shape but not under it in
  the hierarchy. The shape is right; the drill-down follows the hierarchy.
- Unorganized areas and reserves have census shapes but are not places. They
  render as empty land.

Other provinces are empty until their places are loaded. Other countries
need their own boundary source, which the identifier scheme already leaves
room for (`fips`, `nces`).

## Server

One endpoint, `GET /places/{place_id}/children/summary`, that returns each
child place with the numbers the map shades by:

```json
[{ "id": "…", "name": "…", "code": "3510010", "population": 132000,
   "institutions": 14, "verified_institutions": 11, "sources": 37 }]
```

Four aggregate queries over the existing tables. The graph view's endpoint
(`graph-view.md`) can share the service. Nothing else changes on the server.

## Web

Two ways to draw it:

- **D3-geo on SVG or canvas.** No tiles, no basemap, no key: just the
  shapes, projected and shaded, over the console's background. It looks
  clean, matches the theme in both modes, and the whole thing is a few
  hundred lines. The right choice for a console.
- **MapLibre GL** with the shapes as a vector layer over a free tile source
  (OpenFreeMap, Protomaps). Gives roads and labels behind the shapes, at the
  cost of a tile dependency and a heavier bundle. Worth it only if the demo
  needs recognizable geography.

Start with D3-geo. The feature lives in `features/map` with a route at
`(console)/map`, and a link from each place page that opens the map at that
place.

What the view does:

- **A level at a time.** The map shows the children of the current place.
  Breadcrumbs above it show the path from the country down.
- **Shading** by one measure chosen from a toggle: institutions found,
  verified share, sources found, population. The scale reads its colors from
  the theme tokens.
- **Hover** shows a tooltip with the place's name and numbers.
- **Click** zooms to the shape's bounds and loads the next level. At a
  municipality, or any place with no children, the side panel lists its
  institutions through the existing institutions table with `place_id` fixed,
  which already admits every place under it.
- **Search** reuses the entity combobox and flies to the place.
- **URL state** holds the place and the measure so a view can be shared.

## Steps

1. The boundary script, the three TopoJSON files and the coverage check,
   fixed until it reports no gaps for Ontario.
2. The summary endpoint, its schema and a test on a small fixture.
3. Regenerate the API client.
4. The route and the map: project, draw, shade, zoom to a clicked shape.
5. Breadcrumbs, the measure toggle, the tooltip, the side panel.
6. Search, URL state and the link from the place page.

## Risks

- **Join gaps.** Found by the coverage check on day one, not in the demo.
- **File size.** Simplify hard; the municipality file is the big one.
  Load each level only when first needed.
- **A flat country.** Only Ontario has places, so the country level shows
  one shaded province and twelve empty ones. Start the demo at Ontario.
- **No pins.** Institutions have no points, and adding them means another
  data source per country. The counts and the list are the honest version.
