import { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../../lib/api';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, CardHeader, Badge, Button, PageLoading, EmptyState, formatDate, formatDateTime, formatCurrency } from '../../components/ui';

export default function PatientDetail() {
  const { id } = useParams();
  const [detail, setDetail] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setError('');
    api.get(`/patients/${id}`).then((res) => setDetail(res.data)).catch((err) => {
      if (err?.response?.status === 402) setBlocked(true);
      else setError('Could not load this patient. Please try again.');
    });
  }, [id]);

  useEffect(load, [load]);

  if (blocked) return <UpgradePrompt pillar="manage" />;

  if (error && !detail) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!detail) return <PageLoading />;
  const { patient, appointments, followups, invoices, whatsapp } = detail;

  return (
    <div className="space-y-6">
      <div>
        <Link to="/app/patients" className="text-sm text-brand-700">← Back to Patient CRM</Link>
        <h1 className="text-2xl font-bold text-gray-900 mt-1">{patient.name}</h1>
        <p className="text-sm text-gray-500 mt-1">{patient.phone} {patient.email ? `· ${patient.email}` : ''}</p>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="md:col-span-2 space-y-6">
          <Card>
            <CardHeader title="Visit History" />
            <div className="px-5 pb-5">
              {appointments.length === 0 ? <EmptyState title="No visits recorded yet." /> : (
                <div className="divide-y divide-gray-100">
                  {appointments.map((a) => (
                    <div key={a.id} className="py-2.5 flex items-center justify-between text-sm">
                      <span>{formatDate(a.appointment_date)} · {a.doctor_name || 'Unassigned'}</span>
                      <Badge tone={a.status}>{a.status}</Badge>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Follow-ups" />
            <div className="px-5 pb-5">
              {followups.length === 0 ? <EmptyState title="No follow-ups scheduled." /> : (
                <div className="divide-y divide-gray-100">
                  {followups.map((f) => (
                    <div key={f.id} className="py-2.5 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-gray-800">{f.reason}</span>
                        <Badge tone={f.status}>{f.status}</Badge>
                      </div>
                      <p className="text-xs text-gray-400">Due {formatDate(f.due_date)}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="WhatsApp History" />
            <div className="px-5 pb-5">
              {whatsapp.length === 0 ? <EmptyState title="No messages sent yet." /> : (
                <div className="space-y-3">
                  {whatsapp.map((w) => (
                    <div key={w.id} className="bg-gray-50 rounded-lg p-3 text-sm">
                      <p className="text-gray-700">{w.message}</p>
                      <p className="text-xs text-gray-400 mt-1">{formatDateTime(w.created_at)} · <Badge tone="slate">{w.status}</Badge></p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="p-5">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Patient Summary</p>
            <p className="text-sm text-gray-900 mt-2">{patient.age ? `${patient.age} yrs` : '—'} {patient.gender}</p>
            <p className="text-sm text-gray-500 mt-1">Total visits: {patient.total_visits}</p>
            <p className="text-sm text-gray-500">Lifetime value: {formatCurrency(patient.lifetime_value)}</p>
            {patient.notes && <p className="text-sm text-gray-600 mt-3 border-t border-gray-100 pt-3">{patient.notes}</p>}
          </Card>

          <Card>
            <CardHeader title="Invoices" />
            <div className="px-5 pb-5">
              {invoices.length === 0 ? <EmptyState title="No invoices yet." /> : (
                <div className="divide-y divide-gray-100">
                  {invoices.map((inv) => (
                    <div key={inv.id} className="py-2.5 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-gray-800">{inv.invoice_number}</span>
                        <Badge tone={inv.status}>{inv.status}</Badge>
                      </div>
                      <p className="text-xs text-gray-400">{formatCurrency(inv.total)}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
