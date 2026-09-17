import type { ApiV2ErrorKind, ApiV2Issue } from "@/lib/api-v2/errors";
import type { CatalogFilterMetadata } from "@/domain/catalog-discovery";
import type { SearchSuggestion } from "@/types/property";

export type DiscoveryAutocompleteResponse =
  | { status: "SUCCESS" | "SUCCESS_EMPTY"; suggestions: SearchSuggestion[] }
  | { status: "PARTIAL_DATA"; suggestions: SearchSuggestion[]; issues: ApiV2Issue[] }
  | { status: "FAILURE"; suggestions: []; error: { kind: ApiV2ErrorKind } };

export type DiscoveryFilterMetadataResponse =
  | { status: "SUCCESS"; metadata: CatalogFilterMetadata }
  | { status: "SUCCESS_EMPTY"; metadata: null }
  | { status: "PARTIAL_DATA"; metadata: CatalogFilterMetadata; issues: ApiV2Issue[] }
  | { status: "FAILURE"; metadata: null; error: { kind: ApiV2ErrorKind } };

export type DiscoveryFilterMetadataState =
  | { status: "LOADING"; metadata: null }
  | DiscoveryFilterMetadataResponse;
