import { Link } from 'react-router-dom';
import { PublicHeader, PublicFooter } from '../components/PublicNav';
import FaqList from '../components/FaqList';
import { FAQS } from '../data/faq';

export default function FAQ() {
  return (
    <div className="min-h-screen bg-gray-50">
      <PublicHeader />

      <section className="max-w-3xl mx-auto px-6 pt-8 pb-10 text-center">
        <p className="inline-block text-xs font-semibold tracking-wide uppercase bg-brand-50 text-brand-700 rounded-full px-3 py-1 mb-5">
          FAQ
        </p>
        <h1 className="text-3xl md:text-4xl font-extrabold text-gray-900 tracking-tight">
          Frequently Asked Questions
        </h1>
        <p className="mt-4 text-gray-500">Everything you need to know about ROSKYRO. Can't find your answer?</p>
        <Link to="/contact" className="inline-block mt-2 text-brand-700 font-semibold text-sm">Talk to us →</Link>
      </section>

      <section className="max-w-3xl mx-auto px-6 pb-20">
        <FaqList items={FAQS} />
      </section>

      <PublicFooter />
    </div>
  );
}
