import { Activity, ShieldCheck, Ticket, Workflow } from 'lucide-react';
import { Link } from 'react-router-dom';
import { NAV_ITEMS } from '../app/navigation';
import { StatusBadge } from '../components/StatusBadge';
import { EventsPage } from './EventsPage';
import { HealthPanel } from './HealthPanel';

export function OverviewPage({ accessToken }: { accessToken: string }) {
  const connectedCount = NAV_ITEMS.length;

  return (
    <>
      <div className="metric-grid">
        <article className="card metric-card">
          <div className="metric-icon"><Activity size={20} /></div>
          <span className="metric-label">Connected screens</span>
          <strong className="metric-value">{connectedCount}</strong>
        </article>
        <article className="card metric-card">
          <div className="metric-icon"><Workflow size={20} /></div>
          <span className="metric-label">Contract source</span>
          <strong className="metric-value">ESB OpenAPI</strong>
        </article>
        <article className="card metric-card">
          <div className="metric-icon"><ShieldCheck size={20} /></div>
          <span className="metric-label">Business boundary</span>
          <strong className="metric-value">ESB only</strong>
        </article>
        <article className="card metric-card">
          <div className="metric-icon"><Ticket size={20} /></div>
          <span className="metric-label">Product mode</span>
          <strong className="metric-value">Contract-first</strong>
        </article>
      </div>
      <div className="dashboard-grid">
        <HealthPanel accessToken={accessToken} compact />
        <EventsPage accessToken={accessToken} compact />
        <section className="card completion-map">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Frontend completion map</p>
              <h3>Operational screens</h3>
            </div>
          </div>
          <div className="completion-list">
            {NAV_ITEMS.filter((item) => item.path !== '/overview').map((item) => {
              const Icon = item.icon;
              return (
                <Link to={item.path} key={item.path}>
                  <span><Icon size={18} /></span>
                  <span>
                    <strong>{item.label}</strong>
                    <small>Connected to canonical ESB contract</small>
                  </span>
                  <StatusBadge value="AVAILABLE" />
                </Link>
              );
            })}
          </div>
        </section>
      </div>
    </>
  );
}
