import React from 'react';

const STEPS = [
  { n: 1, title: 'Intake', text: 'A dispute arrives and is ranked by deadline and amount.' },
  { n: 2, title: 'Check evidence', text: 'Missing documents for the reason code are flagged.' },
  { n: 3, title: 'Recommend', text: 'Contest, accept, or ask for more evidence.' },
  { n: 4, title: 'Draft rebuttal', text: 'Unsupported claims are removed before you see it.' },
  { n: 5, title: 'You approve', text: 'Nothing is sent until a named reviewer approves.' },
];

export default function WorkflowGuide() {
  return (
    <section aria-label="How a dispute moves through DisputePilot" className="p-4 sm:p-5 rounded-2xl bg-white/[0.02] border border-white/[0.06]">
      <h3 className="font-heading text-sm font-semibold text-white mb-3">How a dispute moves through DisputePilot</h3>
      <ol className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {STEPS.map((s) => (
          <li key={s.n} className="flex items-start gap-3">
            <span className="w-6 h-6 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 text-xs font-mono flex items-center justify-center flex-shrink-0">{s.n}</span>
            <div>
              <p className="text-xs font-semibold text-slate-200">{s.title}</p>
              <p className="text-xs text-slate-400 mt-0.5">{s.text}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
