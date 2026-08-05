import { useState } from 'react';
import { Search, UserCog } from 'lucide-react';
import { Badge, Button, Card, Input, Select, Pagination } from '@event-ticketing/shared-ui';
import { useAdminUsers, useAssignRole } from '../hooks/useAdminApi';
import { PageHeader } from '../components/AppShell';
import { QueryState } from '../components/QueryState';
import { Table } from '../components/Table';
import type { Role, User } from '../types';

export function UserManagementPage() {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [selectedRole, setSelectedRole] = useState<Role>('CHECKIN_STAFF');
  const query = useAdminUsers({ search, page });
  const mutation = useAssignRole();
  return (
    <>
      <PageHeader
        eyebrow="Access control"
        title="Users & roles"
        description="Role changes are audited by Identity and apply to newly issued tokens."
      />
      <Card>
        <div className="toolbar">
          <label className="search-control">
            <Search size={16} />
            <Input
              aria-label="Search users"
              placeholder="Search by email"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
            />
          </label>
          <label className="inline-select">
            Role
            <Select
              aria-label="Role to manage"
              value={selectedRole}
              onChange={(event) => setSelectedRole(event.target.value as Role)}
              options={[
                { value: 'CHECKIN_STAFF', label: 'Check-in staff' },
                { value: 'CUSTOMER', label: 'Customer' },
              ]}
            />
          </label>
        </div>
        <QueryState
          isLoading={query.isLoading}
          error={query.error}
          onRetry={() => void query.refetch()}
        >
          <Table<User>
            rows={query.data?.items ?? []}
            columns={[
              {
                key: 'user',
                label: 'User',
                render: (row) => (
                  <div className="table-primary">
                    <strong>{row.displayName ?? row.email}</strong>
                    <small>{row.email}</small>
                  </div>
                ),
              },
              {
                key: 'status',
                label: 'Account',
                render: (row) => (
                  <Badge tone={row.status?.toLowerCase() === 'active' ? 'success' : 'warning'}>
                    {row.status ?? 'Unknown'}
                  </Badge>
                ),
              },
              {
                key: 'roles',
                label: 'Roles',
                render: (row) => (
                  <div className="badge-list">
                    {row.roles.map((role) => (
                      <Badge key={role}>{role}</Badge>
                    ))}
                  </div>
                ),
              },
              {
                key: 'actions',
                label: '',
                render: (row) => (
                  <div className="table-actions">
                    <Button
                      size="sm"
                      icon={<UserCog size={15} />}
                      loading={mutation.isPending && mutation.variables?.userId === row.id}
                      onClick={() =>
                        mutation.mutate({ userId: row.id, role: selectedRole, action: 'assign' })
                      }
                    >
                      Assign
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      loading={mutation.isPending && mutation.variables?.userId === row.id}
                      onClick={() =>
                        mutation.mutate({ userId: row.id, role: selectedRole, action: 'revoke' })
                      }
                    >
                      Revoke
                    </Button>
                  </div>
                ),
              },
            ]}
          />
          {query.data && query.data.totalPages > 1 && (
            <Pagination page={page} pageCount={query.data.totalPages} onPageChange={setPage} />
          )}
        </QueryState>
        {mutation.error && (
          <p className="form-error" role="alert">
            {mutation.error instanceof Error ? mutation.error.message : 'Role change failed.'}
          </p>
        )}
      </Card>
    </>
  );
}
