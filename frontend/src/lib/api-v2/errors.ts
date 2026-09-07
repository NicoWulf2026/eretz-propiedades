export type ApiV2ErrorKind =
  | "NOT_FOUND"
  | "BAD_REQUEST"
  | "NETWORK_ERROR"
  | "TIMEOUT"
  | "SERVER_ERROR"
  | "INVALID_RESPONSE"
  | "UNCONFIGURED";

export type ApiV2Issue = { path: string; message: string };

export class ApiV2Error extends Error {
  constructor(
    readonly kind: ApiV2ErrorKind,
    message: string,
    readonly status: number | null = null,
    options?: { cause?: unknown; issues?: ApiV2Issue[] },
  ) {
    super(message, options?.cause === undefined ? undefined : { cause: options.cause });
    this.name = "ApiV2Error";
    this.issues = options?.issues ?? [];
  }

  readonly issues: ApiV2Issue[];
}

export type ApiV2Result<T> =
  | { status: "SUCCESS"; data: T }
  | { status: "SUCCESS_EMPTY"; data: T }
  | { status: "PARTIAL_DATA"; data: T; issues: ApiV2Issue[] }
  | { status: "FAILURE"; error: ApiV2Error };

export function apiV2Failure(kind: ApiV2ErrorKind, message: string, status: number | null = null): ApiV2Result<never> {
  return { status: "FAILURE", error: new ApiV2Error(kind, message, status) };
}
