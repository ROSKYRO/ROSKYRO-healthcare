import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, Badge, Button, Input, Select, Textarea, PageLoading, EmptyState, formatDateTime } from '../../components/ui';

export default function Whatsapp() {
  const [messages, setMessages] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [form, setForm] = useState({ patientName: '', patientPhone: '', templateName: '', message: '' });
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [sendError, setSendError] = useState('');

  const load = useCallback(() => {
    setError('');
    api.get('/whatsapp').then((res) => setMessages(res.data.messages)).catch((err) => {
      if (err?.response?.status === 402) setBlocked(true);
      else setError('Could not load messages. Please try again.');
    });
  }, []);

  useEffect(load, [load]);
  useEffect(() => {
    api.get('/whatsapp/templates').then((res) => setTemplates(res.data.templates)).catch(() => {});
  }, []);

  async function send(e) {
    e.preventDefault();
    // Fixed: "Custom message" (templateName === '') had no way to actually
    // type a message body -- the form never collected `message`, so every
    // send with this option selected hit the backend's "Provide either a
    // message or a known templateName." 400, with no hint to the user that
    // a text field was even missing. Now required client-side whenever no
    // template is selected, and included in the POST body.
    if (!form.templateName && !form.message.trim()) {
      setSendError('Please type a message, or choose a template instead.');
      return;
    }
    setSending(true);
    setSendError('');
    try {
      await api.post('/whatsapp/send', form);
      setForm({ patientName: '', patientPhone: '', templateName: '', message: '' });
      load();
    } catch (err) {
      setSendError(err?.response?.data?.error || 'Could not send this message. Please try again.');
    } finally {
      setSending(false);
    }
  }

  if (blocked) return <UpgradePrompt pillar="manage" />;

  if (error && !messages) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!messages) return <PageLoading />;

  const selectedTemplate = templates.find((t) => t.key === form.templateName);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">WhatsApp Communication</h1>
        <p className="text-sm text-gray-500 mt-1">Send reminders, follow-up nudges and review requests.</p>
      </div>

      <Card className="p-5">
        <form onSubmit={send} className="grid grid-cols-3 gap-4 items-end">
          <Input label="Patient name" required value={form.patientName} onChange={(e) => setForm((f) => ({ ...f, patientName: e.target.value }))} />
          <Input label="Phone" required value={form.patientPhone} onChange={(e) => setForm((f) => ({ ...f, patientPhone: e.target.value }))} />
          <Select
            label="Template"
            value={form.templateName}
            onChange={(e) => setForm((f) => ({ ...f, templateName: e.target.value, message: e.target.value ? '' : f.message }))}
          >
            <option value="">Custom message</option>
            {templates.map((t) => <option key={t.key} value={t.key}>{t.key.replace(/_/g, ' ')}</option>)}
          </Select>
          {selectedTemplate && <p className="col-span-3 text-xs text-gray-400 -mt-2">Preview: "{selectedTemplate.preview}"</p>}
          {!form.templateName && (
            <Textarea
              label="Message"
              required
              rows={2}
              placeholder="Type your custom message…"
              value={form.message}
              onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))}
              className="col-span-3"
            />
          )}
          {sendError && <p className="col-span-3 text-sm text-rose-600">{sendError}</p>}
          <div className="col-span-3"><Button type="submit" disabled={sending}>{sending ? 'Sending…' : 'Send Message'}</Button></div>
        </form>
      </Card>

      <Card>
        <div className="px-5 pt-5"><h3 className="text-base font-semibold text-gray-900">Message Log</h3></div>
        <div className="px-5 pb-5">
          {messages.length === 0 ? <EmptyState title="No messages sent yet." /> : (
            <div className="divide-y divide-gray-100">
              {messages.map((m) => (
                <div key={m.id} className="py-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-gray-900">{m.patient_name} · {m.patient_phone}</span>
                    <Badge tone="slate">{m.status}</Badge>
                  </div>
                  <p className="text-gray-600 mt-1">{m.message}</p>
                  <p className="text-xs text-gray-400 mt-1">{formatDateTime(m.created_at)}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
