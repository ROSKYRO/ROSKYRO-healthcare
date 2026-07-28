import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { Card, CardHeader, Table, Badge, Button, PageLoading, formatDateTime } from '../../components/ui';

export default function WhatsappQueue() {
  const [queue, setQueue] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    // Fixed: this never cleared a prior error at the start of a reload --
    // so after an initial failed load followed by a successful Retry, the
    // stale "Could not load..." banner kept rendering above the
    // now-successfully-loaded queue table, permanently misleading the ops
    // user into thinking the page is still broken. Every sibling internal
    // page's load() clears error first; this one didn't.
    setError('');
    api.get('/whatsapp/queue').then((res) => setQueue(res.data.queue)).catch(() => {
      setError('Could not load the WhatsApp queue. Please try again.');
    });
  }, []);

  useEffect(load, [load]);

  // "Send" opens the pre-filled wa.me chat in ROSKYRO's own logged-in
  // WhatsApp Web/Business session (see app/utils/whatsapp_sender.py) AND
  // marks it dispatched in the same click -- the ops user just has to
  // hit Enter in the WhatsApp tab that opens to actually send it.
  async function sendAndDispatch(message) {
    setBusyId(message.id);
    setError('');
    window.open(message.wa_link, '_blank', 'noopener,noreferrer');
    try {
      await api.post(`/whatsapp/queue/${message.id}/dispatch`);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not mark this message dispatched.');
    } finally {
      setBusyId(null);
    }
  }

  if (error && !queue) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!queue) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">WhatsApp Send Queue</h1>
        <p className="text-sm text-gray-500 mt-1">
          Har business ke patient-facing WhatsApp messages (referral updates + manual sends) yahan ek hi shared queue
          mein aate hain — kis bhi business ne, kisi bhi computer se banaya ho. Isliye ek hi ROSKYRO WhatsApp number
          (is computer par logged-in) se sabka kaam ho jaata hai, koi paid API nahi chahiye. "Send" click karne se
          WhatsApp pre-filled message ke saath khulega — bas Enter dabao, message chala jaayega.
        </p>
      </div>

      {error && <p className="text-sm text-rose-600 bg-rose-50 border border-rose-100 rounded-lg px-4 py-2">{error}</p>}

      <Card>
        <CardHeader
          title={`Pending (${queue.length})`}
          subtitle="Sabse purana pehle — koi bhi message peeche na chhoote."
        />
        <Table
          rows={queue}
          emptyMessage="Queue khali hai — koi pending WhatsApp message nahi."
          columns={[
            { key: 'org_name', header: 'Business', render: (m) => m.org_name || '—' },
            { key: 'patient_name', header: 'Patient', render: (m) => (
              <div>
                <p className="text-gray-900">{m.patient_name}</p>
                <p className="text-xs text-gray-400">{m.patient_phone}</p>
              </div>
            ) },
            { key: 'message', header: 'Message', render: (m) => (
              <p className="text-sm text-gray-700 max-w-md truncate" title={m.message}>{m.message}</p>
            ) },
            { key: 'status', header: 'Status', render: (m) => <Badge tone={m.status}>{m.status}</Badge> },
            { key: 'created_at', header: 'Queued', render: (m) => formatDateTime(m.created_at) },
            { key: 'actions', header: '', render: (m) => (
              !m.wa_link ? (
                <span className="text-xs text-rose-600">No valid phone — can't build a link</span>
              ) : (
                <Button size="sm" disabled={busyId === m.id} onClick={() => sendAndDispatch(m)}>
                  {busyId === m.id ? '…' : '📲 Send via WhatsApp'}
                </Button>
              )
            ) },
          ]}
        />
      </Card>
    </div>
  );
}
