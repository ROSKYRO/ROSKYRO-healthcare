import LegalLayout from '../../components/LegalLayout';

const SECTIONS = [
  {
    heading: 'Eligibility',
    paragraphs: [
      'Refund requests are considered on a case-by-case basis, primarily where a technical failure on our end prevented you from accessing a paid feature, or where you were incorrectly billed. We evaluate each request individually and will explain our decision.',
    ],
  },
  {
    heading: 'Subscription Cancellation',
    paragraphs: [
      'You may cancel any subscription pillar at any time from your account billing settings. Cancellation stops future billing from your next cycle onward; it does not automatically refund the current, already-paid billing period, since you retain access to that pillar for the remainder of the period you already paid for.',
    ],
  },
  {
    heading: 'Non-refundable Services',
    paragraphs: [
      'Onboarding, training, custom setup work already performed, and any month already actively used are generally non-refundable. Third-party ad spend (Meta Ads, Google Ads) placed on your behalf is non-refundable once spent with the ad platform.',
    ],
  },
  {
    heading: 'Refund Timeline',
    paragraphs: [
      'Approved refunds are processed within 7–14 business days to the original payment method (UPI), unless otherwise agreed.',
    ],
  },
  {
    heading: 'Contact Support',
    paragraphs: [
      'To request a refund, contact us at roskyroofficial@gmail.com or through our Contact Us page with your account details and the reason for your request.',
    ],
  },
];

export default function RefundPolicy() {
  return (
    <LegalLayout
      title="Refund Policy"
      tagline="How refunds and subscription cancellations work at ROSKYRO."
      effectiveDate="23 July 2026"
      sections={SECTIONS}
    />
  );
}
