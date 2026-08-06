import { useCallback, useEffect, useState } from 'react';
import { esbAdminClient, type AggregateHealth } from '../api/esb';
import { StatusBadge } from '../components/StatusBadge';

export function HealthPanel({ accessToken, compact = false }: { accessToken: string; compact?: boolean }) {
  const [health, setHealth] = useState<AggregateHealth | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setError('');
    void esbAdminClient
      .health(accessToken)
      .then(setHealth)
      .catch((value: Error) => setError(value.message));
  }, [accessToken]);

  useEffect(load, [load]);

  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Platform</p>
          <h3>Aggregate health</h3>
        </div>
        {health && <StatusBadge value={health.status} />}
      </div>
      {error && <p className="form-error">{error}</p>}
      {health ? (
        <div className={compact ? 'health-list compact-health-list' : 'health-list'}>
          {health.dependencies.map((dependency) => (
            <div className="health-row" key={dependency.name}>
              <span>
                <span
                  className={`status-dot ${dependency.status === 'UP' ? 'is-healthy' : 'is-degraded'}`}
                />
                {dependency.name}
              </span>
              <small>
                {dependency.critical ? 'critical' : 'noncritical'} · {dependency.status}
                {dependency.latencyMs !== undefined ? ` · ${dependency.latencyMs} ms` : ''}
                {dependency.errorCode ? ` · ${dependency.errorCode}` : ''}
              </small>
            </div>
          ))}
        </div>
      ) : (
        !error && <p className="muted">Loading dependency status…</p>
      )}
      <button className="text-button" type="button" onClick={load}>
        Refresh health
      </button>
    </section>
  );
}
