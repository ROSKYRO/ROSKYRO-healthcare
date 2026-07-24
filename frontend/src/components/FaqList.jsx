// Native <details>/<summary> accordion -- zero JS state needed, works
// everywhere, and stays keyboard/screen-reader accessible for free.
export default function FaqList({ items }) {
  return (
    <div className="divide-y divide-gray-100 border border-gray-200 rounded-2xl bg-white overflow-hidden">
      {items.map((f) => (
        <details key={f.q} className="group px-5 py-4">
          <summary className="flex items-center justify-between cursor-pointer list-none font-semibold text-gray-900 text-sm">
            {f.q}
            <span className="ml-4 text-gray-400 transition group-open:rotate-45 text-lg leading-none">+</span>
          </summary>
          <p className="text-sm text-gray-600 mt-3 leading-relaxed">{f.a}</p>
        </details>
      ))}
    </div>
  );
}
