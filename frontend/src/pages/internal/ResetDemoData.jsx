import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, Button, Input, PageLoading, EmptyState } from '../../components/ui';

const CONFIRM_PHRASE = 'DELETE DEMO DATA';

export default function ResetDemoData() {
  const { user } = useAuth();
  const [preview, setPreview] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [confirmText, setConfirmText] = useState('');
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState('');
  const [result, setResult] = useState(null);

  const load = useCallback(() => {
    setLoadError('');
    api.get('/admin/reset-demo-data/preview').then((res) => setPreview(res.data)).catch((err) => {
      setLoadError(err?.response?.data?.error || 'Could not load a preview. Please try again.');
    });
  }, []);

  useEffect(load, [load]);

  if (user.role !== 'roskyro_admin') {
    return (
      <Card className="p-10 text-center max-w-md mx-auto">
        <p className="text-lg font-bold text-gray-900">Super admin access only</p>
        <p className="text-sm text-gray-500 mt-2">
          Resetting demo data can only be done by a ROSKYRO super admin account.
        </p>
      </Card>
    );
  }

  async function runReset() {
    setRunning(true);
    setRunError('');
    try {
      const res = await api.post('/admin/reset-demo-data/run', { confirm: confirmText });
      setResult(res.data);
      setConfirmText('');
    } catch (err) {
      setRunError(err?.response?.data?.error || 'Could not run the reset. Nothing was deleted.');
    } finally {
      setRunning(false);
    }
  }

  if (loadError && !preview) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{loadError}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!preview) return <PageLoading />;

  if (result) {
    const nonZero = result.results.filter((r) => r.deleted > 0);
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Reset Demo Data</h1>
        </div>
        <Card className="p-6 bg-emerald-50 border-emerald-100">
          <p className="text-lg font-bold text-emerald-900">Done — {result.totalDeleted} demo records removed.</p>
          <p className="text-sm text-emerald-700 mt-1">
            The platform is now a clean slate. Pricing, payment settings, and your ROSKYRO team accounts were left untouched.
          </p>
        </Card>
        <Card>
          <CardHeader title="What was removed" />
          <div className="px-5 pb-5">
            {nonZero.length === 0 ? (
              <EmptyState title="Nothing to remove" subtitle="The platform was already clean." />
            ) : (
              <div className="divide-y divide-gray-100">
                {nonZero.map((r) => (
                  <div key={r.label} className="flex items-center justify-between py-2 text-sm">
                    <span className="text-gray-700">{r.label}</span>
                    <span className="font-semibold text-gray-900">{r.deleted}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>
    );
  }

  const nonZeroPreview = preview.items.filter((i) => i.count > 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Reset Demo Data</h1>
        <p className="text-sm text-gray-500 mt-1">
          Super admin only — permanently clears every seeded/demo business record (businesses, partners, referrals,
          subscriptions, patients, appointments, tasks, etc.) so you can onboard real clients on a clean slate.
        </p>
      </div>

      <Card className="p-4 bg-amber-50 border-amber-100">
        <p className="text-sm text-amber-800">
          <span className="font-semibold">This cannot be undone.</span> {preview.preserved}
        </p>
      </Card>

      <Card>
        <CardHeader
          title={`${preview.total} records will be permanently deleted`}
          subtitle={preview.total === 0 ? 'The platform is already clean — nothing to reset.' : 'Review the breakdown below before confirming.'}
          action={<Button size="sm" variant="secondary" onClick={load}>Refresh</Button>}
        />
        <div className="px-5 pb-5">
          {nonZeroPreview.length === 0 ? (
            <EmptyState title="Nothing to delete" subtitle="No demo data found." />
          ) : (
            <div className="divide-y divide-gray-100">
              {nonZeroPreview.map((i) => (
                <div key={i.label} className="flex items-center justify-between py-2 text-sm">
                  <span className="text-gray-700">{i.label}</span>
                  <span className="font-semibold text-gray-900">{i.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      {preview.total > 0 && (
        <Card className="p-5">
          <p className="text-sm font-medium text-gray-700">
            Type <span className="font-mono font-bold text-rose-700">{CONFIRM_PHRASE}</span> below to confirm.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={CONFIRM_PHRASE}
              className="max-w-[260px]"
            />
            <Button
              variant="danger"
              disabled={confirmText.trim() !== CONFIRM_PHRASE || running}
              onClick={runReset}
            >
              {running ? 'Deleting…' : 'Permanently Delete Demo Data'}
            </Button>
          </div>
          {runError && <p className="text-sm text-rose-600 mt-3">{runError}</p>}
        </Card>
      )}
    </div>
  );
}
