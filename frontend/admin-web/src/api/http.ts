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

type RequestOptions = Omit<RequestInit, 'body'> & { body?: unknown; accessToken?: string };

const jsonHeaders = (headers?: HeadersInit) => {
  const result = new Headers(headers);
  result.set('Accept', 'application/json');
  if (!result.has('Content-Type')) result.set('Content-Type', 'application/json');
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
  if (!baseUrl)
    throw new ApiError('The service is not configured', {
      status: 503,
      code: 'SERVICE_UNAVAILABLE',
      retryable: true,
    });
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 15_000);
  const headers = jsonHeaders(options.headers);
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
    if (!response.ok) {
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
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError')
      throw new ApiError('The service did not respond in time', { code: 'SERVICE_TIMEOUT' });
    throw new ApiError('The service is unavailable', { code: 'SERVICE_UNAVAILABLE' });
  } finally {
    window.clearTimeout(timer);
  }
}

export const normalisePage = <T>(
  payload: unknown,
  fallbackPage = 1,
  fallbackPageSize = 20,
): import('../types').Page<T> => {
  if (Array.isArray(payload))
    return {
      items: payload as T[],
      page: fallbackPage,
      pageSize: fallbackPageSize,
      total: payload.length,
      totalPages: 1,
    };
  const record =
    typeof payload === 'object' && payload !== null ? (payload as Record<string, unknown>) : {};
  const items = (record.items ?? record.data ?? record.results) as T[] | undefined;
  const page = Number(record.page ?? fallbackPage);
  const pageSize = Number(record.pageSize ?? record.page_size ?? fallbackPageSize);
  const total = Number(record.total ?? items?.length ?? 0);
  const totalPages = record.totalPages ?? (Math.ceil(total / pageSize) || 1);
  return {
    items: Array.isArray(items) ? items : [],
    page,
    pageSize,
    total,
    totalPages: Math.max(1, Number(totalPages)),
  };
};
