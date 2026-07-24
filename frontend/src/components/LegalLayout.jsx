import { PublicHeader, PublicFooter } from './PublicNav';

/** Shared layout for every legal/policy page (Privacy, Terms, Refund,
 * Cookie, Disclaimer) -- `sections` is an array of { heading, paragraphs }
 * where paragraphs is an array of strings (rendered as <p>) or a single
 * array wrapped list (rendered as a <ul> when items look like short bullets
 * via the `bullets` key instead). */
export default function LegalLayout({ title, tagline, effectiveDate, sections }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <PublicHeader />

      <section className="max-w-3xl mx-auto px-6 pt-8 pb-8">
        <p className="inline-block text-xs font-semibold tracking-wide uppercase bg-brand-50 text-brand-700 rounded-full px-3 py-1 mb-5">
          Legal
        </p>
        <h1 className="text-3xl md:text-4xl font-extrabold text-gray-900 tracking-tight">{title}</h1>
        {tagline && <p className="mt-3 text-gray-500">{tagline}</p>}
        <p className="mt-2 text-xs text-gray-400">Effective date: {effectiveDate}</p>
      </section>

      <section className="max-w-3xl mx-auto px-6 pb-12 space-y-8">
        {sections.map((s) => (
          <div key={s.heading}>
            <h2 className="text-lg font-bold text-gray-900">{s.heading}</h2>
            <div className="mt-2 space-y-2">
              {s.paragraphs.map((p, i) =>
                s.bullets ? (
                  <ul key={i} className="list-disc list-inside space-y-1">
                    {p.split('\n').map((line) => <li key={line} className="text-sm text-gray-600">{line}</li>)}
                  </ul>
                ) : (
                  <p key={i} className="text-sm text-gray-600 leading-relaxed">{p}</p>
                )
              )}
            </div>
          </div>
        ))}
      </section>

      <section className="max-w-3xl mx-auto px-6 pb-20">
        <div className="border border-gray-200 rounded-2xl p-5 bg-white text-xs text-gray-400 leading-relaxed">
          This page is provided as general, standard-form informational content and does not constitute legal
          advice. We recommend having it reviewed by a qualified lawyer before relying on it as legally binding
          for your specific business.
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
