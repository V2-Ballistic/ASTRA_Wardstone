// ══════════════════════════════════════════════════════════════
//  ASTRA — Safe API error rendering
//
//  File: frontend/src/lib/errors.ts
//
//  FastAPI's `detail` field is one of:
//    1. a plain string (most HTTPException raises)
//    2. a Pydantic v2 validation array:
//         [{ type, loc, msg, input, ... }, ...]
//    3. an arbitrary object (some endpoints attach structured detail)
//
//  Rendering any of (2) or (3) directly as a React child crashes with
//  "Objects are not valid as a React child (found: object with keys
//  {type, loc, msg, input})". `formatApiError` always returns a plain
//  string suitable for `setError(...)` or for embedding in JSX.
// ══════════════════════════════════════════════════════════════

type PydanticError = {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
  input?: unknown;
};

function isPydanticErrorArray(value: unknown): value is PydanticError[] {
  return (
    Array.isArray(value)
    && value.length > 0
    && value.every(
      (v): v is PydanticError =>
        typeof v === 'object' && v !== null && 'msg' in (v as object),
    )
  );
}

function formatPydanticError(arr: PydanticError[]): string {
  return arr
    .map((e) => {
      const loc = Array.isArray(e.loc) && e.loc.length > 0
        ? e.loc.filter((p) => p !== 'body' && p !== 'query' && p !== 'path').join('.')
        : '';
      const msg = e.msg || 'Validation error';
      return loc ? `${loc}: ${msg}` : msg;
    })
    .join('; ');
}

/**
 * Convert any caught error from an Axios request — or any thrown value —
 * into a safe, human-readable string.
 *
 * @param err      The caught error (Axios error, Error instance, string, or anything).
 * @param fallback Message to return when `err` carries no useful detail.
 */
export function formatApiError(
  err: unknown,
  fallback: string = 'An unexpected error occurred',
): string {
  if (err == null) return fallback;

  // Axios error shape: err.response.data.detail
  const detail = (err as {
    response?: { data?: { detail?: unknown; message?: unknown } };
  })?.response?.data?.detail;

  if (typeof detail === 'string' && detail.trim()) return detail;
  if (typeof detail === 'number' || typeof detail === 'boolean') return String(detail);
  if (isPydanticErrorArray(detail)) return formatPydanticError(detail);

  if (detail && typeof detail === 'object') {
    // Some endpoints return { detail: { detail: '...' } } or other shapes.
    const nested = (detail as { detail?: unknown; message?: unknown }).detail
      ?? (detail as { detail?: unknown; message?: unknown }).message;
    if (typeof nested === 'string' && nested.trim()) return nested;
    try {
      const s = JSON.stringify(detail);
      if (s && s !== '{}') return s;
    } catch {
      // fall through to message / fallback
    }
  }

  // Sometimes the body carries `message` instead of `detail`.
  const bodyMessage = (err as { response?: { data?: { message?: unknown } } })
    ?.response?.data?.message;
  if (typeof bodyMessage === 'string' && bodyMessage.trim()) return bodyMessage;

  // Network/transport errors — Axios sets err.message.
  const message = (err as { message?: unknown })?.message;
  if (typeof message === 'string' && message.trim()) return message;

  if (typeof err === 'string') return err;
  return fallback;
}
