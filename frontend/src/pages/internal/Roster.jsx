import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { Card, Table, Badge, Button, PageLoading } from '../../components/ui';

export default function Roster() {
  const [roster, setRoster] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setError('');
    api.get('/tasks/team/roster').then((res) => setRoster(res.data.roster)).catch(() => {
      setError('Could not load the team roster. Please try again.');
    });
  }, []);

  useEffect(load, [load]);

  if (error && !roster) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!roster) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Team Roster</h1>
        <p className="text-sm text-gray-500 mt-1">Workload and SLA health across the ROSKYRO internal team.</p>
      </div>

      <Card>
        <Table
          rows={roster}
          columns={[
            { key: 'name', header: 'Name' },
            { key: 'role', header: 'Role', render: (r) => <Badge tone="slate">{r.role.replace('roskyro_', '').replace(/_/g, ' ')}</Badge> },
            { key: 'open_tasks', header: 'Open Tasks' },
            { key: 'overdue_tasks', header: 'Overdue', render: (r) => (
              <span className={r.overdue_tasks > 0 ? 'text-rose-600 font-semibold' : ''}>{r.overdue_tasks}</span>
            ) },
            { key: 'completed_tasks', header: 'Completed' },
          ]}
        />
      </Card>
    </div>
  );
}
