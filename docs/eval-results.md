# Eval results

The numbers of each full eval run (spec section 10), newest first. The rows themselves are in
`eval_runs` and `eval_scores`; the eval database holds the graph each run built until the next
run resets it.

Since 2026-10-09 the dataset is ten municipalities (the two ministry subjects of run 1 are
gone: zero by design until the agency directory is loaded) and `eval run` works a quick set of
five of them plus the places file by default, `--all` for every subject. Files are parsed
lazily since the same date, one range of pages at a time as the agent reads; the parse job logs
the seconds each range took, so the next run can put a number on the parse worker per subject.

## Run 1: 2026-10-07, the twelve subjects

Dataset `b5a0696d5d64`, model `gpt-6-luna`, eval run `01a1141b-4d75-7043-8e7a-19263a57d60e`.
Twelve subject files and the Ontario places file with its 435 other governments held. 222
assignments in 6 h 45 min: two agents at a time for the first four hours, then five.
The 110 `find_homepage` the province-wide discovery spawned for universities, colleges and
school boards were cancelled by hand as outside every file.

| Measure | Recall | Precision | Gate |
| --- | --- | --- | --- |
| `find_institutions` on the subject files | 81% (120/149), parent links 53/66 | 66% | 95%: fail |
| `find_homepage`, homepages on the list file | 96% (23/24) | 100% | 99%: fail |
| `find_sources`, the four gated types on the subject files | 59% (150/255) | 81% | 90%: fail |

Cost $6.78: $6.18 of model time, $0.60 for 120 Brave searches. By subject (every assignment
spawned from the subject's own): Toronto $2.00, Greater Sudbury $0.78, Ottawa $0.74, Oakville
$0.50, Kitchener $0.47, Kingston $0.42, Simcoe $0.40, McGarry $0.38, Hawkesbury $0.28, the
province $0.14, Ministry of Transportation $0.12, Waterloo $0.11, Ministry of Public and
Business Service Delivery and Procurement $0.07.

Recall per subject (institutions / homepages / sources): Simcoe 100/75/88, Greater Sudbury
100/47/63, Hawkesbury 100/60/74, Kingston 72/21/34, Kitchener 67/46/56, McGarry 100/50/100,
Oakville 77/30/45, Ottawa 100/54/61, Waterloo 54/50/54, Toronto 100/79/68, both ministries 0/0
and 29 and 9 on sources.

The misses, explained:

- **Both ministries at zero on institutions, and so on homepages.** No assignment looked under a ministry: `find_institutions` takes a place, and the province-wide discovery the harness queued for each ministry subject filled its budget with universities, colleges and school boards. Decided after this run: a ministry's agencies are an official list's to load (`ontario_agencies`, a Phase 7 item), not the agent's to find. The harness now queues only a ministry's `find_sources`, and the agencies stay misses with this reason until the list is loaded.
- **Sources found unevenly** (34% in Kingston to 100% in McGarry): the misses cluster in tenders, board meetings and capital plans, and 38 bodies ended with no summary, mostly spawned `find_sources` on bodies whose homepage was verified late in the run.
- **Discovery over-saves**: 61 bodies saved out of scope, 27 of them in Toronto, whose discovery also ran out of budget (82 requests, two sessions).
- **The `find_homepage` total of 48%** counts the 435 held governments as undecided on the list file's domain measure; on the 24 homepages it judged it got 23.
- **Parsing** cost the parse worker twenty minutes per long PDF the agent opened once (a 395-page budget, a 311-page strategy); 9 of 18 PDFs were pruned before their parse finished. See the Phase 7 todo items.
