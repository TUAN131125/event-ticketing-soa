import type { ReactNode } from 'react';
import {
  Activity,
  CalendarDays,
  ClipboardList,
  CircleDollarSign,
  RefreshCcw,
  Server,
} from 'lucide-react';
import { Badge, Button, Card } from '@event-ticketing/shared-ui';
import { useAdminOverview } from '../hooks/useAdminApi';
import { PageHeader } from '../components/AppShell';
import { QueryState } from '../components/QueryState';

const money = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});
export function DashboardPage() {
  const query = useAdminOverview();
  const overview = query.data;
  return (
    <>
      <PageHeader
        eyebrow="Today"
        title="Good morning, operator"
        description="A live view of event operations. Data is sourced from the booking gateway."
        actions={
          <Button
            icon={<RefreshCcw size={16} />}
            variant="secondary"
            onClick={() => void query.refetch()}
          >
            Refresh
          </Button>
        }
      />
      <QueryState
        isLoading={query.isLoading}
        error={query.error}
        onRetry={() => void query.refetch()}
      >
        <div className="metric-grid">
          <Metric icon={<CalendarDays />} label="Published events" value={overview?.events ?? 0} />
          <Metric icon={<ClipboardList />} label="Total bookings" value={overview?.bookings ?? 0} />
          <Metric
            icon={<Activity />}
            label="Active bookings"
            value={overview?.activeBookings ?? 0}
          />
          <Metric
            icon={<CircleDollarSign />}
            label="Revenue"
            value={overview?.revenue === undefined ? '—' : money.format(overview.revenue)}
          />
        </div>
        <div className="dashboard-grid">
          <Card>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Dependencies</p>
                <h3>Service health</h3>
              </div>
              <Server size={21} aria-hidden="true" />
            </div>
            <div className="health-list">
              {overview?.serviceHealth?.map((service) => (
                <div className="health-row" key={service.name}>
                  <span
                    className={`status-dot ${service.status.toLowerCase() === 'healthy' || service.status.toLowerCase() === 'ok' ? 'is-healthy' : 'is-degraded'}`}
                  />
                  <span>{service.name}</span>
                  <Badge
                    tone={
                      service.status.toLowerCase() === 'healthy' ||
                      service.status.toLowerCase() === 'ok'
                        ? 'success'
                        : 'warning'
                    }
                  >
                    {service.status}
                  </Badge>
                  {service.latencyMs !== undefined && <small>{service.latencyMs} ms</small>}
                </div>
              )) ?? <p className="muted">No service health telemetry returned.</p>}
            </div>
          </Card>
          <Card>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Runbook</p>
                <h3>Operational reminders</h3>
              </div>
            </div>
            <ul className="plain-list">
              <li>Verify payment failures are compensated before closing an event.</li>
              <li>Review reservation expiry lag and failed notifications.</li>
              <li>Keep admin actions traceable with a correlation ID.</li>
            </ul>
          </Card>
        </div>
      </QueryState>
    </>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <Card className="metric-card">
      <span className="metric-icon">{icon}</span>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
    </Card>
  );
}
