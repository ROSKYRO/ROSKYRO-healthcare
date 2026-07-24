import LegalLayout from '../../components/LegalLayout';

const SECTIONS = [
  {
    heading: 'Information We Collect',
    paragraphs: [
      'When you use ROSKYRO, we may collect: (a) account information such as your name, business name, email, phone number and role; (b) business operational data you enter into the platform, including patient records, appointments, billing and referral information; (c) usage data such as pages visited, features used and device/browser information; and (d) information you submit through forms, such as the Contact Us form or demo requests.',
    ],
  },
  {
    heading: 'How We Use Information',
    paragraphs: [
      'We use collected information to provide and operate the ROSKYRO platform, process subscriptions and referrals, respond to enquiries and support requests, improve our product and AI-assisted features, send you service updates and (where you have opted in) marketing communications, and comply with legal obligations.',
    ],
  },
  {
    heading: 'Cookies',
    paragraphs: [
      'We use cookies and similar technologies to keep you signed in, remember your preferences, and understand how our website is used. See our separate Cookie Policy for full details on the types of cookies we use and how to manage them.',
    ],
  },
  {
    heading: 'Data Security',
    paragraphs: [
      'We apply reasonable administrative, technical and physical safeguards to protect your data, including access controls scoped by user role, encrypted connections, and restricted internal access to patient-level data. No method of transmission or storage is 100% secure, but we work to protect your information to industry standards.',
    ],
  },
  {
    heading: 'Third-Party Services',
    paragraphs: [
      'We may share data with trusted third-party service providers who help us operate the platform (for example, hosting, database, communication and analytics providers), under confidentiality obligations. We do not sell your personal data to third parties for their own marketing purposes.',
    ],
  },
  {
    heading: 'User Rights',
    paragraphs: [
      'You may request access to, correction of, or deletion of your personal data, subject to our legal and operational obligations (for example, retaining certain records required by healthcare or tax regulation). To exercise these rights, contact us using the details on our Contact Us page.',
    ],
  },
  {
    heading: 'Data Retention',
    paragraphs: [
      'We retain account and business data for as long as your account is active and as needed to comply with legal, accounting or regulatory requirements. You may request deletion of your account data, subject to the retention obligations described above.',
    ],
  },
  {
    heading: "Children's Privacy",
    paragraphs: [
      'ROSKYRO is a business tool intended for use by adult healthcare business owners, staff and administrators. We do not knowingly collect personal data directly from children. Patient records entered by a healthcare business may include minors’ information as part of normal clinical operations, handled under the same data protection safeguards described in this policy.',
    ],
  },
  {
    heading: 'Contact Information',
    paragraphs: [
      'Questions about this Privacy Policy can be sent to hello@roskyro.com or through our Contact Us page.',
    ],
  },
];

export default function PrivacyPolicy() {
  return (
    <LegalLayout
      title="Privacy Policy"
      tagline="How ROSKYRO collects, uses and protects your information."
      effectiveDate="23 July 2026"
      sections={SECTIONS}
    />
  );
}
