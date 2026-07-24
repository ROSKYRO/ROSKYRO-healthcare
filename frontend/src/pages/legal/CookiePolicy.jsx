import LegalLayout from '../../components/LegalLayout';

const SECTIONS = [
  {
    heading: 'What Cookies Are',
    paragraphs: [
      'Cookies are small text files stored on your device when you visit a website. They help the site remember information about your visit, such as your preferences and sign-in state.',
    ],
  },
  {
    heading: 'Types of Cookies',
    paragraphs: [
      'Essential cookies — required for core functionality such as staying signed in.\nPreference cookies — remember settings like your last-used view or filters.\nAnalytics cookies — help us understand how the site is used so we can improve it.',
    ],
    bullets: true,
  },
  {
    heading: 'Why We Use Cookies',
    paragraphs: [
      'We use cookies to keep the platform functional (keeping you logged in across pages), to understand usage patterns on our public marketing pages, and to improve the product experience over time.',
    ],
  },
  {
    heading: 'Managing Cookies',
    paragraphs: [
      'Most browsers let you view, delete and block cookies through their settings. Blocking essential cookies may prevent parts of ROSKYRO — such as staying signed in — from working correctly.',
    ],
  },
];

export default function CookiePolicy() {
  return (
    <LegalLayout
      title="Cookie Policy"
      tagline="How ROSKYRO uses cookies on this website."
      effectiveDate="23 July 2026"
      sections={SECTIONS}
    />
  );
}
