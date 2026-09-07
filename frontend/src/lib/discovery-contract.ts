import type { ApiV2ErrorKind, ApiV2Issue } from "@/lib/api-v2/errors";
import type { SearchSuggestion } from "@/types/property";

export type DiscoveryAutocompleteResponse =
  | { status: "SUCCESS" | "SUCCESS_EMPTY"; suggestions: SearchSuggestion[] }
  | { status: "PARTIAL_DATA"; suggestions: SearchSuggestion[]; issues: ApiV2Issue[] }
  | { status: "FAILURE"; suggestions: []; error: { kind: ApiV2ErrorKind } };
