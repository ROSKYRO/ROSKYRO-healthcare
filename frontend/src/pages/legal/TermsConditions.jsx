import LegalLayout from '../../components/LegalLayout';

const SECTIONS = [
  {
    heading: 'Acceptance of Terms',
    paragraphs: [
      'By creating an account or using ROSKYRO, you agree to be bound by these Terms & Conditions. If you do not agree, please do not use the platform. These terms apply to all users, including healthcare businesses (customers), partner organizations, and ROSKYRO staff accounts.',
    ],
  },
  {
    heading: 'Services',
    paragraphs: [
      'ROSKYRO provides a subscription-based AI + Human operating system for healthcare businesses across three pillars — GROW (visibility and marketing), MANAGE (operations) and CONNECT (partner network and referrals). Features available to your account depend on which pillar(s) you are subscribed to.',
    ],
  },
  {
    heading: 'Pricing & Payments',
    paragraphs: [
      'Subscription fees are billed monthly (or annually, where selected) and are payable to ROSKYRO via the payment method indicated at checkout or onboarding. Referral commission arrangements under CONNECT, where applicable, are paid directly between the referring and receiving businesses — ROSKYRO does not hold or process that commission. Prices may change with prior notice; continued use after a price change constitutes acceptance of the new pricing.',
    ],
  },
  {
    heading: 'Refund Policy',
    paragraphs: [
      'Refunds are handled under our separate Refund Policy, which forms part of these Terms. Please review it for eligibility and timelines.',
    ],
  },
  {
    heading: 'User Responsibilities',
    paragraphs: [
      'You are responsible for the accuracy of the data you enter into ROSKYRO (including patient and business records), for keeping your account credentials secure, for the conduct of any staff accounts you create, and for using the platform in compliance with applicable healthcare, data protection and consumer-protection laws.',
    ],
  },
  {
    heading: 'Intellectual Property',
    paragraphs: [
      'The ROSKYRO platform, including its software, design, branding and content (excluding data you input), is owned by ROSKYRO Technologies and its licensors. You retain ownership of the business and patient data you input into the platform.',
    ],
  },
  {
    heading: 'Account Suspension',
    paragraphs: [
      'We may suspend or terminate an account for non-payment, violation of these Terms, fraudulent activity, or misuse of the platform, with notice where practicable. You may cancel your own subscription at any time from your account settings.',
    ],
  },
  {
    heading: 'Limitation of Liability',
    paragraphs: [
      'ROSKYRO is provided on an "as available" basis. To the maximum extent permitted by law, ROSKYRO and its team are not liable for indirect, incidental or consequential damages arising from use of the platform. ROSKYRO assists with visibility, operations and referral connections but does not provide medical advice or guarantee specific business outcomes.',
    ],
  },
  {
    heading: 'Governing Law (India)',
    paragraphs: [
      'These Terms are governed by the laws of India. Any disputes arising from these Terms or use of ROSKYRO shall be subject to the exclusive jurisdiction of the courts of Mumbai, Maharashtra.',
    ],
  },
  {
    heading: 'Contact Details',
    paragraphs: [
      'Questions about these Terms can be sent to hello@roskyro.com or through our Contact Us page.',
    ],
  },
];

export default function TermsConditions() {
  return (
    <LegalLayout
      title="Terms & Conditions"
      tagline="The terms that govern your use of ROSKYRO."
      effectiveDate="23 July 2026"
      sections={SECTIONS}
    />
  );
}
