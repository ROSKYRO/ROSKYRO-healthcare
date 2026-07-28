import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../../lib/api';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, CardHeader, StatTile, Badge, Button, PageLoading, EmptyState } from '../../components/ui';

const CONTENT_TYPES = ['social_post', 'seo_content', 'gbp_update'];

export default function GrowthHub() {
  const [dash, setDash] = useState(null);
  const [approvals, setApprovals] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setError('');
    Promise.all([api.get('/dashboard/customer'), api.get('/approvals')])
      .then(([d, a]) => {
        if (!d.data.activePillars?.includes('grow')) { setBlocked(true); return; }
        setDash(d.data);
        setApprovals(a.data.approvals.filter((x) => CONTENT_TYPES.includes(x.approval_type)));
      })
      .catch((err) => {
        if (err?.response?.status === 402) setBlocked(true);
        else setError('Could not load the Growth Hub. Please try again.');
      });
  }, []);

  useEffect(load, [load]);

  if (blocked) return <UpgradePrompt pillar="grow" />;

  if (error && !dash) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!dash) return <PageLoading />;

  const breakdown = dash.visibilityScore?.breakdown || {};

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Growth Hub</h1>
        <p className="text-sm text-gray-500 mt-1">AI Visibility, GBP, Local SEO, Social Media and Content — one place for the GROW pillar.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile label="Visibility Score" value={dash.visibilityScore ? `${dash.visibilityScore.score}/100` : '—'} icon={"\u{1F441}\u{FE0F}"} tone="brand" />
        <StatTile label="GBP Completeness" value={breakdown.gbp_completeness ? `${breakdown.gbp_completeness}%` : '—'} icon={"\u{1F4CD}"} tone="blue" />
        <StatTile label="Review Velocity" value={breakdown.review_velocity ? `${breakdown.review_velocity}%` : '—'} icon={"\u{2B50}"} tone="amber" />
        <StatTile label="SEO Health" value={breakdown.seo_health ? `${breakdown.seo_health}%` : '—'} icon={"\u{1F50D}"} tone="slate" />
      </div>

      <Card>
        <CardHeader title="Marketing Performance" subtitle="This month, by channel" />
        <div className="px-5 pb-5 space-y-3">
          {dash.marketingPerformance.length === 0 ? <EmptyState title="Marketing numbers will appear once your first campaign reports in." /> : (
            dash.marketingPerformance.map((m) => (
              <div key={m.channel} className="flex items-center justify-between text-sm">
                <span className="font-medium text-gray-700 capitalize">{m.channel.replace(/_/g, ' ')}</span>
                <span className="text-gray-500">{m.impressions} impressions · {m.clicks} clicks · {m.leads} leads</span>
              </div>
            ))
          )}
        </div>
      </Card>

      <Card>
        <CardHeader title="Content Studio" subtitle="Social posts, SEO content and GBP updates — AI-drafted, human-reviewed" action={<Link to="/app/approvals"><Button size="sm" variant="secondary">Review all</Button></Link>} />
        <div className="px-5 pb-5">
          {approvals.length === 0 ? <EmptyState title="Nothing in the content pipeline right now." /> : (
            <div className="divide-y divide-gray-100">
              {approvals.map((a) => (
                <div key={a.id} className="py-2.5 flex items-center justify-between text-sm">
                  <div>
                    <p className="font-medium text-gray-900">{a.title}</p>
                    <p className="text-xs text-gray-400 capitalize">{a.approval_type.replace(/_/g, ' ')}</p>
                  </div>
                  <Badge tone={a.status}>{a.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      <div className="grid md:grid-cols-2 gap-6">
        <Card>
          <CardHeader title="Reviews" action={<Link to="/app/reviews"><Button size="sm" variant="secondary">Open</Button></Link>} />
          <div className="px-5 pb-5">
            <p className="text-2xl font-bold text-gray-900">{dash.reviews?.average || '—'} <span className="text-sm font-normal text-gray-400">/ 5 · {dash.reviews?.total || 0} reviews</span></p>
          </div>
        </Card>
        <Card>
          <CardHeader title="Monthly Growth Report" action={<Link to="/app/reports"><Button size="sm" variant="secondary">Open</Button></Link>} />
          <div className="px-5 pb-5">
            {!dash.latestMonthlyReport ? <EmptyState title="Your first report is being prepared." /> : (
              <p className="text-sm text-gray-600">{dash.latestMonthlyReport.period_month} — {dash.latestMonthlyReport.summary?.newPatients ?? '—'} new patients, {dash.latestMonthlyReport.summary?.revenueGrowthPct ?? '—'}% revenue growth.</p>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
