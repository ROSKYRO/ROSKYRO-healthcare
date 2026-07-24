import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, Badge, Button, Input, Select, PageLoading, EmptyState, formatDateTime } from '../../components/ui';

export default function Whatsapp() {
  const [messages, setMessages] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [form, setForm] = useState({ patientName: '', patientPhone: '', templateName: '' });
  const [sending, setSending] = useState(false);

  const load = useCallback(() => {
    api.get('/whatsapp').then((res) => setMessages(res.data.messages)).catch((err) => { if (err?.response?.status === 402) setBlocked(true); });
  }, []);

  useEffect(load, [load]);
  useEffect(() => {
    api.get('/whatsapp/templates').then((res) => setTemplates(res.data.templates)).catch(() => {});
  }, []);

  async function send(e) {
    e.preventDefault();
    setSending(true);
    try {
      await api.post('/whatsapp/send', form);
      setForm({ patientName: '', patientPhone: '', templateName: '' });
      load();
    } finally {
      setSending(false);
    }
  }

  if (blocked) return <UpgradePrompt pillar="manage" />;
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
          <Select label="Template" value={form.templateName} onChange={(e) => setForm((f) => ({ ...f, templateName: e.target.value }))}>
            <option value="">Custom message</option>
            {templates.map((t) => <option key={t.key} value={t.key}>{t.key.replace(/_/g, ' ')}</option>)}
          </Select>
          {selectedTemplate && <p className="col-span-3 text-xs text-gray-400 -mt-2">Preview: "{selectedTemplate.preview}"</p>}
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
