import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, StatTile, Badge, PageLoading, EmptyState, Button, formatCurrency } from '../../components/ui';
import { BUSINESS_CATEGORY_LABELS } from '../../lib/businessTaxonomy';

// Fixed: price used to be a hardcoded literal per pillar ('14,999' /
// '9,999' / '4,999') baked straight into the bundle -- so the moment a
// super admin repriced a plan via internal/PricingManagement.jsx (which
// writes PATCH /plans/{code}), this Dashboard kept showing the OLD number
// forever, with no way to fix it short of a frontend redeploy. Same fix as
// Landing.jsx: static copy (emoji, name, tagline) stays here since that's
// genuinely content, not billing data; price now always comes live from
// GET /plans, matched by `code` -- there is exactly one place a plan's
// price can be set (Pricing Management), and every surface that shows a
// price reads from it live.
const PILLAR_UPSELL = {
  grow: { emoji: '\u{1F680}', name: 'GROW', tagline: 'Visibility, reviews, SEO, social & content — all managed for you.' },
  manage: { emoji: '\u{2699}\u{FE0F}', name: 'MANAGE', tagline: 'Patient CRM, appointments, queue, billing & WhatsApp.' },
  connect: { emoji: '\u{1F91D}', name: 'Networking Marketing', tagline: 'A verified network of trusted healthcare partners.' },
};

function UpsellCard({ pillar, price }) {
  const info = PILLAR_UPSELL[pillar];
  return (
    <Card className="p-5 border-dashed border-2 border-gray-200 bg-gray-50/50">
      <p className="text-2xl">{info.emoji}</p>
      <p className="font-semibold text-gray-900 mt-1">Activate {info.name}</p>
      <p className="text-sm text-gray-500 mt-1">{info.tagline}</p>
      <p className="text-sm font-semibold text-gray-700 mt-2">
        {price != null
          ? <>₹{Number(price).toLocaleString('en-IN')}/month <span className="font-normal text-gray-400">· Monthly Subscription</span></>
          : <Link to="/app/plans" className="text-brand-700 font-medium">See pricing →</Link>}
      </p>
      <Link to="/app/plans"><Button size="sm" className="mt-3">Activate {info.name}</Button></Link>
    </Card>
  );
}

export default function CustomerDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [priceByCode, setPriceByCode] = useState({});

  const load = () => {
    setError('');
    // Previously no .catch -- this is the very first page every customer
    // user lands on after logging in, so a transient network/5xx error
    // here meant a permanent loading spinner with no way to recover short
    // of a hard refresh.
    api.get('/dashboard/customer').then((res) => setData(res.data)).catch(() => {
      setError('Could not load your dashboard. Please try again.');
    });
  };

  useEffect(load, []);

  useEffect(() => {
    // Best-effort only -- same as Landing.jsx: if this fails, the upsell
    // cards below just fall back to "See pricing →" instead of showing a
    // stale/fake number.
    api.get('/plans').then((res) => {
      const map = {};
      for (const p of res.data.plans || []) map[p.code] = p.monthly_price;
      setPriceByCode(map);
    }).catch(() => {});
  }, []);

  if (error) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }
  if (!data) return <PageLoading />;
  const pillars = data.activePillars || [];
  const hasGrow = pillars.includes('grow');
  const hasManage = pillars.includes('manage');
  const hasConnect = pillars.includes('connect');
  const hasAnyPillar = pillars.length > 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Welcome back, {user.name.split(' ')[0]}</h1>
        <p className="text-sm text-gray-500 mt-1 flex items-center gap-2 flex-wrap">
          Here's how {user.orgName} is doing right now.
          {user.businessCategory && (
            <Badge tone="slate">{BUSINESS_CATEGORY_LABELS[user.businessCategory] || user.businessCategory}</Badge>
          )}
        </p>
      </div>

      {!hasAnyPillar && (
        <Card className="p-6 bg-brand-50 border-brand-100">
          <p className="font-semibold text-gray-900">You haven't activated a ROSKYRO pillar yet</p>
          <p className="text-sm text-gray-600 mt-1">Pick GROW, MANAGE, Networking Marketing — or bundle all three and save — to start seeing real data here.</p>
          <Link to="/app/plans"><Button className="mt-4">View plans</Button></Link>
        </Card>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile label="Today's Appointments" value={data.todaysAppointments.length} icon={"\u{1F4C5}"} tone="brand" />
        <StatTile label="New Patients (Month)" value={data.newPatientsThisMonth} icon={"\u{1F9D1}"} tone="blue" />
        <StatTile label="Revenue (Month)" value={formatCurrency(data.revenueThisMonth)} icon={"\u{20B9}"} tone="brand" />
        <StatTile
          label="Visibility Score"
          value={hasGrow ? (data.visibilityScore ? `${data.visibilityScore.score}/100` : '—') : 'GROW only'}
          sub={hasGrow && data.visibilityScore ? `As of ${data.visibilityScore.period_month}` : !hasGrow ? 'Activate GROW to unlock' : 'Not yet calculated'}
          icon={"\u{1F441}\u{FE0F}"}
          tone="amber"
        />
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <Card className="md:col-span-2">
          <CardHeader title="Today's Appointments" subtitle="Live from your schedule" />
          <div className="px-5 pb-5">
            {data.todaysAppointments.length === 0 ? (
              <EmptyState title="No appointments scheduled for today." />
            ) : (
              <div className="divide-y divide-gray-100">
                {data.todaysAppointments.map((a) => (
                  <div key={a.id} className="py-3 flex items-center justify-between text-sm">
                    <div>
                      <p className="font-medium text-gray-900">{a.patient_name}</p>
                      <p className="text-gray-400">{a.appointment_time?.slice(0, 5)} · {a.doctor_name || 'Unassigned'}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* A QR self-booking's payment is patient-self-reported until this
                          clinic's own front desk verifies the UPI payment and confirms it
                          (see BookingSettings.jsx's QR Bookings table) -- flag it here too
                          so it doesn't read as a normal confirmed appointment in the
                          meantime. */}
                      {a.payment_status === 'pending' && <Badge tone="pending">payment pending</Badge>}
                      <Badge tone={a.status}>{a.status}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>

        {hasGrow ? (
          <Card>
            <CardHeader title="Your Platforms" action={<Link to="/app/growth"><Button size="sm" variant="secondary">Open</Button></Link>} />
            <div className="px-5 pb-5">
              {!data.platformLinks || data.platformLinks.length === 0 ? (
                <EmptyState title="Your ROSKYRO team will add these soon." />
              ) : (
                <div className="space-y-2">
                  {data.platformLinks.slice(0, 3).map((l) => (
                    <a
                      key={l.id}
                      href={l.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-between text-sm rounded-lg border border-gray-200 px-3 py-2 hover:bg-gray-50 transition"
                    >
                      <span className="font-medium text-gray-700">{l.label}</span>
                      <span className="text-brand-700 text-xs font-medium">Open ↗</span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          </Card>
        ) : <UpsellCard pillar="grow" price={priceByCode.grow} />}
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <Card>
          <CardHeader
            title="Pending Approvals"
            subtitle="AI-drafted, human-reviewed — waiting on you"
            action={data.pendingApprovals.length > 0 && <Link to="/app/approvals"><Button size="sm" variant="secondary">Review all</Button></Link>}
          />
          <div className="px-5 pb-5">
            {data.pendingApprovals.length === 0 ? (
              <EmptyState title="Nothing waiting on your approval." subtitle="You're all caught up." />
            ) : (
              <div className="space-y-3">
                {data.pendingApprovals.slice(0, 4).map((a) => (
                  <div key={a.id} className="text-sm">
                    <p className="font-medium text-gray-900">{a.title}</p>
                    <p className="text-gray-400 text-xs mt-0.5">{a.approval_type.replace(/_/g, ' ')}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>

        {hasConnect ? (
          <Card>
            <CardHeader title="Referral Network Activity" subtitle="Referrals sent through ROSKYRO" action={<Link to="/app/referrals"><Button size="sm" variant="secondary">Open</Button></Link>} />
            <div className="px-5 pb-5">
              {!data.referralsSummary || data.referralsSummary.length === 0 ? (
                <EmptyState title="No referrals yet." subtitle="Send your first referral to a trusted partner." />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {data.referralsSummary.map((r) => (
                    <Badge key={r.status} tone={r.status}>{r.status} · {r.count}</Badge>
                  ))}
                </div>
              )}
            </div>
          </Card>
        ) : <UpsellCard pillar="connect" price={priceByCode.connect} />}
      </div>

      {hasManage && data.manageSnapshot && (
        <Card>
          <CardHeader title="Today's Operations" subtitle="MANAGE pillar snapshot" />
          <div className="px-5 pb-5 grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-gray-400">Patients waiting in queue</p>
              <p className="text-xl font-bold text-gray-900">{data.manageSnapshot.queueWaiting}</p>
              <Link to="/app/queue" className="text-brand-700 text-xs font-medium">Open queue →</Link>
            </div>
            <div>
              <p className="text-gray-400">Follow-ups due</p>
              <p className="text-xl font-bold text-gray-900">{data.manageSnapshot.followupsDue}</p>
              <Link to="/app/followups" className="text-brand-700 text-xs font-medium">Open follow-ups →</Link>
            </div>
            <div>
              <p className="text-gray-400">Unpaid invoices</p>
              <p className="text-xl font-bold text-gray-900">{data.manageSnapshot.unpaidInvoices} <span className="text-xs font-normal text-gray-400">({formatCurrency(data.manageSnapshot.unpaidInvoicesTotal)})</span></p>
              <Link to="/app/billing" className="text-brand-700 text-xs font-medium">Open billing →</Link>
            </div>
          </div>
        </Card>
      )}
      {!hasManage && <UpsellCard pillar="manage" price={priceByCode.manage} />}

      {hasGrow && (
        <div className="grid md:grid-cols-2 gap-6">
          <Card>
            <CardHeader title="Marketing Performance" subtitle="This month, by channel" />
            <div className="px-5 pb-5 space-y-3">
              {data.marketingPerformance.length === 0 ? (
                <EmptyState title="Marketing numbers will appear once your first campaign reports in." />
              ) : (
                data.marketingPerformance.map((m) => (
                  <div key={m.channel} className="flex items-center justify-between text-sm">
                    <span className="font-medium text-gray-700 capitalize">{m.channel.replace(/_/g, ' ')}</span>
                    <span className="text-gray-500">{m.impressions} impressions · {m.clicks} clicks · {m.leads} leads</span>
                  </div>
                ))
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Monthly Growth Report" subtitle={data.latestMonthlyReport?.period_month} action={<Link to="/app/reports"><Button size="sm" variant="secondary">All reports</Button></Link>} />
            <div className="px-5 pb-5">
              {!data.latestMonthlyReport ? (
                <EmptyState title="Your first monthly report is being prepared." />
              ) : (
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><p className="text-gray-400">New patients</p><p className="font-semibold text-gray-900">{data.latestMonthlyReport.summary?.newPatients ?? '—'}</p></div>
                  <div><p className="text-gray-400">Revenue growth</p><p className="font-semibold text-gray-900">{data.latestMonthlyReport.summary?.revenueGrowthPct ?? '—'}%</p></div>
                  <div><p className="text-gray-400">Reviews gained</p><p className="font-semibold text-gray-900">{data.latestMonthlyReport.summary?.reviewsGained ?? '—'}</p></div>
                  <div><p className="text-gray-400">Referrals sent</p><p className="font-semibold text-gray-900">{data.latestMonthlyReport.summary?.referralsSent ?? '—'}</p></div>
                </div>
              )}
            </div>
          </Card>
        </div>
      )}

      <p className="text-xs text-gray-400 text-center pt-4">Completed work this month: {data.completedWorkThisMonth} tasks handled by your ROSKYRO team.</p>
    </div>
  );
}
