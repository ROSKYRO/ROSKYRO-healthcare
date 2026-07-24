import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, Badge, Button, Input, PageLoading, EmptyState, formatDateTime } from '../../components/ui';

const STATUS_FLOW = { waiting: 'in_consultation', in_consultation: 'done' };
const STATUS_LABEL = { waiting: 'Call In', in_consultation: 'Mark Done' };

export default function Queue() {
  const [queue, setQueue] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [patientName, setPatientName] = useState('');
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    api.get('/queue').then((res) => setQueue(res.data.queue)).catch((err) => { if (err?.response?.status === 402) setBlocked(true); });
  }, []);

  useEffect(load, [load]);

  async function checkIn(e) {
    e.preventDefault();
    if (!patientName.trim()) return;
    await api.post('/queue', { patientName });
    setPatientName('');
    load();
  }

  async function advance(entry) {
    const next = STATUS_FLOW[entry.status];
    if (!next) return;
    setBusyId(entry.id);
    try {
      await api.patch(`/queue/${entry.id}`, { status: next });
      load();
    } finally {
      setBusyId(null);
    }
  }

  async function noShow(entry) {
    setBusyId(entry.id);
    try {
      await api.patch(`/queue/${entry.id}`, { status: 'no_show' });
      load();
    } finally {
      setBusyId(null);
    }
  }

  if (blocked) return <UpgradePrompt pillar="manage" />;
  if (!queue) return <PageLoading />;

  const active = queue.filter((q) => ['waiting', 'in_consultation'].includes(q.status));
  const finished = queue.filter((q) => ['done', 'no_show', 'cancelled'].includes(q.status));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Queue Management</h1>
        <p className="text-sm text-gray-500 mt-1">Today's walk-in token queue.</p>
      </div>

      <Card className="p-5">
        <form onSubmit={checkIn} className="flex gap-3">
          <Input placeholder="Patient name to check in…" value={patientName} onChange={(e) => setPatientName(e.target.value)} className="flex-1" />
          <Button type="submit">Check In</Button>
        </form>
      </Card>

      <Card>
        <div className="px-5 pt-5"><h3 className="text-base font-semibold text-gray-900">Live Queue</h3></div>
        <div className="px-5 pb-5">
          {active.length === 0 ? <EmptyState title="No one waiting right now." /> : (
            <div className="divide-y divide-gray-100">
              {active.map((entry) => (
                <div key={entry.id} className="py-3 flex items-center justify-between text-sm">
                  <div className="flex items-center gap-4">
                    <span className="h-8 w-8 rounded-full bg-brand-50 text-brand-700 font-bold flex items-center justify-center">{entry.token_number}</span>
                    <div>
                      <p className="font-medium text-gray-900">{entry.patient_name}</p>
                      <p className="text-xs text-gray-400">Checked in {formatDateTime(entry.checked_in_at)}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={entry.status}>{entry.status.replace(/_/g, ' ')}</Badge>
                    <Button size="sm" disabled={busyId === entry.id} onClick={() => advance(entry)}>{STATUS_LABEL[entry.status]}</Button>
                    {entry.status === 'waiting' && <Button size="sm" variant="ghost" disabled={busyId === entry.id} onClick={() => noShow(entry)}>No-show</Button>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      {finished.length > 0 && (
        <Card>
          <div className="px-5 pt-5"><h3 className="text-base font-semibold text-gray-900">Completed Today</h3></div>
          <div className="px-5 pb-5 divide-y divide-gray-100">
            {finished.map((entry) => (
              <div key={entry.id} className="py-2.5 flex items-center justify-between text-sm">
                <span>{entry.token_number}. {entry.patient_name}</span>
                <Badge tone={entry.status}>{entry.status.replace(/_/g, ' ')}</Badge>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
