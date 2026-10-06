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
    "/review-items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Review Items
         * @description The items, open ones by default, oldest first.
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
        /** ApproveInput */
        ApproveInput: {
            /** Note */
            note?: string | null;
            /** Institution Type */
            institution_type?: string | null;
        };
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
        };
        /**
         * EntityKind
         * @enum {string}
         */
        EntityKind: "place" | "institution" | "source" | "domain" | "homepage";
        /** EvidenceOutput */
        EvidenceOutput: {
            /** Quote */
            quote: string;
            /** Kind */
            kind: string;
            /** Locator */
            locator: number | null;
            /** Link Url */
            link_url: string | null;
            /** Page Url */
            page_url: string;
            /**
             * Snapshot Url
             * @description A short-lived download link to the stored page or file; null once pruned.
             */
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
         * ReviewStatus
         * @enum {string}
         */
        ReviewStatus: "open" | "approved" | "rejected" | "merged";
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
export type ApproveInput = components['schemas']['ApproveInput'];
export type AssignmentType = components['schemas']['AssignmentType'];
export type CountryInstitutionTypeInput = components['schemas']['CountryInstitutionTypeInput'];
export type CountryOutput = components['schemas']['CountryOutput'];
export type CountrySettingsInput = components['schemas']['CountrySettingsInput'];
export type DecisionInput = components['schemas']['DecisionInput'];
export type DecisionOutput = components['schemas']['DecisionOutput'];
export type EntityKind = components['schemas']['EntityKind'];
export type EvidenceOutput = components['schemas']['EvidenceOutput'];
export type HttpValidationError = components['schemas']['HTTPValidationError'];
export type Health = components['schemas']['Health'];
export type InstitutionTypeInput = components['schemas']['InstitutionTypeInput'];
export type KindApproveInput = components['schemas']['KindApproveInput'];
export type KindDecisionInput = components['schemas']['KindDecisionInput'];
export type KindDecisionOutput = components['schemas']['KindDecisionOutput'];
export type KindOutput = components['schemas']['KindOutput'];
export type MergeInput = components['schemas']['MergeInput'];
export type NamingRules = components['schemas']['NamingRules'];
export type ReviewItemDetail = components['schemas']['ReviewItemDetail'];
export type ReviewItemOutput = components['schemas']['ReviewItemOutput'];
export type ReviewStatus = components['schemas']['ReviewStatus'];
export type SourceTypeInput = components['schemas']['SourceTypeInput'];
export type SpawnOutput = components['schemas']['SpawnOutput'];
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
                    "application/json": components["schemas"]["CountrySettingsInput"][];
                };
            };
        };
    };
    "countries-read_country": {
        parameters: {
            query?: never;
            header?: never;
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
            header?: never;
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
            header?: never;
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
            header?: never;
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
            header?: never;
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
            header?: never;
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
                    "application/json": components["schemas"]["InstitutionTypeInput"][];
                };
            };
        };
    };
    "countries-put_institution_type": {
        parameters: {
            query?: never;
            header?: never;
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
            header?: never;
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
                    "application/json": components["schemas"]["SourceTypeInput"][];
                };
            };
        };
    };
    "countries-put_source_type": {
        parameters: {
            query?: never;
            header?: never;
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
            header?: never;
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
    "review-list_review_items": {
        parameters: {
            query?: {
                status?: components["schemas"]["ReviewStatus"] | null;
                kind?: string | null;
                limit?: number;
                offset?: number;
            };
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
                    "application/json": components["schemas"]["ReviewItemOutput"][];
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
                    "application/json": components["schemas"]["KindOutput"][];
                };
            };
        };
    };
    "review-approve_review_kind": {
        parameters: {
            query?: never;
            header?: never;
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
            header?: never;
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
            header?: never;
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
            header?: never;
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
            header?: never;
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
            header?: never;
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
}
