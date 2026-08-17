// Correlation ids, browser side.
//
// Every API response carries an `X-Request-Id` header (set by
// core/observability.py). The same id is stamped on every audit_events row and
// every workflow_events row produced while handling that request. Surfacing it
// in the UI is what turns "it broke and I don't know why" into one grep.
//
// TWO THINGS THAT MAKE THIS FAIL SILENTLY, both already handled:
//
//  1. A browser can only read response headers named in the server's CORS
//     `expose_headers`. `allow_headers` is about REQUEST headers and does not
//     cover this, and there is no wildcard default. api_server.py now lists
//     X-Request-Id explicitly. Same-origin calls (the Vite proxy in dev, the
//     mounted SPA in production) work either way — which is exactly what would
//     hide the problem until a cross-origin caller hit it.
//
//  2. A network-level failure produces no Response at all, so there is no
//     header to read. That is why the last successfully-seen id is remembered:
//     it is still the best pointer to the surrounding server-side activity,
//     and it is clearly labelled as approximate where it is shown.

/** The last request id this browser saw, across any endpoint. */
let _lastRequestId: string | null = null

export const REQUEST_ID_HEADER = 'X-Request-Id'

/**
 * Read the correlation id off a response, remembering it for later.
 * Returns null when the header is absent or unreadable (see note 1 above).
 */
export function readRequestId(res: Response): string | null {
  const id = res.headers.get(REQUEST_ID_HEADER)
  if (id) _lastRequestId = id
  return id
}

/**
 * The most recent id seen. Use only when a specific response is unavailable —
 * a thrown network error, or a render crash — and label it as approximate.
 */
export function lastRequestId(): string | null {
  return _lastRequestId
}
