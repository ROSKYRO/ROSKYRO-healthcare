import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, Badge, Button, Input, PageLoading, EmptyState, formatDateTime } from '../../components/ui';

function randomPassword() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';
  let out = '';
  for (let i = 0; i < 10; i++) out += chars[Math.floor(Math.random() * chars.length)];
  return out;
}

function RequestRow({ req, onResolved }) {
  const [newPassword, setNewPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  async function resolve() {
    if (newPassword.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await api.post(`/password-resets/${req.id}/resolve`, { newPassword });
      // Deliberately do NOT reload the list here -- reloading now would
      // move this row into "Handled" and unmount it before the admin has
      // actually read/copied the password they need to relay by hand.
      // The list only refreshes once they've dismissed this box below.
      setResult(newPassword);
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not reset this password.');
    } finally {
      setBusy(false);
    }
  }

  async function dismiss() {
    setBusy(true);
    try {
      await api.post(`/password-resets/${req.id}/dismiss`);
      onResolved();
    } finally {
      setBusy(false);
    }
  }

  if (req.status !== 'pending') {
    return (
      <div className="py-3 flex items-center justify-between text-sm">
        <div>
          <p className="text-gray-800">{req.user_name} <span className="text-gray-400">({req.user_role})</span></p>
          <p className="text-xs text-gray-400">{req.org_name || 'ROSKYRO internal'} · {req.user_phone || req.user_email}</p>
        </div>
        <Badge tone={req.status === 'resolved' ? 'verified' : 'slate'}>{req.status}</Badge>
      </div>
    );
  }

  return (
    <div className="py-4 border-b border-gray-100 last:border-0">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-semibold text-gray-900">{req.user_name} <span className="text-xs font-normal text-gray-400">({req.user_role})</span></p>
          <p className="text-xs text-gray-500 mt-0.5">{req.org_name || 'ROSKYRO internal'}</p>
          <p className="text-xs text-gray-500 mt-0.5">📱 {req.user_phone || '—'} · ✉️ {req.user_email || '—'}</p>
          {req.note && <p className="text-xs text-gray-500 mt-1 italic">"{req.note}"</p>}
          <p className="text-xs text-gray-400 mt-1">Requested {formatDateTime(req.requested_at)}</p>
        </div>
        <Badge tone="pending">pending</Badge>
      </div>

      {result ? (
        <div className="mt-3 bg-emerald-50 border border-emerald-100 rounded-lg p-3 text-sm">
          <p className="text-emerald-800 font-semibold">Password reset. Tell {req.user_name} directly (call/WhatsApp):</p>
          <p className="font-mono text-lg text-emerald-900 mt-1 select-all">{result}</p>
          <p className="text-xs text-emerald-700 mt-2">This won't be shown again — copy or note it down first.</p>
          <Button size="sm" className="mt-3" onClick={onResolved}>
            Done — I've told them
          </Button>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <Input
            label="New password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="Type or generate"
            className="max-w-[220px]"
          />
          <Button variant="secondary" size="sm" onClick={() => setNewPassword(randomPassword())} disabled={busy}>
            Generate
          </Button>
          <Button size="sm" onClick={resolve} disabled={busy}>
            {busy ? 'Saving…' : 'Reset Password'}
          </Button>
          <Button variant="ghost" size="sm" onClick={dismiss} disabled={busy}>
            Dismiss
          </Button>
        </div>
      )}
      {error && <p className="text-sm text-rose-600 mt-2">{error}</p>}
    </div>
  );
}

export default function PasswordRequests() {
  const { user } = useAuth();
  const [requests, setRequests] = useState(null);

  const load = useCallback(() => {
    api.get('/password-resets').then((res) => setRequests(res.data.requests));
  }, []);

  useEffect(load, [load]);

  if (user.role !== 'roskyro_admin') {
    return (
      <Card className="p-10 text-center max-w-md mx-auto">
        <p className="text-lg font-bold text-gray-900">Super admin access only</p>
        <p className="text-sm text-gray-500 mt-2">
          Password reset requests can only be handled by a ROSKYRO super admin account.
        </p>
      </Card>
    );
  }

  if (!requests) return <PageLoading />;

  const pending = requests.filter((r) => r.status === 'pending');
  const handled = requests.filter((r) => r.status !== 'pending');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Password Requests</h1>
        <p className="text-sm text-gray-500 mt-1">
          Super admin only — there's no self-service reset link. When someone forgets their password, they submit a
          request from the login page; verify it's really them, then set a new password by hand and tell them
          directly.
        </p>
      </div>

      <Card>
        <CardHeader title={`Pending (${pending.length})`} />
        <div className="px-5 pb-5">
          {pending.length === 0 ? (
            <EmptyState title="No pending requests" subtitle="Nothing waiting on you right now." />
          ) : (
            pending.map((r) => <RequestRow key={r.id} req={r} onResolved={load} />)
          )}
        </div>
      </Card>

      {handled.length > 0 && (
        <Card>
          <CardHeader title="Handled" subtitle="Resolved or dismissed requests" />
          <div className="px-5 pb-5 divide-y divide-gray-100">
            {handled.map((r) => <RequestRow key={r.id} req={r} onResolved={load} />)}
          </div>
        </Card>
      )}
    </div>
  );
}
