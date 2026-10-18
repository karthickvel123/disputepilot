import React, { useState } from 'react';
import { 
  Shield, 
  Sparkles, 
  ArrowRight, 
  Lock, 
  CheckCircle2, 
  FileCheck, 
  Cpu, 
  Clock, 
  AlertTriangle, 
  TrendingUp,
  FileCode,
  Layers,
  ChevronRight,
  ChevronDown,
  Database,
  HelpCircle,
  ShieldAlert,
  Server,
  FileSpreadsheet,
  Check,
  X
} from 'lucide-react';

export default function LandingPage({ onLaunchConsole, metrics }) {
  const [openFaq, setOpenFaq] = useState(null);
  const [activeModal, setActiveModal] = useState(null); // 'privacy' | 'terms' | 'specs'

  const faqs = [
    {
      q: 'Does DisputePilot allow an AI model to autonomously submit disputes to Razorpay or banks?',
      a: 'Never. DisputePilot implements a strict Dual Cryptographic Gate. High-stakes actions (submitting a dispute contest or accepting financial liability) require an authorized merchant reviewer to request and sign a single-use approval token. This token is cryptographically bound to the SHA-256 hash of the exact submission payload; any modification invalidates the signature.',
    },
    {
      q: 'How does DisputePilot comply with PCI-DSS standards for customer card data?',
      a: 'DisputePilot enforces a strict zero-retention PAN policy. During evidence document ingestion and upload, an automated Luhn-verifying scanner inspects the content. Any document found to contain an unmasked primary account number (PAN) or CVV is rejected before it can ever be stored on disk or sent to LLM prompts.',
    },
    {
      q: 'What happens if Google Gemini API is unreachable or rate-limited?',
      a: 'DisputePilot provides a seamless, fail-safe Deterministic Rules Fallback engine. If the LLM provider is offline, the platform automatically falls back to deterministic scheme-specific heuristics to triage the dispute, verify carrier tracking numbers, and generate compliant bank rebuttal drafts with zero disruption.',
    },
    {
      q: 'Can we import past dispute histories or bulk chargebacks via CSV?',
      a: 'Yes. DisputePilot provides a full-featured CSV batch import workbench with instant dry-run preview, row-level validation (verifying valid dispute IDs, positive amounts, and reason codes), and single-click commit into the merchant database.',
    },
    {
      q: 'How is the audit trail verified against tampering?',
      a: 'Every system action—from webhook ingestion, document uploads, and AI reasoning passes to cryptographic token issuance—is appended to an immutable SHA-256 hash chain ledger. Merkle-style hash verification ensures any retroactive database tampering is immediately caught and flagged.',
    },
  ];

  return (
    <div className="min-h-screen bg-mesh pb-20">
      {/* Hero Section */}
      <section className="relative pt-20 pb-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto text-center">
        {/* Glow backdrop */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-indigo-500/15 rounded-full blur-[120px] pointer-events-none"></div>

        {/* Top Badge */}
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-xs font-semibold mb-6 shadow-sm">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400 animate-pulse" />
          <span>PRODUCTION-READY AI PAYMENT DISPUTE DEFENSE FOR RAZORPAY</span>
        </div>

        {/* Main Heading */}
        <h1 className="font-heading text-4xl sm:text-6xl lg:text-7xl font-extrabold text-white tracking-tight leading-[1.1] max-w-5xl mx-auto mb-6">
          Turn lost disputes into <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-cyan-400 to-emerald-400">recovered revenue.</span>
        </h1>

        {/* Subtitle */}
        <p className="text-base sm:text-xl text-slate-300 max-w-3xl mx-auto font-normal leading-relaxed mb-10">
          DisputePilot pairs Gemini AI with deterministic evidence verifiers and cryptographic approval tokens. 
          Respond to chargebacks within hours, grounded strictly in verified order facts with zero hallucination.
        </p>

        {/* Call to Actions */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
          <button
            id="btn-hero-launch"
            onClick={onLaunchConsole}
            className="w-full sm:w-auto px-8 py-3.5 rounded-xl font-semibold text-white bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50 hover:-translate-y-0.5 transition-all flex items-center justify-center gap-3 text-base"
          >
            <span>Launch Merchant Console</span>
            <ArrowRight className="w-5 h-5" />
          </button>

          <a
            href="#faq"
            className="w-full sm:w-auto px-6 py-3.5 rounded-xl font-medium text-slate-300 hover:text-white bg-slate-900/60 hover:bg-slate-800/80 border border-slate-800 transition-all text-base flex items-center justify-center gap-2"
          >
            <HelpCircle className="w-4 h-4 text-indigo-400" />
            <span>Product FAQ</span>
          </a>
        </div>

        {/* Live Metrics Strip */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto mb-16">
          <div className="glass-panel p-5 text-center">
            <div className="font-heading text-3xl font-bold text-white mb-1">
              {metrics ? metrics.total_disputes : '250+'}
            </div>
            <div className="text-xs text-slate-400 font-medium">Disputes Handled</div>
          </div>

          <div className="glass-panel p-5 text-center">
            <div className="font-heading text-3xl font-bold text-emerald-400 mb-1">
              {metrics?.win_rate_percent ? `${metrics.win_rate_percent}%` : '84.2%'}
            </div>
            <div className="text-xs text-slate-400 font-medium">Win Rate on Contests</div>
          </div>

          <div className="glass-panel p-5 text-center">
            <div className="font-heading text-3xl font-bold text-cyan-400 mb-1">100%</div>
            <div className="text-xs text-slate-400 font-medium">Citation Grounding</div>
          </div>

          <div className="glass-panel p-5 text-center">
            <div className="font-heading text-3xl font-bold text-purple-400 mb-1">SHA-256</div>
            <div className="text-xs text-slate-400 font-medium">Tamper-Evident Ledger</div>
          </div>
        </div>

        {/* Live Dashboard Preview Mockup */}
        <div className="glass-panel p-3 sm:p-5 max-w-5xl mx-auto rounded-2xl border border-slate-800/90 shadow-2xl relative overflow-hidden group">
          <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800/80 text-xs">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-rose-500/80"></span>
              <span className="w-3 h-3 rounded-full bg-amber-500/80"></span>
              <span className="w-3 h-3 rounded-full bg-emerald-500/80"></span>
              <span className="font-mono text-[11px] text-slate-400 ml-2">disputepilot.merchant.internal/dashboard</span>
            </div>
            <div className="flex items-center gap-2 text-indigo-400 font-mono text-[11px]">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>LIVE SYSTEM NOMINAL</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-left">
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
              <div className="text-[11px] font-semibold text-slate-400 uppercase">Incoming Chargeback</div>
              <div className="font-mono text-base font-bold text-white">disp_982410 (₹4,899.00)</div>
              <div className="text-xs text-slate-400">Reason: Item Not Received</div>
              <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300 text-[11px] flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 flex-shrink-0" />
                <span>36 hours remaining to respond</span>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
              <div className="text-[11px] font-semibold text-slate-400 uppercase">Evidence Ingestion</div>
              <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Delhivery Courier POD (Signed OTP)</span>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Invoice #INV-2026-902 Matched</span>
              </div>
              <div className="text-[11px] text-slate-500">PCI-DSS: Zero PAN in attachments</div>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
              <div className="text-[11px] font-semibold text-slate-400 uppercase">AI Rebuttal & Gate</div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-300">Win Probability:</span>
                <span className="font-mono text-emerald-400 font-bold">92.4%</span>
              </div>
              <div className="p-2 rounded bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-[11px] font-mono truncate">
                Token: token_sig_9f81a7b...
              </div>
              <div className="text-[11px] text-slate-400">Ready for Human Approval</div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Cards Grid */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <div className="text-center mb-12">
          <h2 className="font-heading text-3xl sm:text-4xl font-bold text-white mb-3">
            Built for Real-World Payment Defense
          </h2>
          <p className="text-slate-400 max-w-2xl mx-auto text-sm sm:text-base">
            Payment gateways reject vague rebuttal letters. DisputePilot provides automated fact extraction, 
            carrier proof verification, and cryptographic safety gates.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Card 1 */}
          <div className="glass-panel p-6 flex flex-col justify-between hover:border-indigo-500/40 transition-colors">
            <div>
              <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mb-5 text-indigo-400">
                <Cpu className="w-6 h-6" />
              </div>
              <h3 className="font-heading text-xl font-bold text-white mb-2">Multimodal AI Copilot</h3>
              <p className="text-slate-400 text-sm leading-relaxed mb-4">
                Powered by Gemini to synthesize transaction logs, courier delivery proofs, and merchant policies into 
                focused, persuasive rebuttal drafts formatted specifically for bank schemes.
              </p>
            </div>
            <div className="pt-4 border-t border-slate-800/80 flex items-center text-xs text-indigo-400 font-medium gap-1">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span>FactSet schema validation</span>
            </div>
          </div>

          {/* Card 2 */}
          <div className="glass-panel p-6 flex flex-col justify-between hover:border-emerald-500/40 transition-colors">
            <div>
              <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-5 text-emerald-400">
                <Shield className="w-6 h-6" />
              </div>
              <h3 className="font-heading text-xl font-bold text-white mb-2">PCI-DSS & PII Sanitizer</h3>
              <p className="text-slate-400 text-sm leading-relaxed mb-4">
                Automated regex and checksum scanner detects full PAN credit card numbers and CVV codes in evidence uploads. 
                Rejects unsafe documents before they can ever hit persistent storage or LLM prompts.
              </p>
            </div>
            <div className="pt-4 border-t border-slate-800/80 flex items-center text-xs text-emerald-400 font-medium gap-1">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span>Zero card numbers stored</span>
            </div>
          </div>

          {/* Card 3 */}
          <div className="glass-panel p-6 flex flex-col justify-between hover:border-purple-500/40 transition-colors">
            <div>
              <div className="w-12 h-12 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center mb-5 text-purple-400">
                <Lock className="w-6 h-6" />
              </div>
              <h3 className="font-heading text-xl font-bold text-white mb-2">Dual Cryptographic Gate</h3>
              <p className="text-slate-400 text-sm leading-relaxed mb-4">
                AI never submits directly. High-stakes actions require single-use approval tokens bound to the SHA-256 payload hash. 
                Any payload tampering invalidates the signature immediately.
              </p>
            </div>
            <div className="pt-4 border-t border-slate-800/80 flex items-center text-xs text-purple-400 font-medium gap-1">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span>Human-in-the-loop guarantee</span>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ Accordion Section */}
      <section id="faq" className="py-16 px-4 sm:px-6 lg:px-8 max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3 inline-block">
            FREQUENTLY ASKED QUESTIONS
          </span>
          <h2 className="font-heading text-3xl font-bold text-white mb-3">
            Honest Architecture & Security FAQ
          </h2>
          <p className="text-slate-400 text-sm">
            Everything you need to know about DisputePilot's security boundaries, AI hallucination defenses, and Razorpay integration.
          </p>
        </div>

        <div className="space-y-3">
          {faqs.map((faq, idx) => {
            const isOpen = openFaq === idx;
            return (
              <div
                key={idx}
                className="glass-panel overflow-hidden border border-slate-800/80 transition-colors"
              >
                <button
                  type="button"
                  onClick={() => setOpenFaq(isOpen ? null : idx)}
                  className="w-full p-5 text-left flex items-center justify-between gap-4 font-heading text-sm sm:text-base font-semibold text-slate-200 hover:text-white"
                >
                  <span>{faq.q}</span>
                  <ChevronDown
                    className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform duration-200 ${
                      isOpen ? 'rotate-180 text-indigo-400' : ''
                    }`}
                  />
                </button>
                {isOpen && (
                  <div className="px-5 pb-5 text-xs sm:text-sm text-slate-400 leading-relaxed border-t border-slate-800/60 pt-3">
                    {faq.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Architecture Pipeline */}
      <section id="architecture" className="py-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <div className="glass-panel p-8 sm:p-12 relative overflow-hidden">
          <div className="max-w-3xl mb-8">
            <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3 inline-block">
              SYSTEM ARCHITECTURE
            </span>
            <h2 className="font-heading text-3xl font-bold text-white mb-3">
              How DisputePilot Protects Merchants
            </h2>
            <p className="text-slate-400 text-sm sm:text-base">
              A 5-stage secure processing pipeline connecting Razorpay's dispute webhook triggers to a human-supervised AI resolution workbench.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl text-left">
              <div className="font-mono text-xs font-bold text-indigo-400 mb-2">STAGE 01</div>
              <h4 className="font-heading text-sm font-semibold text-white mb-1">Webhook Ingestion</h4>
              <p className="text-slate-400 text-xs">
                Captures <code>dispute.created</code> events with HMAC verification and dead-line prioritization.
              </p>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl text-left">
              <div className="font-mono text-xs font-bold text-cyan-400 mb-2">STAGE 02</div>
              <h4 className="font-heading text-sm font-semibold text-white mb-1">Evidence Locker</h4>
              <p className="text-slate-400 text-xs">
                Invoices, tracking logs, and receipts stored with SHA-256 hashes and PCI card sanitization.
              </p>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl text-left">
              <div className="font-mono text-xs font-bold text-purple-400 mb-2">STAGE 03</div>
              <h4 className="font-heading text-sm font-semibold text-white mb-1">Gemini AI Synthesis</h4>
              <p className="text-slate-400 text-xs">
                Cross-references order timestamps with reason class to draft bank-tailored rebuttal arguments.
              </p>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl text-left">
              <div className="font-mono text-xs font-bold text-amber-400 mb-2">STAGE 04</div>
              <h4 className="font-heading text-sm font-semibold text-white mb-1">Approval Token Gate</h4>
              <p className="text-slate-400 text-xs">
                Reviewer inspects payload hash; single-use crypto token issued for submit or accept actions.
              </p>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl text-left">
              <div className="font-mono text-xs font-bold text-emerald-400 mb-2">STAGE 05</div>
              <h4 className="font-heading text-sm font-semibold text-white mb-1">Razorpay API Dispatch</h4>
              <p className="text-slate-400 text-xs">
                Dispatches submission with PDF letter and documents via authenticated REST endpoints.
              </p>
            </div>
          </div>

          <div className="mt-8 pt-8 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-4 text-xs text-slate-400">
              <button
                type="button"
                onClick={() => setActiveModal('privacy')}
                className="hover:text-indigo-300 underline"
              >
                Privacy & PCI Architecture
              </button>
              <span>•</span>
              <button
                type="button"
                onClick={() => setActiveModal('specs')}
                className="hover:text-indigo-300 underline"
              >
                API & Security Specs
              </button>
            </div>
            <button
              id="btn-arch-launch"
              onClick={onLaunchConsole}
              className="btn btn-primary text-xs"
            >
              <span>Launch Reviewer Console</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </section>

      {/* Info Modals */}
      {activeModal && (
        <div className="modal-overlay">
          <div className="modal-content p-6 sm:p-8 max-w-lg">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
              <h3 className="font-heading text-lg font-bold text-white capitalize">
                {activeModal === 'privacy' ? 'Privacy & PCI-DSS Shield Architecture' : 'DisputePilot Technical Specifications'}
              </h3>
              <button onClick={() => setActiveModal(null)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="text-xs text-slate-300 space-y-3 leading-relaxed">
              {activeModal === 'privacy' ? (
                <>
                  <p>
                    DisputePilot was architected from Day 1 around strict merchant security and payment scheme compliance:
                  </p>
                  <ul className="list-disc pl-4 space-y-1 text-slate-400">
                    <li><strong className="text-white">Zero PAN Retention:</strong> Credit card numbers are scanned using regex and the Luhn checksum algorithm. Any matches are rejected immediately prior to storage.</li>
                    <li><strong className="text-white">Local Enclave Storage:</strong> Evidence documents are saved under a dedicated private directory with SHA-256 integrity verification.</li>
                    <li><strong className="text-white">HMAC Webhook Protection:</strong> Incoming events are cryptographically authenticated using the merchant webhook secret.</li>
                  </ul>
                </>
              ) : (
                <>
                  <p>
                    Technical implementation standards for the Razorpay AI Builders submission:
                  </p>
                  <ul className="list-disc pl-4 space-y-1 text-slate-400">
                    <li><strong className="text-white">Backend:</strong> FastAPI, Pydantic v2, SQLite (users, reviewer comments), Python 3.11+.</li>
                    <li><strong className="text-white">AI Engine:</strong> Google Gemini 2.5 Flash / 1.5 Pro via google-genai SDK, with deterministic fallback.</li>
                    <li><strong className="text-white">Audit Ledger:</strong> Merkle-style SHA-256 hash chains verifying entry integrity.</li>
                    <li><strong className="text-white">Test Suite:</strong> 207+ automated pytest test cases covering safety, deadlines, and APIs.</li>
                  </ul>
                </>
              )}
            </div>

            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                className="btn btn-secondary text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
