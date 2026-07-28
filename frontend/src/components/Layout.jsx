import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { canCreateReferrals } from '../lib/referralRights';
import clsx from 'clsx';
import logo from '../assets/logo.png';

// `pillar` marks an item as belonging to a paid ROSKYRO pillar — items
// without a `pillar` (Dashboard, Approvals, Team, Plans) are always
// available to any customer account regardless of subscription.
const NAV = {
  customer: [
    { to: '/app', label: 'Dashboard', icon: '\u{1F3E0}', end: true },
    { section: 'GROW', pillar: 'grow' },
    { to: '/app/growth', label: 'Growth Hub', icon: '\u{1F680}', pillar: 'grow' },
    { to: '/app/reviews', label: 'Reviews', icon: '\u{2B50}', pillar: 'grow' },
    { to: '/app/reports', label: 'Growth Reports', icon: '\u{1F4C8}', pillar: 'grow' },
    { section: 'MANAGE', pillar: 'manage' },
    { to: '/app/appointments', label: 'Appointments', icon: '\u{1F4C5}', pillar: 'manage' },
    { to: '/app/patients', label: 'Patient CRM', icon: '\u{1F4C7}', pillar: 'manage' },
    { to: '/app/queue', label: 'Queue', icon: '\u{1F522}', pillar: 'manage' },
    { to: '/app/followups', label: 'Follow-ups', icon: '\u{1F514}', pillar: 'manage' },
    { to: '/app/billing', label: 'Billing', icon: '\u{1F9FE}', pillar: 'manage' },
    { to: '/app/whatsapp', label: 'WhatsApp', icon: '\u{1F4AC}', pillar: 'manage' },
    { to: '/app/booking', label: 'Online Booking (QR)', icon: '\u{1F4F1}', pillar: 'manage' },
    { section: 'Networking Marketing', pillar: 'connect' },
    // Listing yourself as a Networking Marketing partner is always free, regardless of
    // subscription -- so this item deliberately has no `pillar`, unlike the
    // rest of the Networking Marketing section below it.
    { to: '/app/become-partner', label: 'Become a Partner', icon: '\u{1F195}' },
    // Choosing/creating a referral is restricted to certain business types
    // (Clinic, Hospital, Eye Hospital) -- see lib/referralRights.js. Other
    // business types can list themselves as a partner above, but these two
    // items are hidden for them since there's nothing for them to do here.
    { to: '/app/referrals', label: 'Referral Network', icon: '\u{1F91D}', pillar: 'connect', requiresReferralRights: true },
    { to: '/app/partners', label: 'Partner Directory', icon: '\u{1F4D1}', pillar: 'connect', requiresReferralRights: true },
    { to: '/app/partnerships', label: 'My Partners', icon: '\u{2B50}', pillar: 'connect', requiresReferralRights: true },
    { to: '/app/settlements', label: 'Marketing Fee Payouts', icon: '\u{1F4B0}', pillar: 'connect', requiresReferralRights: true },
    { section: null },
    { to: '/app/approvals', label: 'Pending Approvals', icon: '\u{2705}' },
    { to: '/app/team', label: 'My Team', icon: '\u{1F465}' },
    { to: '/app/plans', label: 'Plans & Billing', icon: '\u{1F4B3}' },
  ],
  partner: [
    { to: '/partner', label: 'Dashboard', icon: '\u{1F3E0}', end: true },
    { to: '/partner/requests', label: 'Referral Requests', icon: '\u{1F4E5}' },
    { to: '/partner/partnerships', label: 'Partnerships', icon: '\u{2B50}' },
    { to: '/partner/wallet', label: 'Wallet', icon: '\u{1F4B0}' },
    { to: '/partner/plans', label: 'Plans & Billing', icon: '\u{1F4B3}' },
  ],
  internal: [
    { to: '/team', label: 'Team Dashboard', icon: '\u{1F3E2}', end: true },
    { to: '/team/tasks', label: 'Task Queue', icon: '\u{1F4CB}' },
    { to: '/team/referrals', label: 'All Referrals', icon: '\u{1F91D}' },
    { to: '/team/organizations', label: 'Businesses', icon: '\u{1F3E5}' },
    { to: '/team/partner-verification', label: 'Partner Verification', icon: '\u{1F510}' },
    { to: '/team/settlements', label: 'Settlements', icon: '\u{1F4B0}' },
    { to: '/team/marketing-payouts', label: 'Marketing Fee Payouts', icon: '\u{1F4E4}' },
    { to: '/team/subscription-renewals', label: 'Subscription Renewals', icon: '\u{1F501}' },
    // Shared across every business/computer -- see routers/whatsapp.py's
    // /queue endpoints and app/utils/whatsapp_sender.py for why this is
    // centralized here instead of each business sending its own.
    { to: '/team/whatsapp-queue', label: 'WhatsApp Queue', icon: '\u{1F4F2}' },
    { to: '/team/roster', label: 'Team Roster', icon: '\u{1F465}' },
    // Super-admin only — the consolidated Earnings Wallet rolls up both
    // revenue streams (Marketing Fees + subscription renewals) and the
    // business-wise payout breakdown in one place, same restriction as
    // Pricing & Payments below.
    { to: '/team/wallet', label: 'Earnings Wallet', icon: '\u{1F4B0}', roles: ['roskyro_admin'] },
    // Super-admin only — pricing & UPI payment settings live behind this,
    // never shown to other internal roles (ops/growth/content/etc).
    { to: '/team/pricing', label: 'Pricing & Payments', icon: '\u{1F4B3}', roles: ['roskyro_admin'] },
    // Super-admin only — resetting a locked-out user's password is a
    // manual, by-hand action, never self-service (see auth.py's login/
    // password-resets routers).
    { to: '/team/password-requests', label: 'Password Requests', icon: '\u{1F511}', roles: ['roskyro_admin'] },
  ],
};

// Pillar codes stay lowercase internally ('grow'/'manage'/'connect'), but
// 'connect' now displays as "Networking Marketing" everywhere in the UI --
// a plain .toUpperCase() on the code would still read "CONNECT", so any
// display string built from a pillar code goes through this map instead.
const PILLAR_DISPLAY_NAMES = { grow: 'GROW', manage: 'MANAGE', connect: 'Networking Marketing' };

const SHELL_LABEL = {
  customer: 'Business Dashboard',
  partner: 'Partner Portal',
  internal: 'ROSKYRO Team Dashboard',
};

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const items = (NAV[user.appShell] || []).filter((item) => {
    if (item.roles && !item.roles.includes(user.role)) return false;
    if (item.requiresReferralRights && !canCreateReferrals(user)) return false;
    return true;
  });
  const activePillars = user.activePillars || [];

  return (
    <div className="min-h-screen flex bg-gray-50">
      <aside className="w-64 shrink-0 bg-brand-950 text-white flex flex-col">
        <div className="px-5 py-5 border-b border-white/10 flex items-center gap-2">
          <img src={logo} alt="ROSKYRO" className="h-8 w-8 object-contain shrink-0" />
          <div>
            <p className="text-lg font-extrabold tracking-tight leading-tight">ROSKYRO</p>
            <p className="text-xs text-brand-200">{SHELL_LABEL[user.appShell] || 'Healthcare OS'}</p>
          </div>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {items.map((item, idx) => {
            if (item.section !== undefined) {
              if (item.section === null) return <div key={`sep-${idx}`} className="border-t border-white/10 my-2" />;
              const locked = item.pillar && !activePillars.includes(item.pillar);
              return (
                <p key={item.section} className="px-3 pt-3 pb-1 text-[11px] font-semibold tracking-wider text-brand-400 flex items-center gap-1.5">
                  {item.section}
                  {locked && <span title="Not active on your plan">{'\u{1F512}'}</span>}
                </p>
              );
            }

            const locked = item.pillar && !activePillars.includes(item.pillar);
            if (locked) {
              return (
                <NavLink
                  key={item.to}
                  to="/app/plans"
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-brand-400 hover:bg-white/5"
                  title={`Activate ${PILLAR_DISPLAY_NAMES[item.pillar] || item.pillar.toUpperCase()} to unlock`}
                >
                  <span className="text-base opacity-50">{item.icon}</span>
                  <span className="flex-1">{item.label}</span>
                  <span className="text-xs">{'\u{1F512}'}</span>
                </NavLink>
              );
            }

            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition',
                    isActive ? 'bg-white text-brand-900' : 'text-brand-100 hover:bg-white/10'
                  )
                }
              >
                <span className="text-base">{item.icon}</span>
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <div className="px-4 py-4 border-t border-white/10">
          <p className="text-sm font-semibold truncate">{user.name}</p>
          <p className="text-xs text-brand-300 truncate">{user.orgName || user.role.replace(/_/g, ' ')}</p>
          <button
            onClick={() => {
              logout();
              navigate('/login');
            }}
            className="mt-3 text-xs text-brand-200 hover:text-white underline"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 min-w-0">
        <div className="max-w-6xl mx-auto px-6 py-8">{children}</div>
      </main>
    </div>
  );
}
