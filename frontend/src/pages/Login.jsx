import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../lib/api';
import { Button, Input, Textarea } from '../components/ui';
import logo from '../assets/logo.png';

const DEMO_ACCOUNTS = [
  { label: 'Clinic Owner (Customer)', identifier: 'sunrise.family.clinic@example.com' },
  { label: 'Partner Admin (CityScan Diagnostics)', identifier: 'admin.cityscan.diagnostics@example.com' },
  { label: 'ROSKYRO Admin (Internal)', identifier: 'admin@roskyro.com' },
  { label: 'ROSKYRO Ops Manager (Internal)', identifier: 'ops@roskyro.com' },
];

function ForgotPasswordPanel({ onClose }) {
  const [identifier, setIdentifier] = useState('');
  const [note, setNote] = useState('');
  const [state, setState] = useState('idle'); // idle | busy | done | error
  const [errorMsg, setErrorMsg] = useState('');
  const [alreadyPending, setAlreadyPending] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setState('busy');
    setErrorMsg('');
    try {
      const { data } = await api.post('/password-resets', { identifier, note });
      setAlreadyPending(!!data.alreadyPending);
      setState('done');
    } catch (err) {
      setErrorMsg(err?.response?.data?.error || 'Could not submit your request. Please try again.');
      setState('error');
    }
  }

  if (state === 'done') {
    return (
      <div className="mt-6 border border-brand-100 bg-brand-50 rounded-xl p-4">
        <p className="text-sm font-semibold text-brand-800">
          {alreadyPending ? "You've already got a request pending." : 'Request sent.'}
        </p>
        <p className="text-xs text-brand-700 mt-1">
          A ROSKYRO super admin will verify it's really you and set a new password by hand — they'll reach out on
          the mobile number/email you gave us. This is not automatic; there's no reset link.
        </p>
        <button type="button" onClick={onClose} className="text-xs text-brand-700 font-medium mt-3 underline">
          Back to sign in
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="mt-6 border border-gray-200 rounded-xl p-4 space-y-3">
      <p className="text-sm font-semibold text-gray-900">Forgot your password?</p>
      <p className="text-xs text-gray-500">
        Enter the mobile number or email your account uses. A ROSKYRO super admin will manually verify you and set a
        new password — no automated email link.
      </p>
      <Input
        label="Mobile number or email"
        required
        value={identifier}
        onChange={(e) => setIdentifier(e.target.value)}
        placeholder="9800000001 or you@business.com"
      />
      <Textarea
        label="Anything else to help us confirm it's you (optional)"
        rows={2}
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      {errorMsg && <p className="text-sm text-rose-600">{errorMsg}</p>}
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={state === 'busy'}>
          {state === 'busy' ? 'Sending…' : 'Send request'}
        </Button>
        <button type="button" onClick={onClose} className="text-xs text-gray-500 hover:text-gray-700">
          Cancel
        </button>
      </div>
    </form>
  );
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('Roskyro@123');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showForgot, setShowForgot] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const user = await login(identifier, password);
      const home = { customer: '/app', partner: '/partner', internal: '/team' }[user.appShell] || '/app';
      navigate(home);
    } catch (err) {
      setError(err?.response?.data?.error || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <Link to="/" className="flex items-center gap-2 text-lg font-extrabold text-brand-700">
            <img src={logo} alt="ROSKYRO" className="h-8 w-8 object-contain" />
            ROSKYRO
          </Link>
          <h1 className="text-2xl font-bold text-gray-900 mt-6">Welcome back</h1>
          <p className="text-sm text-gray-500 mt-1">Sign in to your ROSKYRO Healthcare OS dashboard.</p>

          {!showForgot ? (
            <>
              <form onSubmit={handleSubmit} className="mt-6 space-y-4">
                <Input
                  label="Mobile number or email"
                  required
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="9800000001 or you@business.com"
                />
                <Input label="Password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
                {error && <p className="text-sm text-rose-600">{error}</p>}
                <Button type="submit" disabled={loading} className="w-full">
                  {loading ? 'Signing in…' : 'Sign in'}
                </Button>
              </form>

              <button
                type="button"
                onClick={() => setShowForgot(true)}
                className="text-sm text-brand-700 font-medium mt-3 hover:underline"
              >
                Forgot password?
              </button>

              <p className="text-sm text-gray-500 mt-4">
                New healthcare business? <Link to="/register" className="text-brand-700 font-medium">Create an account</Link>
              </p>

              <div className="mt-8 border-t border-gray-200 pt-6">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Demo accounts (password: Roskyro@123)</p>
                <div className="space-y-1">
                  {DEMO_ACCOUNTS.map((a) => (
                    <button
                      key={a.identifier}
                      type="button"
                      onClick={() => setIdentifier(a.identifier)}
                      className="block text-left text-xs text-brand-700 hover:underline"
                    >
                      {a.label} — {a.identifier}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-gray-400 mt-2">
                  Mobile-number login also works for every seeded account — ask a super admin for the number.
                </p>
              </div>
            </>
          ) : (
            <ForgotPasswordPanel onClose={() => setShowForgot(false)} />
          )}
        </div>
      </div>
      <div className="hidden lg:flex flex-1 bg-brand-950 items-center justify-center text-white p-12">
        <div className="max-w-sm">
          <p className="text-2xl font-bold leading-snug">"ROSKYRO is my digital business team."</p>
          <p className="text-brand-200 mt-4 text-sm">
            You never learn AI. You never write prompts. You only approve results and watch measurable growth.
          </p>
        </div>
      </div>
    </div>
  );
}
