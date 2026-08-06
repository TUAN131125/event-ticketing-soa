import { ApiError } from '../../api/auth-client';

export function ApiErrorDetails({ error }: { error: unknown }) {
  if (!(error instanceof ApiError)) return null;
  return (
    <dl className="api-error-details" aria-label="Error details">
      <div>
        <dt>Error code</dt>
        <dd>{error.code}</dd>
      </div>
      {error.correlationId && (
        <div>
          <dt>Correlation ID</dt>
          <dd>{error.correlationId}</dd>
        </div>
      )}
      {error.traceId && (
        <div>
          <dt>Trace ID</dt>
          <dd>{error.traceId}</dd>
        </div>
      )}
    </dl>
  );
}
