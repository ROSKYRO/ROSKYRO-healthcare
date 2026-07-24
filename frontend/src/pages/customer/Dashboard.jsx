import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, StatTile, Badge, PageLoading, EmptyState, Button, formatCurrency } from '../../components/ui';

const PILLAR_UPSELL = {
  grow: { emoji: '\u{1F680}', name: 'GROW', price: '14,999', tagline: 'Visibility, reviews, SEO, social & content — all managed for you.' },
  manage: { emoji: '\u{2699}\u{FE0F}', name: 'MANAGE', price: '9,999', tagline: 'Patient CRM, appointments, queue, billing & WhatsApp.' },
  connect: { emoji: '\u{1F91D}', name: 'CONNECT', price: '4,999', tagline: 'A verified network of trusted healthcare partners.' },
};

function UpsellCard({ pillar }) {
  const info = PILLAR_UPSELL[pillar];
  return (
    <Card className="p-5 border-dashed border-2 border-gray-200 bg-gray-50/50">
      <p className="text-2xl">{info.emoji}</p>
      <p className="font-semibold text-gray-900 mt-1">Activate {info.name}</p>
      <p className="text-sm text-gray-500 mt-1">{info.tagline}</p>
      <p className="text-sm font-semibold text-gray-700 mt-2">₹{info.price}/month <span className="font-normal text-gray-400">· Monthly Subscription</span></p>
      <Link to="/app/plans"><Button size="sm" className="mt-3">Activate {info.name}</Button></Link>
    </Card>
  );
}

export default function CustomerDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get('/dashboard/customer').then((res) => setData(res.data));
  }, []);

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
        <p className="text-sm text-gray-500 mt-1">Here's how {user.orgName} is doing right now.</p>
      </div>

      {!hasAnyPillar && (
        <Card className="p-6 bg-brand-50 border-brand-100">
          <p className="font-semibold text-gray-900">You haven't activated a ROSKYRO pillar yet</p>
          <p className="text-sm text-gray-600 mt-1">Pick GROW, MANAGE, CONNECT — or bundle all three and save — to start seeing real data here.</p>
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
                    <Badge tone={a.status}>{a.status}</Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>

        {hasGrow ? (
          <Card>
            <CardHeader title="Google Reviews" />
            <div className="px-5 pb-5">
              <p className="text-3xl font-bold text-gray-900">{data.reviews.average || '—'} <span className="text-base font-normal text-gray-400">/ 5</span></p>
              <p className="text-sm text-gray-500 mt-1">{data.reviews.total} total reviews</p>
              <Link to="/app/reviews" className="text-sm text-brand-700 font-medium mt-3 inline-block">View all reviews →</Link>
            </div>
          </Card>
        ) : <UpsellCard pillar="grow" />}
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
        ) : <UpsellCard pillar="connect" />}
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
      {!hasManage && <UpsellCard pillar="manage" />}

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
