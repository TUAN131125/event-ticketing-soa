import {
  CalendarDays,
  LayoutDashboard,
  ScanLine,
  Workflow,
  type LucideIcon,
} from 'lucide-react';

export type NavigationGroup = 'Monitor' | 'Operate';

export type NavigationItem = {
  path: string;
  label: string;
  icon: LucideIcon;
  group: NavigationGroup;
};

export const NAV_ITEMS: NavigationItem[] = [
  { path: '/overview', label: 'Overview', icon: LayoutDashboard, group: 'Monitor' },
  { path: '/events', label: 'Event management', icon: CalendarDays, group: 'Operate' },
  { path: '/check-in', label: 'Ticket check-in', icon: ScanLine, group: 'Operate' },
  { path: '/traces', label: 'Workflow traces', icon: Workflow, group: 'Monitor' },
];
