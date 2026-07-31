import { forwardRef } from 'react';
import clsx from 'clsx';

export function Card({ className, children, ...props }) {
  return (
    <div className={clsx('bg-white rounded-2xl border border-gray-200 shadow-sm', className)} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-start justify-between px-5 pt-5 pb-2">
      <div>
        <h3 className="text-base font-semibold text-gray-900">{title}</h3>
        {subtitle && <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function StatTile({ label, value, sub, icon, tone = 'brand' }) {
  const tones = {
    brand: 'bg-brand-50 text-brand-700',
    amber: 'bg-amber-50 text-amber-700',
    blue: 'bg-blue-50 text-blue-700',
    rose: 'bg-rose-50 text-rose-700',
    slate: 'bg-slate-100 text-slate-700',
  };
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500 font-medium">{label}</p>
        {icon && <span className={clsx('h-9 w-9 rounded-xl flex items-center justify-center text-lg', tones[tone])}>{icon}</span>}
      </div>
      <p className="text-2xl font-bold text-gray-900 mt-2">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </Card>
  );
}

const BADGE_TONES = {
  draft: 'bg-gray-100 text-gray-700',
  open: 'bg-amber-100 text-amber-800',
  pending_review: 'bg-amber-100 text-amber-800',
  queued: 'bg-amber-100 text-amber-800',
  sent: 'bg-blue-100 text-blue-800',
  accepted: 'bg-teal-100 text-teal-800',
  declined: 'bg-rose-100 text-rose-800',
  in_progress: 'bg-indigo-100 text-indigo-800',
  report_uploaded: 'bg-purple-100 text-purple-800',
  completed: 'bg-emerald-100 text-emerald-800',
  cancelled: 'bg-gray-200 text-gray-600',
  pending: 'bg-amber-100 text-amber-800',
  pending_payment: 'bg-amber-100 text-amber-800',
  payment_rejected: 'bg-rose-100 text-rose-800',
  verified: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-rose-100 text-rose-800',
  approved: 'bg-emerald-100 text-emerald-800',
  active: 'bg-emerald-100 text-emerald-800',
  done: 'bg-emerald-100 text-emerald-800',
  blocked: 'bg-rose-100 text-rose-800',
  in_review: 'bg-purple-100 text-purple-800',
  paid: 'bg-emerald-100 text-emerald-800',
  low: 'bg-gray-100 text-gray-600',
  normal: 'bg-blue-100 text-blue-700',
  high: 'bg-amber-100 text-amber-800',
  urgent: 'bg-rose-100 text-rose-800',
};

export function Badge({ children, tone }) {
  const key = String(children).toLowerCase().replace(/\s+/g, '_');
  const cls = BADGE_TONES[tone || key] || 'bg-gray-100 text-gray-700';
  return (
    <span className={clsx('inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium capitalize', cls)}>
      {String(children).replace(/_/g, ' ')}
    </span>
  );
}

export function Button({ variant = 'primary', size = 'md', className, children, ...props }) {
  const variants = {
    primary: 'bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-300',
    secondary: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50',
    danger: 'bg-rose-600 text-white hover:bg-rose-700',
    ghost: 'text-gray-600 hover:bg-gray-100',
  };
  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-sm',
    lg: 'px-5 py-2.5 text-base',
  };
  return (
    <button
      className={clsx('rounded-lg font-medium transition disabled:cursor-not-allowed inline-flex items-center justify-center gap-2', variants[variant], sizes[size], className)}
      {...props}
    >
      {children}
    </button>
  );
}

// forwardRef so callers (e.g. BookingSettings.jsx's "select the booking
// link text on copy" behavior) can hold a ref to the underlying <input>
// DOM node -- a plain function component silently drops any ref passed
// to it (React warns "Function components cannot be given refs"), which
// left ref.current always null and any .select()/.focus() call on it a
// silent no-op.
export const Input = forwardRef(function Input({ label, className, ...props }, ref) {
  return (
    <label className="block">
      {label && <span className="block text-sm font-medium text-gray-700 mb-1">{label}</span>}
      <input
        ref={ref}
        className={clsx('w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500', className)}
        {...props}
      />
    </label>
  );
});

export function Select({ label, className, children, ...props }) {
  return (
    <label className="block">
      {label && <span className="block text-sm font-medium text-gray-700 mb-1">{label}</span>}
      <select
        className={clsx('w-full rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500', className)}
        {...props}
      >
        {children}
      </select>
    </label>
  );
}

export function Textarea({ label, className, ...props }) {
  return (
    <label className="block">
      {label && <span className="block text-sm font-medium text-gray-700 mb-1">{label}</span>}
      <textarea
        className={clsx('w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500', className)}
        {...props}
      />
    </label>
  );
}

export function EmptyState({ title, subtitle, action }) {
  return (
    <div className="text-center py-12 px-6">
      <p className="text-sm font-medium text-gray-700">{title}</p>
      {subtitle && <p className="text-sm text-gray-400 mt-1">{subtitle}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ className }) {
  return (
    <div className={clsx('inline-block h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-brand-600', className)} />
  );
}

export function PageLoading() {
  return (
    <div className="flex items-center justify-center h-64">
      <Spinner />
    </div>
  );
}

export function Table({ columns, rows, keyField = 'id', onRowClick, emptyMessage = 'No records yet.' }) {
  if (!rows || rows.length === 0) return <EmptyState title={emptyMessage} />;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} className="text-left font-medium text-gray-500 px-5 py-3 whitespace-nowrap">
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((row) => (
            <tr
              key={row[keyField]}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={clsx(onRowClick && 'cursor-pointer hover:bg-gray-50')}
            >
              {columns.map((col) => (
                <td key={col.key} className="px-5 py-3 whitespace-nowrap text-gray-700">
                  {col.render ? col.render(row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function formatCurrency(amount) {
  // Fixed: `amount || 0` only substitutes 0 for FALSY input (null/
  // undefined/0/''/NaN) -- a non-numeric but truthy value (e.g. a
  // corrupted numeric field arriving as a string like "N/A") passed
  // straight through, so Number("N/A") became NaN and
  // Intl.NumberFormat.format(NaN) silently rendered "₹NaN" on screen
  // instead of falling back to ₹0. This is the shared money formatter
  // every page on the site uses, so this guards it explicitly.
  const n = Number(amount);
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number.isFinite(n) ? n : 0);
}

export function formatDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function formatDateTime(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}
