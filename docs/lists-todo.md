# Public Atlas: more lists, more countries

The work that follows from `lists-research.md`: the United States as a country, the rest of
Canada's places and governments, and more official lists for Ontario, in eight coding
sessions. Each session ends with what says it is done, and items marked *if time remains*
are the tail an agent takes only when the rest of its session is finished and tested. Every
URL, column name and exception is spelled out in `lists-research.md`; read the matching
section before starting. The sessions run in order, 1 to 8, each from the previous one's
committed state.

Conventions every list follows:

- One module per list under `imports/lists/<country>/<region>/<list>.py` (national lists sit
  at `<country>/<list>.py`), with `COUNTRY`, `SOURCES`, `OVERRIDES` and `entries()`. A list's
  name is its path under `lists/`, so `canada/ontario/places`; the registry discovers modules
  by walking the package, nothing is registered by hand. Shared readers live beside the
  modules that use them (`canada/statcan.py`, `us/census.py`). A rule test mirrors the path
  under `tests/unit/imports/lists/` and calls `entries()` on the cached files and pins the
  counts. The loader does not change
  for a list; when a session says it must, that is the session's first step.
- Every source declares how it is obtained: `fetched` (the URL is the file and the loader
  downloads it, hash pinned) or `manual` (a person obtains the file by the steps the module
  spells out and drops it in the loader's cache; no hash pinned). Session 1 adds the
  distinction; the manual sources are listed at the end. No source file is ever committed to
  the repository: a fresh clone plus the fetched URLs plus the manual steps rebuilds the
  database.
- Government names are composed from the list's designator and the place name in the
  country's naming rules; a legal name the directory gives wins over a composed one.
- A body nothing in the seed fits is loaded as `other` with the reason in the module's
  docstring, never dropped silently.
- Every load is run against the live database with the diff read before `--apply`, and a
  rerun changes nothing.

## Session 1: groundwork

- [x] **Lists package layout.** `imports/lists/` becomes a package tree by country and
      region: `ontario_places.py` moves to `lists/canada/ontario/places.py` and its test to
      `tests/unit/imports/lists/canada/ontario/test_places.py`. `LISTS` in `lists/__init__.py`
      is built by walking the package (`pkgutil.walk_packages`) for modules that define
      `entries`, keyed by the module's path under `lists/` with slashes
      (`canada/ontario/places`); `module_name()` in `imports/service.py` returns that path
      instead of the last dotted segment, since `canada/ontario/places` and
      `canada/quebec/places` would otherwise collide. The CLI's `load-list` choices and the
      evals' `DEFAULT_LISTS` follow. The stored `official_lists.name` keeps the form
      `<list>/<source>`, so the migration also renames Ontario's existing rows from
      `ontario_places/…` to `canada/ontario/places/…` (the loader looks lists up by this
      prefix; a rerun after the rename must change nothing).
- [x] **Shared census readers.** Move `_read_population`, `_read_types`, `Counted`, the
      DGUID pattern and the two StatCan `Source` objects out of `canada/ontario/places.py`
      into `imports/lists/canada/statcan.py`, parameterized by province code (the DGUID regex and the
      attribute file's `PRUID_PRIDU` filter are the only two places `35` is hard-coded). Add
      the 2021 CD and CSD type tables from the research (code, English name, provinces) as
      data in that module, with the municipal, upper-tier, census-only and dropped sets per
      province. `canada/ontario/places.py` imports from it and its test passes unchanged.
- [x] **Schema.** `IdentifierScheme` gains `fips`, `gnis`, `census_gid`, `nces`, `ipeds`;
      one migration for the check constraint.
- [x] **Types.** `shared.py` gains the global type `park_district` ("an independent district
      that runs parks, recreation facilities or forest preserves", default sources
      procurement, tender, budget, board_meeting) and widens `department` to "a department of
      the national or state government".
- [x] **Manual sources.** Rename the `Source` dataclass in `imports/files.py` to `ListFile`
      (it is a file a list module reads, not the graph's `Source` entity, which is a web page
      carrying a procurement signal). It gains `retrieval: Retrieval` with two values,
      `fetched` and `manual`, and for manual files `instructions: str` (the exact steps: the
      page, the tab, the object, the menu item, the expected row count) and `min_rows: int`.
      A fetched file keeps `sha256` and behaves as today. A manual file has no `sha256`: its
      cache name is `<source name><suffix>` alone, `fetch()` never downloads it and, when the
      file is not in the cache, raises with the instructions and the expected path; the
      loader records the hash of whatever file it was given in `official_lists` as it does
      now, and `_table` fails when the file has fewer than `min_rows` rows (the columns check
      already covers the shape). `official_lists` gains a `retrieval` checked-string column
      copied from the file, so the database can say which rows rest on hand-collected files;
      same migration as the schemes. The loader logs every override whose key matched
      nothing, for both kinds, since a new export or a bumped hash can strand one. Add a
      `lists manifest` command that imports every list module and prints two sections, the
      fetched URLs with their hashes and the manual steps: the from-scratch checklist, so it
      cannot drift from the code. The "Sources to fetch by hand" section below becomes the
      first manual `instructions` strings.
- [x] **Canada anchors.** The Canada seed gains Canada's government ("Government of Canada",
      `canada.ca`, `gc.ca`) and an anchor for each of the twelve other provinces and
      territories with its government's name and domains (research section 2.3). `seed
      canada` on the live database adds them and changes nothing else.

**Done when** `vp run check` and `vp run test` pass, the Ontario rule test is unchanged
apart from its path, `load-list canada/ontario/places` reruns against the live database
with no changes after the rename, the countries API and `eval validate` accept the new
type, `lists manifest` prints Ontario's three fetched sources, a manual file missing from the cache fails with its instructions,
and `seed canada` is idempotent with the thirteen provincial anchors in place.

## Session 2: Ontario's provincial bodies

Three tabular lists of the same shape. The first replaces the planned PAS scrape in
`todo.md` Phase 7; update that item to point here.

- [x] **`canada/ontario/agencies`** from the Treasury Board's *List of provincial agencies* XLSX
      (137 rows, header on row 3; add a header-row option to the spreadsheet reader if it
      has none). `crown_corporation` for classification "Operational Enterprise", `agency`
      for the rest; parent = the ministry in the `Ministry` column, created under Ontario as
      a `ministry` when missing (compose "Ministry of ..."); website from `Website`, cleaned.
- [x] **`canada/ontario/fippa_bodies`**: hospitals (144), colleges (24) and universities (22) from
      the FIPPA/MFIPPA Directory of Institutions CSV, each with its website, attached to the
      municipality in `City`. Strip the HTML in cells; "not available" is null. Cross-check
      the universities and colleges against the two ontario.ca pages (drop Royal Military
      College) and pin both counts.
- [x] **`canada/ontario/school_boards`** from the monthly contact CSV (85 rows, ISO-8859-1; note
      the CKAN resource id because the filename changes monthly). 72 district school boards
      and 13 school authorities as `school_board`, the authority kind as an alias. Dedupe
      Grandview; skip "Provincial and Demonstration Schools". Attach by `City`.

The session changed the loader three times, each before the list that needed it: `ListFile`
gained `header_row` (the rows above it stay in the text, so a line number is still the
file's row number); `InstitutionEntry` gained `place_level` and `place_parent`, so a list
that attaches bodies by city can say it means the City of Thunder Bay and not the district,
and the City of Hamilton under Ontario and not the township in Northumberland; and the
loader matches an institution at a place by its whole name and aliases, not by the forms a
place's name takes inside a government's name, which read "Centennial College of Applied
Arts and Technology" as "Applied Arts and Technology" and merged every college so named at
one place. The lists that attach by city share `canada/ontario/communities.py`, the map from
a post-office community to its municipality. The ontario.ca pages are not sources: each
fetch carries a new bot-detection token, so no hash can be pinned; the cross-check is a hand
table in the module, and the three universities the page lists and the directory does not
(NOSM University, Université de Hearst, Université de l'Ontario français) wait for a list
that names them.

**Done when** the three loads are applied, each rule test pins its counts, and the agencies
sit under their ministries.

## Session 3: Ontario's local bodies

- [x] **`canada/ontario/libraries`** from the 2025 library statistics XLSX (sheet `OpenData`, 355
      rows): the board types (Public or Union, County/co-op/Regional, First Nations, LSB;
      about 290) as `library`, name composed as "X Public Library" with the file's
      abbreviated name as an alias, website from `A1.13`, attached by `A1.10 City/Town` or
      by matching the name to a municipality. Contracting municipalities and LSBs are not
      institutions.
- [x] **`canada/ontario/service_managers`** from the *List of service managers* CSV (425 rows,
      anchor cells like the municipal directory's): the 10 DSSABs as `municipal_corporation`
      under their territorial district, with `served_places` = their municipality rows and
      the housing-page URL as the candidate homepage. The 37 municipal service managers are
      existing governments; load nothing new for them.
- [x] **`canada/ontario/health_units`** from the ontario.ca "Public health unit locations" page
      (HTML, 29): brand name as the name, the Reg. 553 legal name and served municipalities
      from a hand-written table in `OVERRIDES`, parent = the council where the unit is a
      municipal department (Toronto, Ottawa, Hamilton, Durham, Halton, Peel, York, Waterloo,
      Niagara, Lambton, Chatham-Kent), websites from the page with schemes added.
- [x] **`canada/ontario/conservation_authorities`** from the GeoHub REST layer
      (`LIO_Open03/MapServer/11`, 36 rows, `returnGeometry=false`, JSON): `LEGAL_NAME` as
      the name, `COMMON_NAME` as an alias, HQ municipality from the FIPPA directory's 36
      rows as a second source. No websites.
- [ ] *If time remains:* **`canada/ontario/electricity_distributors`** from the OEB
      licensed-companies HTML table (60 "Electricity Distributor" rows) as `public_utility`,
      with an exclusion list for the ones no municipality owns (Hydro One Networks and
      Remote Communities, Algoma Power, Canadian Niagara Power, Cornwall Street Railway
      Light and Power, EPCOR, the First Nation power corporations, Cooperative Hydro Embrun)
      and a hand-written HQ municipality each.

The session changed the loader once, for served places, and found two things about the
sources:

- The health unit page is a `manual` file: like the university pages of Session 2, every
  response from ontario.ca carries a new bot-detection token, so no hash can be pinned. The
  module's instructions say how to save the page; the saved copy sits in the loader's cache
  as `public_health_unit_locations_2026_08.html`.
- The conservation authority layer is read in the service's HTML rendering (`f=html`), not
  its JSON: the loader renders a JSON object as one line, and an ArcGIS response is one
  object holding the records, so every authority would have cited the whole file. The HTML
  rendering is the same query's records as a page, one line per field, so each authority
  cites the line that names it. A `records` key on `ListFile` (the path to the array inside
  a JSON object, as `member` names a file inside a ZIP) would let the JSON form be used.
- **A served place says which place it means.** `InstitutionEntry.served_places` was a tuple
  of names, and the loader found each by name at any level, so a name two places go by was
  refused: Cochrane, Kenora, Parry Sound, Rainy River and Thunder Bay are a town or city and
  its district, Peterborough, Perth, Renfrew, Essex and Waterloo a county or region and a
  separated or lower-tier municipality, and Hamilton two municipalities. The first dry runs
  skipped 5 of the 10 DSSABs and 10 of the 29 health units for it. Now `served_places` is a
  tuple of `ServedPlace` (name, level, parent, the last two optional), and
  `Loader._served_place` passes the level and parent to `_find_place` as the entry's own
  place goes through it. The DSSABs' members are all municipalities; the health units' table
  gives each served place its level and parent, and both tests pin the namesake sets.
- The lists that attach by city share `communities.py` as before; nine post-office
  communities joined it (Downsview, Manotick, Glenburnie, Utopia, Finch, Wroxeter, Lanark,
  Trenton, Marmora). A First Nation's library sits at the county or district its reserve lies
  in, since a reserve is not under a municipality; the rows are a hand table in the module.
- The agent had already saved Conservation Halton at Halton and the Halton Region Public
  Health Department at Halton in the live database; the lists place the authority at
  Burlington (its head office) and name the health unit otherwise, so the loader did not
  match them. The reviewer merges those two pairs.

**Done when** libraries, DSSABs, health units and conservation authorities are loaded with
their served places where the list gives them, and every rule test pins its counts.

## Session 4: the United States seed and its places

- [x] **The seed, `countries/seeds/united_states.py`**: naming rules (designator groups,
      connectors "of", "and", "/", leading "The"); four levels (country, state, county,
      municipality) with government types and expected types (`school_board`,
      `fire_service`, `public_utility`, `transit_agency`, `library`, `hospital`,
      `park_district`, `municipal_corporation` on both county and municipality); the types
      the US uses; the platforms (research section 1.7); anchors for the country, the fifty
      states, DC and Puerto Rico with each government's name and main domains, checked
      against the `.gov` registry's "State or territory" rows. `seed united_states` works.
- [x] **`us/states_counties`**: states (SUMLEV 040) and county equivalents (SUMLEV 050,
      FUNCSTAT A, B, C) from SUB-EST2025, CLASSFP and GNIS ids from `national_county2020.txt`
      (map Connecticut's old county codes; planning regions are dropped as FUNCSTAT N).
      Codes in `fips`, population 2025. Honolulu promoted to a municipal government, Kalawao
      dropped, DC's county row suppressed. Puerto Rico's 78 municipios from the Gazetteer
      county file plus the PRM-EST2025 xlsx, as both county and municipal government.
- [x] **`us/municipalities`**: incorporated places (SUMLEV 162, FUNCSTAT A) and towns and
      townships (SUMLEV 061, FUNCSTAT A, B, C) from SUB-EST2025, CLASSFP from the 2020 place
      and cousub files, parent county from the SUMLEV 157 row with `PRIMGEO_FLAG` = 1, legal
      name composed from the census suffix ("X city" → "City of X"). The exception classes
      of research section 1.3 as rules and `OVERRIDES`: independent cities (one place, the
      county code as a second identifier), both consolidated-city patterns, coextensive
      place/MCD rows (drop C5/C2, merge T5), "(balance)" rows, DC. The rule test pins the
      count per class.

The session changed the loader three times (a fourth time after the first dry run) and
found these things about the sources and the plan:

- **A CSV names its delimiter.** The 2020 ANSI code files and the Gazetteer are
  pipe-delimited, so `ListFile` gained `delimiter` (default `,`).
- **A place's parent says which place it means.** `_find_place` looked a parent up by name at
  every level above, so "Washington County" met the state of Washington and twenty-eight other
  counties and the entry was skipped. `PlaceEntry` gained `parent_level` and `parent_parent`,
  as `InstitutionEntry.place_level` and `place_parent` did in session 2; the municipalities
  list names a county parent with its state, and a state parent by its level.
- **A town and the village inside it are two places.** The loader matched a new place by name
  at its level under its parent, so the second of "Hamburg town" and "Hamburg village" in Erie
  County would have been merged into the first and given its code; 2,269 such pairs sit under
  one county. `Known` now carries the government's name, and a place whose government is a
  body of another kind by the designators around the place's name is not the same place. The
  first dry run showed why the name must be taken out before the designators are compared:
  "City of Bird City" and "Township of Bird City" both say "City", and 19 such pairs (Garden
  City, Peoria City, Parish...) had merged. Then the list's own name is compared as written
  (`Naming.plain_forms`): "Galesburg City" is no form of "Galesburg", though "Galesburg" is one
  of "Galesburg Township", so the seven pairs of one kind whose longer name ends in a
  designator word (the Galesburg and Galesburg City townships of Knox County, Chevy Chase and
  Chevy Chase Village) stay two places. That reads the second against the first, which holds
  because the loader orders a level's places by name; the rule test replays the loader's
  order over every pair of siblings and pins that none would merge.
- **`PRIMGEO_FLAG` is not a primary-county flag.** The layout calls it the primitive geography
  flag: a place in two counties is flagged in both or in neither, and 7,836 places in one county
  are flagged in neither. The parent is the county part holding most of the place's population
  (`Estimates.main_county`); no place ties.
- **The consolidated cities are their own rows.** SUMLEV 170 rows (8) carry the government;
  their "(balance)" rows are F and dropped by status. A county consolidated with its city
  (FUNCSTAT C, 33) is loaded as a place with no government, as Ontario's territorial districts
  are, and the municipality inside it carries the government; the places still incorporated
  beside it (Jacksonville Beach, the eighty small cities of Jefferson County, Kentucky: 151 in
  all) sit under the county. Terrebonne Parish (H6, A) keeps its government: Houma's city row
  is N. CLASSFP C6 does not mark a consolidated city-county: it is a place partly independent
  of county subdivisions (Columbus, Ohio); the pattern 2b cities are found by their county's
  status.
- **Merging a T5 row is a drop.** Each of the 29 FUNCSTAT C subdivisions is covered to the
  person by the places inside it (the 071 rows), so the subdivision row is not loaded and the
  place is the government; the module refuses a C row no place covers. The five Ohio ones are
  townships absorbed by a city of another name (Washington township by Dublin).
- **Honolulu and the municipios are municipality-level places.** A government's type comes
  from its place's level, so "promoted to a municipal government" means loaded at the
  municipality level under the state with the county code as its `fips`. The same for the 78
  municipios under Puerto Rico ("Municipality of Adjuntas", "Municipio de Adjuntas" as a
  Spanish alias). Puerto Rico's own code and population come from the PRM-EST2025 sheet's
  "Puerto Rico" row, since SUB-EST2025 leaves the island out.
- **One code per scheme.** An identifier is one per owner and scheme, so an independent city
  keeps its place code (5101000 for Alexandria) and its county code (51510) is dropped, and the
  GNIS ids the 2020 files carry are read for nothing and not stored. A `codes` tuple on
  `PlaceEntry` would carry both; left for the session that needs it.
- **"and" is not a connector** in the US naming rules: the connector pattern would read
  "Juneau city and borough" as a kind before "borough". The designator groups carry "City and
  County" and "City and Borough" in both spellings ("City & County"), since a name's key reads
  "and" as "&" and a designator is looked for in both forms.
- Against the live database: `seed united_states` added the country's tables, 32 platforms and
  the 53 anchors with their 91 domains (the five platforms Canada shares were there); the
  states and counties load added 3,145 places, 3,112 governments and 3,197 codes and figures in
  82 seconds, and the municipalities load its 35,643 places and governments in 15 minutes (the
  rerun, matching every entry by code, takes 5); each rerun changed nothing. The United States
  now holds 38,841 verified places, every one with a `fips` code and a 2025 population, and
  38,808 verified governments: the 33 counties consolidated with their city have none.

**Done when** `seed united_states` and the two loads give every state, every active county
equivalent and every active municipality a verified place with a `fips` code and population,
and the exception counts are pinned.

## Session 5: US legal names, websites and the independent districts

All three read the Census of Governments *Government Units* workbook or NCES, so they share
one parsing pass.

- [ ] **`us/government_units`**: the General Purpose sheet (38,736 rows) matched to the
      places of session 4 (counties and municipalities by `FIPS_STATE` + `FIPS_PLACE`,
      townships by state + county + normalized name): legal `UNIT_NAME` as the government's
      name or alias, `CENSUS_ID_GIDID` as a `census_gid` identifier, `WEB_ADDRESS` as the
      candidate homepage. Then the `.gov` registry (`current-full.csv`) as a third source: a
      domain whose organization matches a loaded government by normalized name + state
      becomes its candidate homepage when it has none. Check first that a `PlaceEntry` for
      an existing place only adds the name, identifier and homepage; if the legal name must
      not replace the composed one, add a `government_aliases` field to the entry (the one
      loader change this plan allows).
- [ ] **`us/school_districts`**: the NCES CCD LEA directory 2023-24 (19,637 rows) as
      `school_board` with `LEAID` in `nces`; `LEA_TYPE` 1 and 2 as boards, 7 (charter
      districts) kept with a marking alias, 4 (service agencies) as `other`; website from
      `WEBSITE`; place = the county of the location address, the city as a served place
      where it matches a loaded municipality.
- [ ] **`us/special_districts`**: the Special District sheet (39,555 rows) typed by
      `FUNCTION_NAME`: fire → `fire_service`; water supply, sewerage, electric, gas, solid
      waste → `public_utility`; transit → `transit_agency`; libraries → `library`; hospitals
      → `hospital`; parks and recreation, natural resources → `park_district`; housing,
      airports, ports, parking, industrial development → `municipal_corporation`; the rest
      → `other` with the function as the suggested type. Place = county; website from
      `WEB_ADDRESS`; `census_gid` identifier.

**Done when** the three loads are applied, the share of governments with a candidate
homepage is reported per level, and school and special districts are counted per type.

## Session 6: US federal, campuses, transit and an eval

- [ ] **`us/federal`**: the Federal Register agencies API JSON (473) as `department` for
      the cabinet departments and `agency` for the rest, parent from `parent_id`, website
      from `agency_url`, filtered to agencies with recent documents; the registry's
      `current-federal.csv` pre-trusts the federal domains that match.
- [ ] **`us/universities`**: IPEDS HD2024 (`CONTROL` 1; `ICLEVEL` 1 → `university`, 2 →
      `college`; website from `WEBADDR`; place by `FIPS` county).
- [ ] **`us/transit`**: the FTA NTD 2024 agency file, public organization types only,
      website from `URL`, place by city and state.
- [ ] **US eval subjects**: three hand-labelled subjects (a mid-size city in an MCD state, a
      county, a school district) and whatever the harness and validator need to run against
      a second country (they read the Canada seed by name today). Score `find_homepage` and
      `find_sources` on them once.

**Done when** the three loads are applied and one eval run over the three US subjects has
scores in the database.

## Session 7: Canada's federal institutions and Quebec

- [ ] **`canada/federal`**: the TBS *Inventory of Federal Organizations and Interests* CSV
      (277 active rows): ministerial departments as `department`; departmental, service and
      special operating agencies and departmental corporations as `agency`; Crown
      corporations as `crown_corporation`; shared-governance corporations, international
      organizations and parliamentary entities as `other`. Parent = the portfolio's
      department (`min_port`), place = Canada, `legal_title` as the name with
      `applied_title` and `abbr_en` as aliases, website from `website`.
- [ ] **`canada/quebec/places`**: MRCs as regions from `MRC_CM_Arg.csv` (87 with websites; the
      two communautés métropolitaines and Kativik as `regional_government` institutions with
      `served_places`, not places); municipalities from the census joined to `MUN.csv` by
      `mcode` (the last five digits of the SGC code), parent MRC from the `mrc` column (not
      the census division: 5 CDR and 12 TÉ divisions), legal name composed from `mdes` with
      French elision, website from `mweb`, `mpopul` as a second population year. Overrides
      for the renames and mergers since 2021. The file updates daily, so the operator
      re-pins the hash at load time; say so in the docstring.

**Done when** both loads are applied, Quebec has its 87 MRCs and about 1,120 municipalities
with codes, and the federal bodies sit under their portfolio departments.

## Session 8: the other provinces and territories

All from the shared census readers plus the thinnest directory that gives legal names. One
module per province; the three territories share one. Websites only where the directory
has them; `find_homepage` does the rest.

- [ ] **`canada/manitoba/places`**: the Municipal Officials Directory PDF (137 entries with
      websites, parsed by Docling; pin the entry count).
- [ ] **`canada/nova_scotia/places`**: the GeoNOVA Socrata JSON (49 rows, `$select` without
      geometry) for legal names; the 9 county municipalities built from their `SC` parts
      with the division's code and summed population; towns under the province; the
      designator rule for the four CD/CSD name collisions.
- [ ] **`canada/new_brunswick/places`**: the GNB local-government contacts PDF (77 rows with
      websites) and StatCan's 2024 interim list of changes CSV for the post-reform CSD codes
      and names; no population; rural districts not loaded.
- [ ] **`canada/british_columbia/places`**: regional districts as regions; legal names and parent
      RD from the BC Data Catalogue WFS JSON (160 municipalities, 28 RDs).
- [ ] **`canada/alberta/places`**: the 2026 municipal codes PDF for types and the CRA list's legal
      forms; websites from the manual Local Authority Contact Information export (427 rows,
      columns Name, Type, Website; join on name, the 77 regional services commissions and
      the Métis settlements skipped or loaded as `other`); improvement districts and special
      areas loaded with a note.
- [ ] **`canada/saskatchewan/places`**, **`canada/newfoundland/places`**, **`canada/pei/places`**,
      **`canada/territories/places`**: census-driven with composed names (the NL towns directory
      PDF, the hand-fetched PEI directory and the MACA pages add what they have). Lloydminster
      and Flin Flon as one place each.
- [ ] *If time remains:* **`canada/ontario/police_boards`**: the 45 municipal police service
      boards and 88 OPP detachment boards from their PAS agency pages (one HTML source per
      page) as `police_service` with member municipalities as `served_places`.

**Done when** every province and territory has its municipalities loaded with codes and
population (NB excepted) and a rerun of every list changes nothing.

## Sources to fetch by hand

These sites block scripts or only offer an interactive export. Each becomes a `manual` list
file (Session 1): the module records the page's URL and these steps as its `instructions`,
and the file goes in the loader's cache under `<source name><suffix>`. The steps are written
so that someone rebuilding from a fresh clone gets the same file.

- Alberta, done 2026-10-09: open the "Find a municipal official" dashboard
  (visualizations.alberta.ca, report `41a37e88-38b3-4c10-b685-50ee51675369`), tab "Contact
  Info for Official and Organization", object "Local Authority Contact Information", its
  vertical-ellipsis menu, "Export data", all rows, Excel. The file is
  `temp-manual-files/Alberta/alberta-local-authority-contacts-2026-10-09.xlsx` (sheet
  "Results", 427 rows, columns Name, Type, Website, Email, Phone, Address, Address (line 2),
  Municipality, Postal Code, Frequency). The province refreshes the table weekly, so a
  re-export differs; that is why manual files pin no hash.

- Prince Edward Island, done 2026-10-09: the Municipal Directory on princeedwardisland.ca
  is a single-page app with no export; each of the 57 results of a blank search was opened
  and its detail view saved. The loader's file is the derived
  `temp-manual-files/Prince Edward Island/pei_municipalities.csv` (57 rows; columns include
  Municipality Name, Municipality Type, Population, Website, source_url); the 57 HTML
  snapshots and `evidence_log.csv` beside it are the proof, kept outside the repository.
- Yukon, done 2026-10-09: `temp-manual-files/Yukon/cs-local-government-directory-2026-06-16_.pdf`
  from yukon.ca, text-based (Docling reads it).
- Nunavut, done 2026-10-09: the 25 community pages under gov.nu.ca/en/communities saved as
  `temp-manual-files/Nunavut/nunavut-community-<slug>.html`, with `nunavut_communities_
  evidence.csv` as the index (URL, capture time, sha256 per page). About 13 of the 25 link a
  hamlet website; the module either declares the 25 pages as HTML files or reads one small
  derived CSV of community and website built from them.
- Saskatchewan, done 2026-10-09: the Municipal Directory on saskatchewan.ca has no export;
  all 761 municipality pages were saved (`temp-manual-files/Saskatchewan/
  sk_municipal_directory_2026-10-09/raw_html/`). The loader's file is the derived
  `data/municipalities.csv` in that folder (761 rows; name, municipality_type, website for
  296, rm_number, source_url, page_sha256); `evidence/evidence.csv` ties every value to its
  page.
- Ontario, done 2026-10-09: Reg. 553 and O. Reg. 135/24 saved from e-Laws as text PDFs in
  `temp-manual-files/Ontario/`; they feed the hand-written tables for health units and
  police boards, not a source. The "Public Health Unit locations" page
  (ontario.ca/page/public-health-unit-locations, updated 2026-08-28, 29 units) is a manual
  file of `canada/ontario/health_units`: fetched once with a browser user agent and put in
  the loader's cache as `public_health_unit_locations_2026_08.html`, since every response
  carries a new bot-detection token.

Two of these (PEI, Saskatchewan) are derived CSVs built from saved pages rather than files
the site served. Their `instructions` say so and point at the raw captures; the loader's
provenance for them is the derived file's hash plus the per-row `source_url` and
`page_sha256` columns. `temp-manual-files/` is a staging folder: the session that writes a
module copies its file into the loader's cache under the module's name, and the folder is
deleted once every file has moved. Until then it stays out of commits.
