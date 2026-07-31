import QRCode from 'qrcode';

// Builds a standard UPI deep-link ("upi://pay?...") and renders it as a
// scannable QR code data URL -- same `qrcode` package + toDataURL() pattern
// already used for the patient-facing booking QR (see
// pages/customer/BookingSettings.jsx), just pointed at a payment link
// instead of a booking link. Any UPI app (GPay/PhonePe/Paytm/etc.) that
// scans this deep-links straight into a pre-filled payment screen -- payee,
// amount and a reference note are all pre-populated, the payer only has to
// confirm.
//
// `pn` (payee name) is always "ROSKYRO" here regardless of who's paying --
// this UPI ID is ROSKYRO's own collection ID (see Pricing & Payments' UPI
// setting), never the paying business/partner's own.
export function buildUpiPaymentLink({ upiId, amount, note }) {
  if (!upiId) return null;
  const params = new URLSearchParams({
    pa: upiId,
    pn: 'ROSKYRO',
    cu: 'INR',
  });
  if (amount) params.set('am', String(amount));
  if (note) params.set('tn', note);
  return `upi://pay?${params.toString()}`;
}

export async function upiPaymentQrDataUrl({ upiId, amount, note }) {
  const link = buildUpiPaymentLink({ upiId, amount, note });
  if (!link) return null;
  return QRCode.toDataURL(link, { width: 220, margin: 1, color: { dark: '#0b1f3a', light: '#ffffff' } });
}
