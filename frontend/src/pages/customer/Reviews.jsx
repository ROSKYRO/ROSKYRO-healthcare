import { useEffect, useState } from 'react';
import api from '../../lib/api';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, Badge, PageLoading, EmptyState, formatDate } from '../../components/ui';

export default function Reviews() {
  const [reviews, setReviews] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    // Previously no .catch at all -- a 402 (Grow plan not active) or any
    // other failure left `reviews` at null forever, a permanent spinner.
    api.get('/reviews').then((res) => setReviews(res.data.reviews)).catch((err) => {
      if (err?.response?.status === 402) setBlocked(true);
      else { setError('Could not load reviews. Please try again.'); setReviews([]); }
    });
  }, []);

  if (blocked) return <UpgradePrompt pillar="grow" />;
  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!reviews) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Reviews</h1>
        <p className="text-sm text-gray-500 mt-1">Google reviews from your patients. Your Review Manager drafts replies for your approval.</p>
      </div>

      {reviews.length === 0 ? <EmptyState title="No reviews yet." /> : (
        <div className="space-y-4">
          {reviews.map((r) => (
            <Card key={r.id} className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-gray-900">{r.patient_name || 'Anonymous'}</p>
                  <p className="text-xs text-gray-400">{formatDate(r.created_at)} · {r.platform}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-amber-500 font-semibold">{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</span>
                  <Badge tone={r.status}>{r.status.replace(/_/g, ' ')}</Badge>
                </div>
              </div>
              <p className="text-sm text-gray-700 mt-3">{r.comment}</p>
              {r.human_reply && (
                <div className="mt-3 bg-gray-50 rounded-lg p-3">
                  <p className="text-xs font-semibold text-gray-500">Your reply</p>
                  <p className="text-sm text-gray-700 mt-1">{r.human_reply}</p>
                </div>
              )}
              {!r.human_reply && r.ai_reply_draft && (
                <div className="mt-3 bg-brand-50 rounded-lg p-3">
                  <p className="text-xs font-semibold text-brand-700">Drafted reply — awaiting your Review Manager to publish</p>
                  <p className="text-sm text-gray-700 mt-1">{r.ai_reply_draft}</p>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
