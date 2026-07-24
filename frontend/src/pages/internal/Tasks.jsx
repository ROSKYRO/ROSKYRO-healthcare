import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { Card, Table, Badge, Button, Select, PageLoading, formatDateTime } from '../../components/ui';

const ROLES = [
  'roskyro_admin', 'roskyro_ops_manager', 'roskyro_growth_expert', 'roskyro_content_specialist',
  'roskyro_seo_specialist', 'roskyro_gbp_specialist', 'roskyro_review_manager', 'roskyro_crm_executive',
  'roskyro_support_executive', 'roskyro_quality_reviewer',
];

export default function Tasks() {
  const { user } = useAuth();
  const [scope, setScope] = useState('mine');
  const [role, setRole] = useState(user.role);
  const [status, setStatus] = useState('');
  const [tasks, setTasks] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    const params = { status: status || undefined };
    if (scope === 'mine') params.mine = 'true';
    else params.role = role;
    api.get('/tasks', { params }).then((res) => setTasks(res.data.tasks));
  }, [scope, role, status]);

  useEffect(load, [load]);

  async function claim(id) {
    setBusyId(id);
    try {
      await api.patch(`/tasks/${id}`, { assignedTo: user.id, status: 'in_progress' });
      load();
    } finally {
      setBusyId(null);
    }
  }

  async function complete(id) {
    setBusyId(id);
    try {
      await api.patch(`/tasks/${id}`, { status: 'done' });
      load();
    } finally {
      setBusyId(null);
    }
  }

  if (!tasks) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Task Queue</h1>
        <p className="text-sm text-gray-500 mt-1">SLA-tracked work across every ROSKYRO team role.</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select value={scope} onChange={(e) => setScope(e.target.value)} className="max-w-[180px]">
          <option value="mine">My Queue</option>
          <option value="role">By Role</option>
        </Select>
        {scope === 'role' && (
          <Select value={role} onChange={(e) => setRole(e.target.value)} className="max-w-[240px]">
            {ROLES.map((r) => <option key={r} value={r}>{r.replace('roskyro_', '').replace(/_/g, ' ')}</option>)}
          </Select>
        )}
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="max-w-[180px]">
          <option value="">All statuses</option>
          {['pending', 'in_progress', 'in_review', 'done', 'blocked'].map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
        </Select>
      </div>

      <Card>
        <Table
          rows={tasks}
          emptyMessage="No tasks in this view."
          columns={[
            { key: 'title', header: 'Task' },
            { key: 'org_name', header: 'Business', render: (r) => r.org_name || '—' },
            { key: 'priority', header: 'Priority', render: (r) => <Badge tone={r.priority}>{r.priority}</Badge> },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'sla_due_at', header: 'SLA Due', render: (r) => (
              <span className={r.is_overdue ? 'text-rose-600 font-medium' : ''}>{formatDateTime(r.sla_due_at)}</span>
            ) },
            { key: 'assigned_to_name', header: 'Assigned To', render: (r) => r.assigned_to_name || '— unassigned —' },
            { key: 'actions', header: '', render: (r) => (
              <div className="flex gap-2">
                {!r.assigned_to && r.status !== 'done' && (
                  <Button size="sm" variant="secondary" disabled={busyId === r.id} onClick={() => claim(r.id)}>Claim</Button>
                )}
                {r.status !== 'done' && (
                  <Button size="sm" disabled={busyId === r.id} onClick={() => complete(r.id)}>Mark Done</Button>
                )}
              </div>
            ) },
          ]}
        />
      </Card>
    </div>
  );
}
