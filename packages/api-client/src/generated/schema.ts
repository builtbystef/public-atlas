export interface paths {
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Health
         * @description Liveness: the process is up.
         */
        get: operations["health-read_health"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/db": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Health Db
         * @description Readiness: the database answers.
         */
        get: operations["health-read_health_db"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/storage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Health Storage
         * @description Readiness: the object store answers and the bucket exists.
         */
        get: operations["health-read_health_storage"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/countries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Countries */
        get: operations["countries-list_countries"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/countries/{country_code}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Country
         * @description The country's settings, its administrative levels and how it uses each type.
         */
        get: operations["countries-read_country"];
        /**
         * Put Country Settings
         * @description Create the country or change its name and naming rules.
         */
        put: operations["countries-put_country_settings"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/countries/{country_code}/administrative-levels/{name}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Put Administrative Level
         * @description Create or change a level. Its types must be ones the country uses. Open review items the
         *     change answers (a type now expected at the level) are settled.
         */
        put: operations["countries-put_administrative_level"];
        post?: never;
        /**
         * Delete Administrative Level
         * @description Refused while a place sits at the level.
         */
        delete: operations["countries-delete_administrative_level"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/countries/{country_code}/institution-types/{institution_type}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Put Country Institution Type
         * @description How the country uses a type: the sources expected for it and what its names look like.
         *     Open review items the change answers (bodies saved as `other` with this type suggested) are
         *     settled.
         */
        put: operations["countries-put_country_institution_type"];
        post?: never;
        /**
         * Delete Country Institution Type
         * @description Refused while one of the country's levels expects the type.
         */
        delete: operations["countries-delete_country_institution_type"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/institution-types": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Institution Types
         * @description Global: one `hospital` for every country.
         */
        get: operations["countries-list_institution_types"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/institution-types/{name}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Put Institution Type
         * @description Create or change a type; a body with another name renames it everywhere.
         */
        put: operations["countries-put_institution_type"];
        post?: never;
        /**
         * Delete Institution Type
         * @description Refused while anything refers to the type.
         */
        delete: operations["countries-delete_institution_type"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/source-types": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Source Types */
        get: operations["countries-list_source_types"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/source-types/{name}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Put Source Type
         * @description Create or change a source type; a body with another name renames it everywhere.
         */
        put: operations["countries-put_source_type"];
        post?: never;
        /**
         * Delete Source Type
         * @description Refused while anything refers to the type.
         */
        delete: operations["countries-delete_source_type"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/institutions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Institutions
         * @description A page of institutions. `q` matches a name or an alias; `place_id` admits the place and
         *     every place under it; the population bounds are on the institution's own place.
         */
        get: operations["graph-list_institutions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/institutions/{institution_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Institution
         * @description The institution with its aliases, its place and the places above, its parent and the
         *     bodies under it, every homepage claim, its sources, and every quote for any of them with a
         *     link to the stored copy it was found on.
         */
        get: operations["graph-read_institution"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/places": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Places
         * @description A page of places, by name unless sorted otherwise, each with its newest population
         *     figure; `q` matches a name or an alias.
         */
        get: operations["graph-list_places"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/places/{place_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Place
         * @description The place with its population, the places above it and its government.
         */
        get: operations["graph-read_place"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/evidence/{evidence_id}/context": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Evidence Context
         * @description The quote with the text around it on the stored copy. `found` is false when the stored
         *     text no longer has the quote: the copy was pruned, or the quote matched the page's HTML.
         */
        get: operations["evidence-read_evidence_context"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/review-items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Review Items
         * @description A page of items, open ones by default, oldest first, each with its entity's name.
         */
        get: operations["review-list_review_items"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/review-items/kinds": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Review Kinds
         * @description The open items grouped by the question they share; one call on a kind decides them all.
         */
        get: operations["review-list_review_kinds"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/review-items/kinds/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve Review Kind
         * @description Approve every open item of the kind. A `new_type` kind gives its bodies the type named,
         *     by default the suggested type as a type name; the type must exist.
         */
        post: operations["review-approve_review_kind"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/review-items/kinds/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reject Review Kind
         * @description Reject every open item of the kind.
         */
        post: operations["review-reject_review_kind"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/review-items/{review_item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Review Item
         * @description The item with its entity, the entity's names and status, and every quote for it with a
         *     link to the stored copy it was found on.
         */
        get: operations["review-read_review_item"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/review-items/{review_item_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve Review Item
         * @description The entity is what the agent said. An institution saved as `other` may be given its type.
         *     The work the approval asks for is created in the run it belongs to.
         */
        post: operations["review-approve_review_item"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/review-items/{review_item_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reject Review Item */
        post: operations["review-reject_review_item"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/review-items/{review_item_id}/merge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Merge Review Item
         * @description The entity is a duplicate of `into_id`: what it holds moves over and it is rejected.
         */
        post: operations["review-merge_review_item"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Runs
         * @description Every run, newest first, each with its progress and cost.
         */
        get: operations["runs-list_runs"];
        put?: never;
        /**
         * Create Run
         * @description Start a run: the work due for the subjects in its filter is created, held in step mode
         *     and queued in auto mode.
         */
        post: operations["runs-create_run"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Run
         * @description The run with its assignments counted by status and result, and what it has cost.
         */
        get: operations["runs-read_run"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/runs/{run_id}/pause": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Pause Run
         * @description The worker starts none of the run's assignments until it is resumed; running ones finish
         *     their session.
         */
        post: operations["runs-pause_run"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/runs/{run_id}/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resume Run */
        post: operations["runs-resume_run"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/runs/{run_id}/stop": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Stop Run
         * @description Cancel everything held or queued; running assignments finish their session.
         */
        post: operations["runs-stop_run"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/runs/{run_id}/release": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Release Assignments
         * @description Queue held assignments: a few at a time, of one type, or the ones named.
         */
        post: operations["runs-release_assignments"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/assignments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Assignments
         * @description A page of assignments by creation, oldest first unless `order` is `desc`, with their
         *     subjects named.
         */
        get: operations["runs-list_assignments"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/assignments/{assignment_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Assignment */
        get: operations["runs-read_assignment"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/assignments/{assignment_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Assignment Events
         * @description Everything the agent saw, said and did, in order: the prompt, its words, its tool calls
         *     and their results, and the videos when recorded, each with a short-lived link to play it.
         */
        get: operations["runs-read_assignment_events"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/assignments/{assignment_id}/findings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Assignment Findings
         * @description What the assignment saved: every quote it recorded, with the entity the quote is for and
         *     a link to the stored page.
         */
        get: operations["runs-read_assignment_findings"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/eval-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Eval Runs
         * @description Every eval run, newest first.
         */
        get: operations["evals-list_eval_runs"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/eval-runs/{eval_run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Eval Run
         * @description One eval run with its scores per subject and assignment type.
         */
        get: operations["evals-read_eval_run"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AdministrativeLevelInput */
        AdministrativeLevelInput: {
            /** Name */
            name: string;
            /** Rank */
            rank: number;
            /** Government Institution Type */
            government_institution_type: string;
            /**
             * Expected Institution Types
             * @default []
             */
            expected_institution_types: string[];
        };
        /** AliasOutput */
        AliasOutput: {
            /** Text */
            text: string;
            /** Language */
            language: string;
            /** Is Acronym */
            is_acronym: boolean;
            entered_by: components["schemas"]["EnteredBy"];
        };
        /** ApproveInput */
        ApproveInput: {
            /** Note */
            note?: string | null;
            /** Institution Type */
            institution_type?: string | null;
        };
        /** AssignmentDetail */
        AssignmentDetail: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Run Id
             * Format: uuid
             */
            run_id: string;
            type: components["schemas"]["AssignmentType"];
            /**
             * Subject Id
             * Format: uuid
             */
            subject_id: string;
            subject?: components["schemas"]["SubjectOutput"] | null;
            status: components["schemas"]["AssignmentStatus"];
            result: components["schemas"]["AssignmentResult"] | null;
            /** Budget Requests */
            budget_requests: number;
            /** Budget Tokens */
            budget_tokens: number;
            /** Requests Used */
            requests_used: number;
            /** Tokens Used */
            tokens_used: number;
            /** Sessions */
            sessions: number;
            /** Handoff Note */
            handoff_note: string | null;
            /** Summary */
            summary: string | null;
            /** Types Not Found */
            types_not_found: string[];
            /** Last Error */
            last_error: string | null;
            /** Parent Assignment Id */
            parent_assignment_id: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Started At */
            started_at: string | null;
            /** Finished At */
            finished_at: string | null;
            /** Cost */
            cost: string;
        };
        /** AssignmentOutput */
        AssignmentOutput: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Run Id
             * Format: uuid
             */
            run_id: string;
            type: components["schemas"]["AssignmentType"];
            /**
             * Subject Id
             * Format: uuid
             */
            subject_id: string;
            subject?: components["schemas"]["SubjectOutput"] | null;
            status: components["schemas"]["AssignmentStatus"];
            result: components["schemas"]["AssignmentResult"] | null;
            /** Budget Requests */
            budget_requests: number;
            /** Budget Tokens */
            budget_tokens: number;
            /** Requests Used */
            requests_used: number;
            /** Tokens Used */
            tokens_used: number;
            /** Sessions */
            sessions: number;
            /** Handoff Note */
            handoff_note: string | null;
            /** Summary */
            summary: string | null;
            /** Types Not Found */
            types_not_found: string[];
            /** Last Error */
            last_error: string | null;
            /** Parent Assignment Id */
            parent_assignment_id: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Started At */
            started_at: string | null;
            /** Finished At */
            finished_at: string | null;
        };
        /**
         * AssignmentResult
         * @description How a finished assignment ended.
         * @enum {string}
         */
        AssignmentResult: "complete" | "complete_with_gaps" | "out_of_budget" | "needs_review" | "no_homepage" | "failed";
        /**
         * AssignmentStatus
         * @description The lifecycle: is it still going.
         * @enum {string}
         */
        AssignmentStatus: "held" | "queued" | "running" | "finished" | "cancelled";
        /**
         * AssignmentType
         * @enum {string}
         */
        AssignmentType: "find_homepage" | "find_institutions" | "find_sources";
        /** CountryInstitutionTypeInput */
        CountryInstitutionTypeInput: {
            /** Institution Type */
            institution_type: string;
            /**
             * Expected Source Types
             * @default []
             */
            expected_source_types: string[];
            /** Name Pattern */
            name_pattern?: string | null;
        };
        /**
         * CountryOutput
         * @description One country's five tables, as the console reads them. The global type tables have routes
         *     of their own.
         */
        CountryOutput: {
            settings: components["schemas"]["CountrySettingsInput"];
            /** Administrative Levels */
            administrative_levels: components["schemas"]["AdministrativeLevelInput"][];
            /** Institution Types */
            institution_types: components["schemas"]["CountryInstitutionTypeInput"][];
        };
        /** CountrySettingsInput */
        CountrySettingsInput: {
            /** Country Code */
            country_code: string;
            /** Name */
            name: string;
            /**
             * @default {
             *       "designators": [],
             *       "connectors": [],
             *       "leading": [],
             *       "and_words": []
             *     }
             */
            naming_rules: components["schemas"]["NamingRules"];
        };
        /** DecisionInput */
        DecisionInput: {
            /** Note */
            note?: string | null;
        };
        /** DecisionOutput */
        DecisionOutput: {
            review_item: components["schemas"]["ReviewItemOutput"];
            /** Spawn */
            spawn: components["schemas"]["SpawnOutput"][];
            /**
             * Assignment Ids
             * @default []
             */
            assignment_ids: string[];
        };
        /**
         * EnteredBy
         * @description How a row got here. On every entity and every evidence row.
         * @enum {string}
         */
        EnteredBy: "manual" | "script" | "agent";
        /**
         * EntityKind
         * @enum {string}
         */
        EntityKind: "place" | "institution" | "source" | "domain" | "homepage";
        /**
         * EntityStatus
         * @enum {string}
         */
        EntityStatus: "candidate" | "verified" | "rejected" | "needs_review";
        /** EvalRunDetail */
        EvalRunDetail: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Run Id
             * Format: uuid
             */
            run_id: string;
            /** Dataset Version */
            dataset_version: string;
            /** Model */
            model: string;
            /** Settings */
            settings: {
                [key: string]: unknown;
            };
            /** Cost */
            cost: string;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Finished At */
            finished_at: string | null;
            /**
             * Summary
             * @default {}
             */
            summary: {
                [key: string]: components["schemas"]["TypeSummary"];
            };
            /** Scores */
            scores: components["schemas"]["EvalScoreOutput"][];
        };
        /** EvalRunOutput */
        EvalRunOutput: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Run Id
             * Format: uuid
             */
            run_id: string;
            /** Dataset Version */
            dataset_version: string;
            /** Model */
            model: string;
            /** Settings */
            settings: {
                [key: string]: unknown;
            };
            /** Cost */
            cost: string;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Finished At */
            finished_at: string | null;
            /**
             * Summary
             * @default {}
             */
            summary: {
                [key: string]: components["schemas"]["TypeSummary"];
            };
        };
        /** EvalScoreOutput */
        EvalScoreOutput: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Subject */
            subject: string;
            assignment_type: components["schemas"]["AssignmentType"];
            /** Recall */
            recall: number | null;
            /** Precision */
            precision: number | null;
            /** Misses */
            misses: {
                [key: string]: unknown;
            }[];
            /** False Positives */
            false_positives: {
                [key: string]: unknown;
            }[];
        };
        /**
         * EventKind
         * @enum {string}
         */
        EventKind: "prompt" | "text" | "tool_call" | "tool_result" | "video";
        /** EventOutput */
        EventOutput: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Session */
            session: number;
            /** Position */
            position: number;
            kind: components["schemas"]["EventKind"];
            /** Tool */
            tool: string | null;
            /** Content */
            content: {
                [key: string]: unknown;
            };
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Video Url */
            video_url?: string | null;
        };
        /** EvidenceOutput */
        EvidenceOutput: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Entity Id
             * Format: uuid
             */
            entity_id: string;
            /** Quote */
            quote: string;
            /** Kind */
            kind: string;
            /** Locator */
            locator: number | null;
            /** Link Url */
            link_url: string | null;
            /** Entered By */
            entered_by: string;
            /** Assignment Id */
            assignment_id: string | null;
            /** Page Url */
            page_url: string;
            /**
             * Snapshot Id
             * Format: uuid
             */
            snapshot_id: string;
            /**
             * Snapshot Url
             * @description A short-lived download link to the stored page or file; null once pruned.
             */
            snapshot_url: string | null;
        };
        /**
         * FindingOutput
         * @description One thing the assignment saved, with the quote it gave for it.
         */
        FindingOutput: {
            /**
             * Evidence Id
             * Format: uuid
             */
            evidence_id: string;
            /**
             * Entity Id
             * Format: uuid
             */
            entity_id: string;
            entity_kind: components["schemas"]["EntityKind"];
            entity_status: components["schemas"]["EntityStatus"];
            /** Label */
            label: string;
            /** Institution Id */
            institution_id: string | null;
            /** Quote */
            quote: string;
            /** Kind */
            kind: string;
            /** Page Url */
            page_url: string;
            /** Link Url */
            link_url: string | null;
            /** Snapshot Url */
            snapshot_url: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** Health */
        Health: {
            /** Status */
            status: string;
        };
        /**
         * HomepageOutput
         * @description A homepage claim: every claim an institution made, verified or not.
         */
        HomepageOutput: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Url */
            url: string;
            status: components["schemas"]["EntityStatus"];
            entered_by: components["schemas"]["EnteredBy"];
            /** Found On Url */
            found_on_url: string | null;
            /** Rejected Reason */
            rejected_reason: string | null;
            /** Trusted Path */
            trusted_path: string | null;
            /** Domain */
            domain: string | null;
            domain_status: components["schemas"]["EntityStatus"] | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** IdentifierOutput */
        IdentifierOutput: {
            /** Scheme */
            scheme: string;
            /** Value */
            value: string;
        };
        /** InstitutionDetail */
        InstitutionDetail: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Institution Type */
            institution_type: string;
            /** Suggested Type */
            suggested_type: string | null;
            status: components["schemas"]["EntityStatus"];
            entered_by: components["schemas"]["EnteredBy"];
            place: components["schemas"]["PlaceRef"];
            /** Place Population */
            place_population: number | null;
            /** Parent Institution Id */
            parent_institution_id: string | null;
            procurement_handled_by: components["schemas"]["ProcurementHandledBy"];
            /** Homepage Id */
            homepage_id: string | null;
            /** Homepage Url */
            homepage_url: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Aliases */
            aliases: components["schemas"]["AliasOutput"][];
            /** Identifiers */
            identifiers: components["schemas"]["IdentifierOutput"][];
            /** Metrics */
            metrics: components["schemas"]["MetricOutput"][];
            /** Places */
            places: components["schemas"]["PlaceRef"][];
            parent: components["schemas"]["InstitutionRef"] | null;
            /** Children */
            children: components["schemas"]["InstitutionRef"][];
            /** Served Places */
            served_places: components["schemas"]["PlaceRef"][];
            /** Homepages */
            homepages: components["schemas"]["HomepageOutput"][];
            /** Sources */
            sources: components["schemas"]["SourceOutput"][];
            /** Evidence */
            evidence: components["schemas"]["EvidenceOutput"][];
        };
        /**
         * InstitutionOutput
         * @description An institution as the table lists it.
         */
        InstitutionOutput: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Institution Type */
            institution_type: string;
            /** Suggested Type */
            suggested_type: string | null;
            status: components["schemas"]["EntityStatus"];
            entered_by: components["schemas"]["EnteredBy"];
            place: components["schemas"]["PlaceRef"];
            /** Place Population */
            place_population: number | null;
            /** Parent Institution Id */
            parent_institution_id: string | null;
            procurement_handled_by: components["schemas"]["ProcurementHandledBy"];
            /** Homepage Id */
            homepage_id: string | null;
            /** Homepage Url */
            homepage_url: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** InstitutionRef */
        InstitutionRef: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Institution Type */
            institution_type: string;
            status: components["schemas"]["EntityStatus"];
        };
        /** InstitutionTypeInput */
        InstitutionTypeInput: {
            /** Name */
            name: string;
            /** Description */
            description: string;
        };
        /** KindApproveInput */
        KindApproveInput: {
            /** Note */
            note?: string | null;
            /** Kind */
            kind: string;
            /** Institution Type */
            institution_type?: string | null;
        };
        /** KindDecisionInput */
        KindDecisionInput: {
            /** Note */
            note?: string | null;
            /** Kind */
            kind: string;
        };
        /** KindDecisionOutput */
        KindDecisionOutput: {
            /** Kind */
            kind: string;
            /** Review Items */
            review_items: components["schemas"]["ReviewItemOutput"][];
            /** Spawn */
            spawn: components["schemas"]["SpawnOutput"][];
            /**
             * Assignment Ids
             * @default []
             */
            assignment_ids: string[];
        };
        /** KindOutput */
        KindOutput: {
            /** Kind */
            kind: string;
            /** Rule */
            rule: string;
            /** Count */
            count: number;
            /** Question */
            question: {
                [key: string]: unknown;
            };
            /**
             * Names
             * @description The first few entities of the kind, to recognise it by.
             */
            names: string[];
            /** Item Ids */
            item_ids: string[];
        };
        /** MergeInput */
        MergeInput: {
            /** Note */
            note?: string | null;
            /**
             * Into Id
             * Format: uuid
             */
            into_id: string;
        };
        /** MetricOutput */
        MetricOutput: {
            /** Name */
            name: string;
            /** Year */
            year: number;
            /** Value */
            value: string;
        };
        /**
         * NamingRules
         * @description How the country writes its public bodies' names, in its languages. A government's name is
         *     a place name with a designator around it ("Township of Elmwood", "Elmwood, Township of");
         *     knowing the designators lets the checks find the place name and tell a township from the
         *     city of the same name.
         */
        NamingRules: {
            /**
             * Designators
             * @default []
             */
            designators: string[][];
            /**
             * Connectors
             * @default []
             */
            connectors: string[];
            /**
             * Leading
             * @default []
             */
            leading: string[];
            /**
             * And Words
             * @default []
             */
            and_words: string[];
        };
        /** Page[AssignmentOutput] */
        Page_AssignmentOutput_: {
            /** Items */
            items: components["schemas"]["AssignmentOutput"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** Page[EvalRunOutput] */
        Page_EvalRunOutput_: {
            /** Items */
            items: components["schemas"]["EvalRunOutput"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** Page[InstitutionOutput] */
        Page_InstitutionOutput_: {
            /** Items */
            items: components["schemas"]["InstitutionOutput"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** Page[PlaceOutput] */
        Page_PlaceOutput_: {
            /** Items */
            items: components["schemas"]["PlaceOutput"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** Page[ReviewItemRow] */
        Page_ReviewItemRow_: {
            /** Items */
            items: components["schemas"]["ReviewItemRow"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** Page[RunDetail] */
        Page_RunDetail_: {
            /** Items */
            items: components["schemas"]["RunDetail"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** PlaceDetail */
        PlaceDetail: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Country Code */
            country_code: string;
            /** Administrative Level */
            administrative_level: string;
            /** Parent Place Id */
            parent_place_id: string | null;
            /** Government Institution Id */
            government_institution_id: string | null;
            status: components["schemas"]["EntityStatus"];
            entered_by: components["schemas"]["EnteredBy"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Population */
            population: number | null;
            /** Parents */
            parents: components["schemas"]["PlaceRef"][];
            government: components["schemas"]["InstitutionRef"] | null;
        };
        /** PlaceOutput */
        PlaceOutput: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Country Code */
            country_code: string;
            /** Administrative Level */
            administrative_level: string;
            /** Parent Place Id */
            parent_place_id: string | null;
            /** Government Institution Id */
            government_institution_id: string | null;
            status: components["schemas"]["EntityStatus"];
            entered_by: components["schemas"]["EnteredBy"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Population */
            population: number | null;
        };
        /** PlaceRef */
        PlaceRef: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Administrative Level */
            administrative_level: string;
        };
        /**
         * ProcurementHandledBy
         * @description Whether an institution buys on its own account or its parent buys for it.
         * @enum {string}
         */
        ProcurementHandledBy: "self" | "parent";
        /**
         * Progress
         * @description How far a run has got and what it has spent.
         */
        Progress: {
            /** By Status */
            by_status: {
                [key: string]: number;
            };
            /** By Result */
            by_result: {
                [key: string]: number;
            };
            /** Cost */
            cost: string;
        };
        /** QuoteContextOutput */
        QuoteContextOutput: {
            /**
             * Evidence Id
             * Format: uuid
             */
            evidence_id: string;
            /** Found */
            found: boolean;
            /** Before */
            before: string;
            /** Quote */
            quote: string;
            /** After */
            after: string;
            /** Page */
            page: number | null;
        };
        /**
         * ReleaseInput
         * @description Which held assignments to queue: a few at a time by default.
         */
        ReleaseInput: {
            /**
             * Limit
             * @default 1
             */
            limit: number;
            assignment_type?: components["schemas"]["AssignmentType"] | null;
            /**
             * Assignment Ids
             * @default []
             */
            assignment_ids: string[];
        };
        /** ReviewItemDetail */
        ReviewItemDetail: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Entity Id
             * Format: uuid
             */
            entity_id: string;
            /** Rule */
            rule: string;
            /** Question */
            question: {
                [key: string]: unknown;
            };
            /** Kind */
            kind: string | null;
            status: components["schemas"]["ReviewStatus"];
            /** Raised By Assignment Id */
            raised_by_assignment_id: string | null;
            /** Decided At */
            decided_at: string | null;
            /** Note */
            note: string | null;
            entity_kind: components["schemas"]["EntityKind"];
            /** Entity Status */
            entity_status: string;
            /** Label */
            label: string;
            /** Names */
            names: string[];
            /** Entity */
            entity: {
                [key: string]: unknown;
            };
            /** Evidence */
            evidence: components["schemas"]["EvidenceOutput"][];
        };
        /** ReviewItemOutput */
        ReviewItemOutput: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Entity Id
             * Format: uuid
             */
            entity_id: string;
            /** Rule */
            rule: string;
            /** Question */
            question: {
                [key: string]: unknown;
            };
            /** Kind */
            kind: string | null;
            status: components["schemas"]["ReviewStatus"];
            /** Raised By Assignment Id */
            raised_by_assignment_id: string | null;
            /** Decided At */
            decided_at: string | null;
            /** Note */
            note: string | null;
        };
        /**
         * ReviewItemRow
         * @description An item as the queue lists it: with what to recognise its entity by.
         */
        ReviewItemRow: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Entity Id
             * Format: uuid
             */
            entity_id: string;
            /** Rule */
            rule: string;
            /** Question */
            question: {
                [key: string]: unknown;
            };
            /** Kind */
            kind: string | null;
            status: components["schemas"]["ReviewStatus"];
            /** Raised By Assignment Id */
            raised_by_assignment_id: string | null;
            /** Decided At */
            decided_at: string | null;
            /** Note */
            note: string | null;
            entity_kind: components["schemas"]["EntityKind"];
            /** Label */
            label: string;
        };
        /**
         * ReviewStatus
         * @enum {string}
         */
        ReviewStatus: "open" | "approved" | "rejected" | "merged";
        /** RunDetail */
        RunDetail: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Country Code */
            country_code: string;
            mode: components["schemas"]["RunMode"];
            status: components["schemas"]["RunStatus"];
            /** Filter */
            filter: {
                [key: string]: unknown;
            };
            /** Is Eval */
            is_eval: boolean;
            /** Record Video */
            record_video: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            progress: components["schemas"]["Progress"];
        };
        /**
         * RunFilter
         * @description What a run works on (spec section 7.1). An empty list is no restriction. The levels and
         *     types bound the subjects a run seeds itself with and every assignment it spawns; the subject
         *     ids name the places and institutions it starts from, and spawned work descends from them.
         */
        RunFilter: {
            /**
             * Administrative Levels
             * @default []
             */
            administrative_levels: string[];
            /**
             * Institution Types
             * @default []
             */
            institution_types: string[];
            /**
             * Assignment Types
             * @default []
             */
            assignment_types: components["schemas"]["AssignmentType"][];
            /**
             * Subject Ids
             * @default []
             */
            subject_ids: string[];
        };
        /** RunInput */
        RunInput: {
            /** Name */
            name: string;
            /** Country Code */
            country_code: string;
            mode: components["schemas"]["RunMode"];
            /**
             * @default {
             *       "administrative_levels": [],
             *       "institution_types": [],
             *       "assignment_types": [],
             *       "subject_ids": []
             *     }
             */
            filter: components["schemas"]["RunFilter"];
            /**
             * Record Video
             * @default false
             */
            record_video: boolean;
        };
        /**
         * RunMode
         * @enum {string}
         */
        RunMode: "step" | "auto";
        /**
         * RunStatus
         * @enum {string}
         */
        RunStatus: "active" | "paused" | "stopped";
        /**
         * SourceAccess
         * @enum {string}
         */
        SourceAccess: "public" | "login";
        /** SourceOutput */
        SourceOutput: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Url */
            url: string;
            /** Source Type */
            source_type: string;
            access: components["schemas"]["SourceAccess"];
            status: components["schemas"]["EntityStatus"];
            entered_by: components["schemas"]["EnteredBy"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** SourceTypeInput */
        SourceTypeInput: {
            /** Name */
            name: string;
            /** Description */
            description: string;
        };
        /**
         * SpawnOutput
         * @description Work the decision asks for; the assignments module queues it.
         */
        SpawnOutput: {
            type: components["schemas"]["AssignmentType"];
            /**
             * Subject Id
             * Format: uuid
             */
            subject_id: string;
        };
        /**
         * SubjectOutput
         * @description The place or institution an assignment works on, by name.
         */
        SubjectOutput: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            kind: components["schemas"]["EntityKind"];
            /** Name */
            name: string;
        };
        /**
         * TypeSummary
         * @description One assignment type's scores over the subjects of a run: how many subjects were judged
         *     on it, and the mean of their recall and precision (unweighted: each subject counts once).
         */
        TypeSummary: {
            /** Subjects */
            subjects: number;
            /** Mean Recall */
            mean_recall: number | null;
            /** Mean Precision */
            mean_precision: number | null;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type AdministrativeLevelInput = components['schemas']['AdministrativeLevelInput'];
export type AliasOutput = components['schemas']['AliasOutput'];
export type ApproveInput = components['schemas']['ApproveInput'];
export type AssignmentDetail = components['schemas']['AssignmentDetail'];
export type AssignmentOutput = components['schemas']['AssignmentOutput'];
export type AssignmentResult = components['schemas']['AssignmentResult'];
export type AssignmentStatus = components['schemas']['AssignmentStatus'];
export type AssignmentType = components['schemas']['AssignmentType'];
export type CountryInstitutionTypeInput = components['schemas']['CountryInstitutionTypeInput'];
export type CountryOutput = components['schemas']['CountryOutput'];
export type CountrySettingsInput = components['schemas']['CountrySettingsInput'];
export type DecisionInput = components['schemas']['DecisionInput'];
export type DecisionOutput = components['schemas']['DecisionOutput'];
export type EnteredBy = components['schemas']['EnteredBy'];
export type EntityKind = components['schemas']['EntityKind'];
export type EntityStatus = components['schemas']['EntityStatus'];
export type EvalRunDetail = components['schemas']['EvalRunDetail'];
export type EvalRunOutput = components['schemas']['EvalRunOutput'];
export type EvalScoreOutput = components['schemas']['EvalScoreOutput'];
export type EventKind = components['schemas']['EventKind'];
export type EventOutput = components['schemas']['EventOutput'];
export type EvidenceOutput = components['schemas']['EvidenceOutput'];
export type FindingOutput = components['schemas']['FindingOutput'];
export type HttpValidationError = components['schemas']['HTTPValidationError'];
export type Health = components['schemas']['Health'];
export type HomepageOutput = components['schemas']['HomepageOutput'];
export type IdentifierOutput = components['schemas']['IdentifierOutput'];
export type InstitutionDetail = components['schemas']['InstitutionDetail'];
export type InstitutionOutput = components['schemas']['InstitutionOutput'];
export type InstitutionRef = components['schemas']['InstitutionRef'];
export type InstitutionTypeInput = components['schemas']['InstitutionTypeInput'];
export type KindApproveInput = components['schemas']['KindApproveInput'];
export type KindDecisionInput = components['schemas']['KindDecisionInput'];
export type KindDecisionOutput = components['schemas']['KindDecisionOutput'];
export type KindOutput = components['schemas']['KindOutput'];
export type MergeInput = components['schemas']['MergeInput'];
export type MetricOutput = components['schemas']['MetricOutput'];
export type NamingRules = components['schemas']['NamingRules'];
export type PageAssignmentOutput = components['schemas']['Page_AssignmentOutput_'];
export type PageEvalRunOutput = components['schemas']['Page_EvalRunOutput_'];
export type PageInstitutionOutput = components['schemas']['Page_InstitutionOutput_'];
export type PagePlaceOutput = components['schemas']['Page_PlaceOutput_'];
export type PageReviewItemRow = components['schemas']['Page_ReviewItemRow_'];
export type PageRunDetail = components['schemas']['Page_RunDetail_'];
export type PlaceDetail = components['schemas']['PlaceDetail'];
export type PlaceOutput = components['schemas']['PlaceOutput'];
export type PlaceRef = components['schemas']['PlaceRef'];
export type ProcurementHandledBy = components['schemas']['ProcurementHandledBy'];
export type Progress = components['schemas']['Progress'];
export type QuoteContextOutput = components['schemas']['QuoteContextOutput'];
export type ReleaseInput = components['schemas']['ReleaseInput'];
export type ReviewItemDetail = components['schemas']['ReviewItemDetail'];
export type ReviewItemOutput = components['schemas']['ReviewItemOutput'];
export type ReviewItemRow = components['schemas']['ReviewItemRow'];
export type ReviewStatus = components['schemas']['ReviewStatus'];
export type RunDetail = components['schemas']['RunDetail'];
export type RunFilter = components['schemas']['RunFilter'];
export type RunInput = components['schemas']['RunInput'];
export type RunMode = components['schemas']['RunMode'];
export type RunStatus = components['schemas']['RunStatus'];
export type SourceAccess = components['schemas']['SourceAccess'];
export type SourceOutput = components['schemas']['SourceOutput'];
export type SourceTypeInput = components['schemas']['SourceTypeInput'];
export type SpawnOutput = components['schemas']['SpawnOutput'];
export type SubjectOutput = components['schemas']['SubjectOutput'];
export type TypeSummary = components['schemas']['TypeSummary'];
export type ValidationError = components['schemas']['ValidationError'];
export type $defs = Record<string, never>;
export interface operations {
    "health-read_health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
        };
    };
    "health-read_health_db": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "health-read_health_storage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
        };
    };
    "countries-list_countries": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CountrySettingsInput"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-read_country": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                country_code: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CountryOutput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-put_country_settings": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                country_code: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CountrySettingsInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CountrySettingsInput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-put_administrative_level": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                country_code: string;
                name: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AdministrativeLevelInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdministrativeLevelInput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-delete_administrative_level": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                country_code: string;
                name: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-put_country_institution_type": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                country_code: string;
                institution_type: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CountryInstitutionTypeInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CountryInstitutionTypeInput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-delete_country_institution_type": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                country_code: string;
                institution_type: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-list_institution_types": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstitutionTypeInput"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-put_institution_type": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InstitutionTypeInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstitutionTypeInput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-delete_institution_type": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-list_source_types": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceTypeInput"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-put_source_type": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SourceTypeInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceTypeInput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "countries-delete_source_type": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "graph-list_institutions": {
        parameters: {
            query?: {
                q?: string | null;
                country_code?: string | null;
                place_id?: string | null;
                administrative_level?: string | null;
                institution_type?: string | null;
                status?: components["schemas"]["EntityStatus"] | null;
                parent_institution_id?: string | null;
                min_population?: number | null;
                max_population?: number | null;
                sort?: "name" | "institution_type" | "status" | "created_at" | "place" | "population";
                order?: "asc" | "desc";
                limit?: number;
                offset?: number;
            };
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_InstitutionOutput_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "graph-read_institution": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                institution_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstitutionDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "graph-list_places": {
        parameters: {
            query?: {
                q?: string | null;
                country_code?: string | null;
                administrative_level?: string | null;
                parent_place_id?: string | null;
                min_population?: number | null;
                max_population?: number | null;
                sort?: "name" | "administrative_level" | "population";
                order?: "asc" | "desc";
                limit?: number;
                offset?: number;
            };
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_PlaceOutput_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "graph-read_place": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                place_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlaceDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "evidence-read_evidence_context": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                evidence_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuoteContextOutput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "review-list_review_items": {
        parameters: {
            query?: {
                status?: components["schemas"]["ReviewStatus"] | null;
                kind?: string | null;
                rule?: string | null;
                limit?: number;
                offset?: number;
            };
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_ReviewItemRow_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "review-list_review_kinds": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KindOutput"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "review-approve_review_kind": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KindApproveInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KindDecisionOutput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "review-reject_review_kind": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KindDecisionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KindDecisionOutput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "review-read_review_item": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                review_item_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewItemDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "review-approve_review_item": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                review_item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApproveInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DecisionOutput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "review-reject_review_item": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                review_item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DecisionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DecisionOutput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "review-merge_review_item": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                review_item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MergeInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DecisionOutput"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "runs-list_runs": {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_RunDetail_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "runs-create_run": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RunInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "runs-read_run": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "runs-pause_run": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "runs-resume_run": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "runs-stop_run": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "runs-release_assignments": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReleaseInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssignmentOutput"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "runs-list_assignments": {
        parameters: {
            query?: {
                run_id?: string | null;
                status?: components["schemas"]["AssignmentStatus"] | null;
                result?: components["schemas"]["AssignmentResult"] | null;
                type?: components["schemas"]["AssignmentType"] | null;
                subject_id?: string | null;
                order?: string;
                limit?: number;
                offset?: number;
            };
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_AssignmentOutput_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "runs-read_assignment": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                assignment_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssignmentDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "runs-read_assignment_events": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                assignment_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EventOutput"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "runs-read_assignment_findings": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                assignment_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FindingOutput"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "evals-list_eval_runs": {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Page_EvalRunOutput_"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    "evals-read_eval_run": {
        parameters: {
            query?: never;
            header?: {
                /** @description `main` (the default) or `eval`: which database the request reads. */
                "x-database"?: string | null;
            };
            path: {
                eval_run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvalRunDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
