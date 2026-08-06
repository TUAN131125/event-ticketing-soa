import { useState, type FormEvent } from 'react';
import { Search } from 'lucide-react';
import { esbAdminClient, type TraceStep } from '../api/esb';
import { StatusBadge } from '../components/StatusBadge';

export function WorkflowTracesPage({ accessToken }: { accessToken: string }) {
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const lookup = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    const id = String(new FormData(event.currentTarget).get('correlationId') ?? '').trim();
    if (!id) return;
    setBusy(true);
    void esbAdminClient
      .traces(accessToken, id)
      .then(setSteps)
      .catch((value: Error) => setError(value.message))
      .finally(() => setBusy(false));
  };

  return (
    <section className="card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">ESB orchestration</p>
          <h3>Workflow trace</h3>
        </div>
        <small className="muted">Admin only</small>
      </div>
      <form className="toolbar" onSubmit={lookup}>
        <Search size={18} aria-hidden="true" />
        <input
          className="native-input"
          name="correlationId"
          aria-label="Correlation ID"
          placeholder="corr-..."
          required
        />
        <button className="native-button" type="submit" disabled={busy}>
          {busy ? 'Loading…' : 'Look up'}
        </button>
      </form>
      {error && <p className="form-error">{error}</p>}
      {steps.length > 0 ? (
        <div className="trace-timeline">
          {steps.map((step, index) => (
            <article className="trace-step" key={`${step.service}-${step.operation}-${index}`}>
              <span className="trace-step__index">{index + 1}</span>
              <div>
                <strong>{step.service}</strong>
                <span>{step.operation}</span>
              </div>
              <StatusBadge value={step.status ?? 'UNKNOWN'} />
              <small>{step.durationMs ?? 0} ms</small>
              <small className={step.errorCode ? 'trace-error' : 'muted'}>
                {step.errorCode ?? 'No error'}
              </small>
            </article>
          ))}
        </div>
      ) : (
        !error && <p className="muted">Enter a correlation ID to reconstruct an ESB workflow.</p>
      )}
    </section>
  );
}
