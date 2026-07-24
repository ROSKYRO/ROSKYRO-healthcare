import LegalLayout from '../../components/LegalLayout';

const SECTIONS = [
  {
    heading: 'No Medical Advice',
    paragraphs: [
      'ROSKYRO is a business software platform for healthcare businesses — it is not a medical device and does not provide medical advice, diagnosis or treatment. All clinical decisions remain the sole responsibility of the licensed healthcare professionals using the platform.',
    ],
  },
  {
    heading: 'Service Availability',
    paragraphs: [
      'We aim for high availability but do not guarantee uninterrupted, error-free access to ROSKYRO at all times. Scheduled maintenance or unforeseen technical issues may occasionally affect access.',
    ],
  },
  {
    heading: 'Third-Party Integrations',
    paragraphs: [
      'ROSKYRO may connect with or rely on third-party services (such as Google Business Profile, Meta/Google Ads, WhatsApp messaging, and payment/UPI rails). We are not responsible for the availability, accuracy or policies of these third-party services.',
    ],
  },
  {
    heading: 'Accuracy of Information',
    paragraphs: [
      'While we strive for accuracy in reports, analytics and AI-assisted content, all outputs should be reviewed by you before being relied upon for business or patient-facing decisions — particularly any AI-drafted content, which is always subject to human review before publishing.',
    ],
  },
  {
    heading: 'Limitation of Liability',
    paragraphs: [
      'ROSKYRO and its team shall not be liable for any loss or damage arising from reliance on information provided through the platform, to the maximum extent permitted by applicable law. See our Terms & Conditions for the full limitation of liability.',
    ],
  },
];

export default function Disclaimer() {
  return (
    <LegalLayout
      title="Disclaimer"
      tagline="Important limitations on how ROSKYRO's information and services should be used."
      effectiveDate="23 July 2026"
      sections={SECTIONS}
    />
  );
}
