import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button, Input, Select } from '../components/ui';
import logo from '../assets/logo.png';

const BUSINESS_TYPES = [
  ['clinic', 'Clinic'],
  ['hospital', 'Hospital'],
  ['diagnostic_lab', 'Diagnostic Lab'],
  ['dental', 'Dental Clinic'],
  ['skin_clinic', 'Skin Clinic'],
  ['physiotherapy', 'Physiotherapy Centre'],
  ['eye_hospital', 'Eye Hospital'],
];

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ orgName: '', businessType: 'clinic', city: '', ownerName: '', email: '', phone: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  function set(key) {
    return (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await register(form);
      navigate('/app/plans');
    } catch (err) {
      setError(err?.response?.data?.error || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="w-full max-w-md">
        <Link to="/" className="flex items-center gap-2 text-lg font-extrabold text-brand-700">
          <img src={logo} alt="ROSKYRO" className="h-8 w-8 object-contain" />
          ROSKYRO
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 mt-6">Bring your business onto ROSKYRO</h1>
        <p className="text-sm text-gray-500 mt-1">
          Takes two minutes. Our Ops team picks up your onboarding right after you sign up.
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <Input label="Business name" required value={form.orgName} onChange={set('orgName')} placeholder="Sunrise Family Clinic" />
          <div className="grid grid-cols-2 gap-3">
            <Select label="Business type" value={form.businessType} onChange={set('businessType')}>
              {BUSINESS_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
            <Input label="City" value={form.city} onChange={set('city')} placeholder="Pune" />
          </div>
          <Input label="Your name" required value={form.ownerName} onChange={set('ownerName')} placeholder="Dr. Anjali Deshmukh" />
          <Input label="Email" type="email" required value={form.email} onChange={set('email')} />
          <Input
            label="Mobile number"
            required
            value={form.phone}
            onChange={set('phone')}
            placeholder="98000 00001"
          />
          <p className="text-xs text-gray-400 -mt-2">You'll use this mobile number (or your email) with your password to sign in.</p>
          <Input label="Password" type="password" required minLength={6} value={form.password} onChange={set('password')} />
          {error && <p className="text-sm text-rose-600">{error}</p>}
          <Button type="submit" disabled={loading} className="w-full">
            {loading ? 'Creating your account…' : 'Create account'}
          </Button>
        </form>

        <p className="text-sm text-gray-500 mt-6">
          Already on ROSKYRO? <Link to="/login" className="text-brand-700 font-medium">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
