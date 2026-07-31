import { Card, Button, Badge, formatCurrency } from './ui';

// Renders a single optional add-on plan (currently: "Reel Making", ₹6999/mo,
// only purchasable while GROW is active) -- shared between the in-app
// business Plans page and the in-app partner Plans page, since both sides
// sell the exact same add-on shape against their own subscribe/cancel API.
export default function AddonCard({ addon, isActive, isPending, requiredPillarActive, onSubscribe, onCancel, busy }) {
  return (
    <Card className="p-5 border-dashed border-2 border-gray-200">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Optional Add-on</p>
          <h3 className="text-lg font-bold text-gray-900 mt-0.5">{addon.name}</h3>
          <p className="text-sm text-gray-500 mt-0.5">{addon.tagline}</p>
        </div>
        {isActive && <Badge tone="verified">Active</Badge>}
        {!isActive && isPending && <Badge tone="pending_payment">Awaiting confirmation</Badge>}
      </div>

      <p className="text-2xl font-extrabold text-gray-900 mt-3">
        {formatCurrency(addon.monthly_price)}<span className="text-sm font-normal text-gray-400">/month</span>
      </p>

      <ul className="mt-3 space-y-1.5">
        {(addon.features || []).map((f) => (
          <li key={f} className="flex items-start gap-2 text-sm text-gray-600">
            <span className="mt-0.5 text-brand-600">✓</span>
            <span>{f}</span>
          </li>
        ))}
      </ul>

      <div className="mt-4">
        {isActive ? (
          <Button size="sm" variant="ghost" disabled={busy} onClick={onCancel}>Cancel Add-on</Button>
        ) : isPending ? (
          <p className="text-xs text-amber-700">
            Payment submitted — ROSKYRO team confirm karne ke baad ye add-on active hoga. See "Awaiting ROSKYRO
            confirmation" above to withdraw.
          </p>
        ) : (
          <>
            <Button size="sm" disabled={busy || !requiredPillarActive} onClick={onSubscribe}>
              {busy ? 'Opening…' : `Add for ${formatCurrency(addon.monthly_price)}/mo`}
            </Button>
            {!requiredPillarActive && (
              <p className="text-xs text-amber-700 mt-2">
                Activate {(addon.requires_pillar || 'GROW').toUpperCase()} first — this add-on only works alongside it.
              </p>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
