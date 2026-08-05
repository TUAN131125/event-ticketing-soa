export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly correlationId?: string;

  constructor(
    message: string,
    options: { status?: number; code?: string; retryable?: boolean; correlationId?: string } = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = options.status ?? 0;
    this.code = options.code ?? 'UNKNOWN_ERROR';
    this.retryable = options.retryable ?? (this.status >= 500 || this.status === 0);
    this.correlationId = options.correlationId;
  }
}

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown;
  accessToken?: string;
  /**
   * Status codes whose documented body must be read instead of raised. `GET /api/health`
   * answers 503 with a full AggregateHealth payload, which the console needs to display.
   */
  acceptStatuses?: number[];
};

const jsonHeaders = (headers: HeadersInit | undefined, hasBody: boolean) => {
  const result = new Headers(headers);
  result.set('Accept', 'application/json');
  if (hasBody && !result.has('Content-Type')) result.set('Content-Type', 'application/json');
  return result;
};

const parseBody = async (response: Response): Promise<unknown> => {
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('json')) return undefined;
  try {
    return await response.json();
  } catch {
    return undefined;
  }
};

export async function request<T>(
  baseUrl: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  return (await requestWithMetadata<T>(baseUrl, path, options)).body;
}

export async function requestWithMetadata<T>(
  baseUrl: string,
  path: string,
  options: RequestOptions = {},
): Promise<{ body: T; etag: string | null }> {
  if (!baseUrl)
    throw new ApiError('The service is not configured', {
      status: 503,
      code: 'SERVICE_UNAVAILABLE',
      retryable: true,
    });
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 15_000);
  const headers = jsonHeaders(options.headers, options.body !== undefined);
  if (options.accessToken) headers.set('Authorization', `Bearer ${options.accessToken}`);
  const correlationId = crypto.randomUUID();
  headers.set('X-Correlation-ID', correlationId);
  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
      ...options,
      headers,
      credentials: 'include',
      signal: options.signal ?? controller.signal,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    const payload = await parseBody(response);
    if (!response.ok && !options.acceptStatuses?.includes(response.status)) {
      const record =
        typeof payload === 'object' && payload !== null ? (payload as Record<string, unknown>) : {};
      const error =
        typeof record.error === 'object' && record.error !== null
          ? (record.error as Record<string, unknown>)
          : record;
      throw new ApiError(
        typeof error.message === 'string' ? error.message : response.statusText || 'Request failed',
        {
          status: response.status,
          code:
            typeof error.code === 'string'
              ? error.code
              : response.status === 401
                ? 'UNAUTHENTICATED'
                : response.status === 403
                  ? 'FORBIDDEN'
                  : response.status === 404
                    ? 'NOT_FOUND'
                    : 'REQUEST_FAILED',
          retryable: typeof record.retryable === 'boolean' ? record.retryable : undefined,
          correlationId:
            typeof record.correlationId === 'string' ? record.correlationId : correlationId,
        },
      );
    }
    return { body: payload as T, etag: response.headers.get('ETag') };
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError')
      throw new ApiError('The service did not respond in time', { code: 'SERVICE_TIMEOUT' });
    throw new ApiError('The service is unavailable', { code: 'SERVICE_UNAVAILABLE' });
  } finally {
    window.clearTimeout(timer);
  }
}
