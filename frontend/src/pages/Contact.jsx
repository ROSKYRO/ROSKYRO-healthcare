import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '../lib/api';
import { Card, Input, Select, Textarea, Button } from '../components/ui';
import { PublicHeader, PublicFooter } from '../components/PublicNav';

const REASON_LABEL = {
  demo: 'Book a Demo',
  consultation: 'Free Consultation',
  enterprise: 'Enterprise / Multi-Branch',
  general: 'General Enquiry',
};

const BUSINESS_TYPES = ['Clinic', 'Hospital', 'Diagnostic Lab', 'Imaging Center', 'Dental Clinic', 'Physiotherapy / Rehab', 'Home Healthcare', 'Veterinary Clinic', 'Other'];

const EMPTY_FORM = { name: '', phone: '', email: '', businessName: '', businessType: '', city: '', message: '' };

export default function Contact() {
  const [params] = useSearchParams();
  const reason = params.get('reason') || 'general';
  const [form, setForm] = useState(EMPTY_FORM);
  const [state, setState] = useState('idle'); // idle | busy | done | error
  const [errorMsg, setErrorMsg] = useState('');

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function submit(e) {
    e.preventDefault();
    setState('busy');
    setErrorMsg('');
    try {
      await api.post('/public/contact', { ...form, reason });
      setState('done');
      setForm(EMPTY_FORM);
    } catch (err) {
      setErrorMsg(err?.response?.data?.error || 'Could not send your message. Please try again.');
      setState('error');
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <PublicHeader />

      <section className="max-w-3xl mx-auto px-6 pt-8 pb-10 text-center">
        <p className="inline-block text-xs font-semibold tracking-wide uppercase bg-brand-50 text-brand-700 rounded-full px-3 py-1 mb-5">
          {REASON_LABEL[reason] || REASON_LABEL.general}
        </p>
        <h1 className="text-3xl md:text-4xl font-extrabold text-gray-900 tracking-tight">
          Let's Talk About Your Growth
        </h1>
        <p className="mt-4 text-gray-500">
          Tell us about your business — a member of our team will reach out within one business day.
        </p>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-20 grid md:grid-cols-5 gap-8">
        <Card className="p-6 md:p-8 md:col-span-3">
          {state === 'done' ? (
            <div className="text-center py-10">
              <p className="text-2xl">✅</p>
              <h2 className="text-lg font-bold text-gray-900 mt-3">Thanks — we've got your message.</h2>
              <p className="text-sm text-gray-500 mt-2">Our team will reach out to you shortly.</p>
              <Button className="mt-6" onClick={() => setState('idle')}>Send another message</Button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="grid sm:grid-cols-2 gap-4">
                <Input label="Full name" required value={form.name} onChange={(e) => update('name', e.target.value)} />
                <Input label="Phone number" required value={form.phone} onChange={(e) => update('phone', e.target.value)} />
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <Input label="Email" type="email" value={form.email} onChange={(e) => update('email', e.target.value)} />
                <Input label="City" value={form.city} onChange={(e) => update('city', e.target.value)} />
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <Input label="Business name" value={form.businessName} onChange={(e) => update('businessName', e.target.value)} />
                <Select label="Business type" value={form.businessType} onChange={(e) => update('businessType', e.target.value)}>
                  <option value="">Select...</option>
                  {BUSINESS_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </Select>
              </div>
              <Textarea label="Message" rows={4} value={form.message} onChange={(e) => update('message', e.target.value)} placeholder="Tell us a bit about your business and what you're looking for..." />
              {errorMsg && <p className="text-sm text-rose-600">{errorMsg}</p>}
              <Button type="submit" size="lg" disabled={state === 'busy'} className="w-full">
                {state === 'busy' ? 'Sending...' : 'Send Message'}
              </Button>
            </form>
          )}
        </Card>

        <div className="md:col-span-2 space-y-6">
          <Card className="p-6">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Office Details</p>
            <p className="text-sm font-semibold text-gray-900">ROSKYRO Technologies</p>
            <p className="text-sm text-gray-600 mt-2">Mumbai, Maharashtra, India</p>
            <p className="text-sm text-gray-600 mt-2">hello@roskyro.com</p>
            <p className="text-sm text-gray-600 mt-1">+91 92441 66752</p>
            <p className="text-sm text-gray-600 mt-2">Mon–Sat, 9:00 AM – 7:00 PM IST</p>
            <a
              href="https://wa.me/919244166752"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 mt-4 bg-emerald-600 text-white text-sm font-semibold px-4 py-2.5 rounded-lg hover:bg-emerald-700"
            >
              Chat on WhatsApp
            </a>
            <a
              href="https://www.google.com/search?q=ROSKYRO&stick=H4sIAAAAAAAA_-NgU1I1qDAxMUlOMk40tjRMMrRISrG0MqgwT01OMzFOM080TE02MDNIXsTKHuQf7B0Z5A8ARqHqGDMAAAA&hl=en&mat=CVdRfy7VAYb3ElcBa0lj_9FwjFs37r9uTaXAm4RVEJm-jFB87T_N2s6SWpsJ0b-qWRIXdPl9SlI82NPI9_xElTYzWor5N7fPDpEDxCL0NIIYgt5foMccsfGwTTLXbtqpOVU&authuser=0"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 mt-3 ml-2 border border-gray-300 text-gray-700 text-sm font-semibold px-4 py-2.5 rounded-lg hover:bg-gray-50"
            >
              View on Google
            </a>
          </Card>

          <Card className="overflow-hidden">
            <iframe
              title="ROSKYRO office location"
              src="https://maps.google.com/maps?q=Mumbai%2C%20Maharashtra%2C%20India&t=&z=12&ie=UTF8&iwloc=&output=embed"
              className="w-full h-64 border-0"
              loading="lazy"
            />
          </Card>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
