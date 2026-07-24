import { useEffect, useState } from 'react';
import api from '../../lib/api';
import { Card, PageLoading, EmptyState } from '../../components/ui';

export default function Reports() {
  const [reports, setReports] = useState(null);

  useEffect(() => {
    api.get('/reports').then((res) => setReports(res.data.reports));
  }, []);

  if (!reports) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Growth Reports</h1>
        <p className="text-sm text-gray-500 mt-1">Your monthly business growth summary, compiled by ROSKYRO.</p>
      </div>

      {reports.length === 0 ? <EmptyState title="Your first monthly report will appear here." /> : (
        <div className="grid md:grid-cols-2 gap-4">
          {reports.map((r) => (
            <Card key={r.id} className="p-5">
              <p className="font-semibold text-gray-900">{r.period_month}</p>
              <p className="text-xs text-gray-400 capitalize">{r.report_type.replace(/_/g, ' ')}</p>
              {r.summary && (
                <div className="grid grid-cols-2 gap-3 mt-4 text-sm">
                  {Object.entries(r.summary).map(([k, v]) => (
                    <div key={k}>
                      <p className="text-gray-400 capitalize">{k.replace(/([A-Z])/g, ' $1')}</p>
                      <p className="font-semibold text-gray-900">{v}</p>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
