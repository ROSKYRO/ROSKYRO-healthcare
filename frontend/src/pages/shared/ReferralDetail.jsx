import { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, Badge, Button, Input, PageLoading, Textarea, formatDateTime } from '../../components/ui';

const STEP_LABELS = {
  draft: 'Referral Created', pending_review: 'Held for ROSKYRO Review', sent: 'Sent to Partner',
  accepted: 'Partner Accepted', declined: 'Partner Declined', in_progress: 'Service In Progress',
  report_uploaded: 'Report Uploaded', completed: 'Completed', cancelled: 'Cancelled',
};

function availableActions(referral, user) {
  if (!referral) return [];
  const shell = user.appShell;
  const actions = [];
  const s = referral.status;

  if (shell === 'partner') {
    if (s === 'sent') actions.push({ status: 'accepted', label: 'Accept Referral', variant: 'primary' }, { status: 'declined', label: 'Decline', variant: 'danger' });
    if (s === 'accepted') actions.push({ status: 'in_progress', label: 'Mark In Progress', variant: 'primary' });
    if (s === 'in_progress') actions.push({ status: 'report_uploaded', label: 'Upload Report & Notify Doctor', variant: 'primary' });
    // Partner has serviced the patient and can close the referral out
    // themselves once they've paid ROSKYRO the Marketing Fee -- attaching a
    // payment reference here (see the field rendered below) records their
    // own "I've paid" claim in the same click, but it still only becomes
    // "Paid" once ROSKYRO independently confirms receipt (Wallet page).
    if (s === 'report_uploaded') actions.push({ status: 'completed', label: "Mark Completed — I've Paid ROSKYRO", variant: 'primary', needsPaymentReference: true });
  }
  if (shell === 'customer') {
    if (s === 'report_uploaded') actions.push({ status: 'completed', label: 'Mark Completed (report reviewed)', variant: 'primary' });
    if (['sent', 'pending_review'].includes(s)) actions.push({ status: 'cancelled', label: 'Cancel Referral', variant: 'danger' });
  }
  if (shell === 'internal') {
    if (s === 'pending_review') actions.push({ status: 'sent', label: 'Release to Partner', variant: 'primary' });
    if (s === 'sent') actions.push({ status: 'accepted', label: 'Force Accept', variant: 'secondary' }, { status: 'declined', label: 'Force Decline', variant: 'secondary' });
    if (s === 'in_progress') actions.push({ status: 'report_uploaded', label: 'Mark Report Uploaded', variant: 'secondary' });
    if (s === 'report_uploaded') actions.push({ status: 'completed', label: 'Force Complete', variant: 'secondary' });
    if (!['completed', 'cancelled', 'declined'].includes(s)) actions.push({ status: 'cancelled', label: 'Cancel', variant: 'ghost' });
  }
  return actions;
}

export default function ReferralDetail({ basePath }) {
  const { id } = useParams();
  const { user } = useAuth();
  const [detail, setDetail] = useState(null);
  const [note, setNote] = useState('');
  const [paymentReference, setPaymentReference] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    api.get(`/referrals/${id}`).then((res) => setDetail(res.data));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function doTransition(status, needsPaymentReference) {
    setBusy(true);
    setError('');
    try {
      const payload = { status, note: note || undefined };
      if (status === 'declined') payload.declineReason = note || 'Declined by partner';
      if (needsPaymentReference && paymentReference) payload.paymentReference = paymentReference;
      await api.post(`/referrals/${id}/transition`, payload);
      setNote('');
      setPaymentReference('');
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not update referral.');
    } finally {
      setBusy(false);
    }
  }

  if (!detail) return <PageLoading />;
  const { referral, history, followups, patient_notifications: patientNotifications = [] } = detail;
  const actions = availableActions(referral, user);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link to={basePath} className="text-sm text-brand-700">← Back</Link>
          <h1 className="text-2xl font-bold text-gray-900 mt-1">{referral.referral_code}</h1>
          <p className="text-sm text-gray-500 mt-1">{referral.patient_name} · {referral.service_requested}</p>
        </div>
        <Badge tone={referral.status}>{referral.status}</Badge>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="md:col-span-2 space-y-6">
          <Card>
            <CardHeader title="Referral Timeline" />
            <div className="px-5 pb-5">
              <ol className="relative border-l border-gray-200 ml-2">
                {history.map((h) => (
                  <li key={h.id} className="mb-5 ml-4">
                    <div className="absolute w-2.5 h-2.5 bg-brand-500 rounded-full -left-[5px] mt-1.5" />
                    <p className="text-sm font-medium text-gray-900">{STEP_LABELS[h.status] || h.status}</p>
                    <p className="text-xs text-gray-400">{formatDateTime(h.changed_at)}</p>
                    {h.note && <p className="text-xs text-gray-500 mt-1">{h.note}</p>}
                  </li>
                ))}
              </ol>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Patient Notifications"
              subtitle="Patient ka koi ROSKYRO login nahi hota — unhe WhatsApp par hi pata chalta hai ki kahan aur kise refer kiya gaya hai."
            />
            <div className="px-5 pb-5 divide-y divide-gray-100">
              {patientNotifications.length === 0 ? (
                <p className="text-sm text-gray-400 py-2">
                  {referral.patient_phone
                    ? 'Abhi tak koi WhatsApp update nahi bheja gaya.'
                    : 'Patient ka phone number file par nahi hai — WhatsApp update nahi bheja ja sakta.'}
                </p>
              ) : (
                patientNotifications.map((m) => (
                  <div key={m.id} className="py-2.5 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-emerald-700">✓ Sent to {m.patient_phone}</span>
                      <span className="text-xs text-gray-400">{formatDateTime(m.created_at)}</span>
                    </div>
                    <p className="text-gray-700 mt-1">{m.message}</p>
                  </div>
                ))
              )}
            </div>
          </Card>

          {followups.length > 0 && (
            <Card>
              <CardHeader title="Follow-ups" />
              <div className="px-5 pb-5 space-y-2">
                {followups.map((f) => (
                  <div key={f.id} className="text-sm">
                    <p className="text-gray-800">{f.note}</p>
                    <p className="text-xs text-gray-400">Due {f.due_date?.slice(0, 10)} · <Badge tone={f.status}>{f.status}</Badge></p>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card className="p-5">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Patient</p>
            <p className="text-sm text-gray-900 mt-1">{referral.patient_name}</p>
            <p className="text-sm text-gray-500">{referral.patient_phone || 'No phone on file'}</p>
            <p className="text-sm text-gray-500">{referral.patient_age ? `${referral.patient_age} yrs` : ''} {referral.patient_gender}</p>

            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mt-4">Referring Business</p>
            <p className="text-sm text-gray-900 mt-1">{referral.referring_org_name}</p>
            <p className="text-sm text-gray-500">{referral.referring_doctor_name}</p>

            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mt-4">Partner</p>
            <p className="text-sm text-gray-900 mt-1">{referral.partner_org_name}</p>

            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mt-4">Urgency</p>
            <Badge tone={referral.urgency === 'emergency' ? 'urgent' : referral.urgency === 'urgent' ? 'high' : 'normal'}>{referral.urgency}</Badge>

            {referral.clinical_notes && (
              <>
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mt-4">Clinical Notes</p>
                <p className="text-sm text-gray-600 mt-1">{referral.clinical_notes}</p>
              </>
            )}
          </Card>

          {actions.length > 0 && (
            <Card className="p-5">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Actions</p>
              <Textarea placeholder="Add a note (optional)" rows={2} value={note} onChange={(e) => setNote(e.target.value)} className="mb-3" />
              {actions.some((a) => a.needsPaymentReference) && (
                <Input
                  label="Payment Reference / UTR (optional)"
                  placeholder="e.g. UPI transaction ID"
                  value={paymentReference}
                  onChange={(e) => setPaymentReference(e.target.value)}
                  className="mb-3"
                />
              )}
              {error && <p className="text-sm text-rose-600 mb-2">{error}</p>}
              <div className="flex flex-col gap-2">
                {actions.map((a) => (
                  <Button key={a.status} variant={a.variant} disabled={busy} onClick={() => doTransition(a.status, a.needsPaymentReference)}>
                    {a.label}
                  </Button>
                ))}
              </div>
              {actions.some((a) => a.needsPaymentReference) && (
                <p className="text-xs text-gray-400 mt-2">
                  Payment reference dena optional hai, lekin dene se ROSKYRO ko confirm karna aasan ho jaata hai. Jab tak
                  ROSKYRO "Confirm Received" nahi karta, ye Marketing Fee dono taraf "Pending" hi dikhegi (Wallet page par dekh sakte hain).
                </p>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
