import React, { useState } from 'react';
import {
  ArrowDown,
  ArrowRight,
  Check,
  ChevronDown,
  CircleCheck,
  Clock3,
  FileCheck2,
  Fingerprint,
  LockKeyhole,
  PackageCheck,
  ScanText,
  ShieldCheck,
  Sparkles,
  X,
  Zap,
} from 'lucide-react';

const faqs = [
  {
    question: 'How does DisputePilot automatically triage incoming disputes?',
    answer: 'When a dispute webhook arrives from Razorpay or is simulated, DisputePilot extracts transaction identifiers, classifies the chargeback reason (e.g. fraud, item not received, duplicate billing), scores the financial recoverability probability, and calculates the exact SLA countdown to ensure bank response deadlines are never missed.',
  },
  {
    question: 'Can AI submit a dispute without a human reviewer approving it?',
    answer: 'No. DisputePilot enforces a strict Separation of Duties. An authorized reviewer must inspect the matched evidence and approve the rebuttal letter. The approval is bound to a cryptographic SHA-256 payload hash and can only be used once.',
  },
  {
    question: 'How does DisputePilot handle sensitive card data and PCI-DSS compliance?',
    answer: 'All uploaded evidence documents and PDF excerpts pass through real-time Luhn algorithm card scanning. Unmasked 13-19 digit primary account numbers (PANs) are detected and quarantined before reaching storage or LLM context.',
  },
  {
    question: 'What happens if the Gemini AI API is offline or unconfigured?',
    answer: 'DisputePilot features a 100% deterministic fallback drafting engine. It synthesizes structured, bank-compliant rebuttal letters citing matched invoices and delivery proofs using rules and templates without requiring any external AI API.',
  },
  {
    question: 'How does DisputePilot submit contests to Razorpay?',
    answer: 'DisputePilot operates a dual-gateway architecture: in Simulated Mode (DATA_MODE=sim), disputes and submissions run against realistic local fixtures; in Live Mode (DATA_MODE=live), it calls Razorpay’s official Dispute API and document upload endpoints.',
  },
  {
    question: 'How does the Tamper-Evident Audit Ledger work?',
    answer: 'Every state transition, evidence ingestion, AI draft generation, and reviewer sign-off is recorded with a cryptographically chained SHA-256 HMAC entry in SQLite, providing an immutable audit trail for compliance and chargeback accounting.',
  },
];

const safeguards = [
  {
    icon: ScanText,
    title: 'Evidence stays in context',
    detail: 'Automatically matches order invoices, carrier delivery tracking, and customer communications into a unified Evidence Locker.',
  },
  {
    icon: Clock3,
    title: 'Bank deadlines stay visible',
    detail: 'Real-time SLA countdown timers prioritize disputes nearing expiry so your team never forfeits a winnable chargeback.',
  },
  {
    icon: Fingerprint,
    title: 'Your team stays in control',
    detail: 'Cryptographic payload-bound approval tokens guarantee that an authorized human reviewer signs off on every contest packet.',
  },
];

export default function LandingPage({
  onLaunchConsole,
  onQuickDemoLogin,
  onSimulateDispute,
  metrics,
  isDemoAllowed = false,
  isSimMode = false,
}) {
  const [openFaq, setOpenFaq] = useState(0);
  const [activeModal, setActiveModal] = useState(null);
  const [simulating, setSimulating] = useState(false);
  const [launchingDemo, setLaunchingDemo] = useState(false);
  const [activeStage, setActiveStage] = useState(1);

  async function handleLaunchDemoClick() {
    if (onQuickDemoLogin) {
      setLaunchingDemo(true);
      try {
        await onQuickDemoLogin();
      } finally {
        setLaunchingDemo(false);
      }
    } else if (onLaunchConsole) {
      onLaunchConsole();
    }
  }

  async function handleSimulateClick() {
    if (!onSimulateDispute) return;
    setSimulating(true);
    try {
      await onSimulateDispute();
    } finally {
      setSimulating(false);
    }
  }

  const disputeCount = Number.isFinite(metrics?.total_disputes)
    ? metrics.total_disputes.toLocaleString('en-IN')
    : null;
  const winRate = Number.isFinite(metrics?.win_rate_percent)
    ? `${metrics.win_rate_percent}%`
    : null;

  return (
    <div className="landing-page">
      <section className="sama-inspired-hero">
        <div className="hero-atmosphere" aria-hidden="true">
          <span className="hero-orbit hero-orbit-one" />
          <span className="hero-orbit hero-orbit-two" />
          <span className="hero-horizon" />
          <span className="hero-light hero-light-left" />
          <span className="hero-light hero-light-right" />
          <span className="hero-grain" />
        </div>

        <div className="sama-hero-content">
          <span className="sama-hero-kicker">
            <span />
            AUTONOMOUS CHARGEBACK DEFENSE FOR RAZORPAY
          </span>
          <h1>Facts first.<br /><em>Fair responses.</em></h1>
          <p>
            Autonomous payment dispute intelligence for modern merchants.
            Automate triage, correlate evidence across orders, generate bank-grade
            rebuttals, and empower reviewers to contest chargebacks with confidence.
          </p>
          <div className="sama-hero-actions">
            <button
              id="btn-hero-launch-demo"
              type="button"
              disabled={launchingDemo}
              onClick={handleLaunchDemoClick}
              className="sama-hero-primary"
            >
              <Sparkles className="h-4 w-4" />
              {launchingDemo ? 'Launching demo…' : 'Launch Demo'}
              <ArrowRight className="h-4 w-4" />
            </button>
            <button
              id="btn-hero-signin"
              type="button"
              onClick={onLaunchConsole}
              className="sama-hero-secondary"
            >
              Sign In
            </button>
            <a className="sama-hero-secondary" href="#approach">
              How it works <ArrowDown className="h-4 w-4" />
            </a>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '12px', fontSize: '13px', color: '#8fa596' }}>
            <span style={{ display: 'inline-block', width: '7px', height: '7px', borderRadius: '50%', backgroundColor: '#4ade80', boxShadow: '0 0 10px rgba(74,222,128,0.7)' }} />
            <span>Click <strong>Launch Demo</strong> for instant access to live dispute operations</span>
          </div>
          {onSimulateDispute && (
            <button
              id="btn-hero-simulate"
              type="button"
              disabled={simulating}
              onClick={handleSimulateClick}
              className="sama-hero-simulate"
            >
              <Zap className="h-3.5 w-3.5" />
              {simulating ? 'Creating sample dispute…' : 'Try a sample dispute'}
            </button>
          )}
        </div>

        <div className="sama-hero-bottomline">
          <span>{isSimMode ? 'INTERACTIVE DEMO ENVIRONMENT' : 'BUILT FOR PAYMENT TEAMS'}</span>
          <span><ShieldCheck className="h-3.5 w-3.5" /> HUMAN APPROVAL ALWAYS REQUIRED</span>
        </div>

        <div className="hero-case-art" aria-label="Illustrative dispute case review">
          <div className="hero-art-topline">
            <span><i /> STAGE {activeStage} OF 4 · {activeStage === 1 ? 'WEBHOOK INGEST' : activeStage === 2 ? 'EVIDENCE MATCH' : activeStage === 3 ? 'AI REBUTTAL' : 'HUMAN APPROVAL'}</span>
            <div style={{ display: 'flex', gap: '3px' }}>
              {[1, 2, 3, 4].map((step) => (
                <button
                  key={step}
                  type="button"
                  onClick={() => setActiveStage(step)}
                  style={{
                    padding: '2px 6px',
                    fontSize: '9px',
                    fontWeight: 700,
                    borderRadius: '4px',
                    border: '1px solid',
                    borderColor: activeStage === step ? '#5e9a79' : 'rgba(0,0,0,0.15)',
                    background: activeStage === step ? '#eef7f2' : 'transparent',
                    color: activeStage === step ? '#275239' : '#849087',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                  title={`View Stage 0${step}`}
                >
                  0{step}
                </button>
              ))}
            </div>
          </div>
          <div className="hero-art-card">
            {activeStage === 1 && (
              <>
                <div className="hero-art-summary">
                  <span className="hero-art-label">01 · INGEST & TRIAGE</span>
                  <strong>Item not received (INR)</strong>
                  <small>Razorpay Webhook · disp_fraud_001 <span>·</span> 94% Win Score</small>
                </div>
                <div className="hero-art-amount">
                  <span className="hero-art-label">DISPUTE AMOUNT</span>
                  <strong>₹4,899</strong>
                  <small>INR · Escalated</small>
                </div>
                <div className="hero-art-divider" />
                <div className="hero-art-evidence-label">
                  <span>Intelligent Triage Pipeline</span>
                  <span>Verified</span>
                </div>
                <div className="hero-art-row">
                  <PackageCheck className="h-4 w-4" />
                  <span><strong>Webhook Authenticity</strong><small>HMAC-SHA256 signature verified</small></span>
                  <CircleCheck className="hero-art-check h-4 w-4" />
                </div>
                <div className="hero-art-row">
                  <FileCheck2 className="h-4 w-4" />
                  <span><strong>Chargeback Classification</strong><small>Non-receipt categorized</small></span>
                  <CircleCheck className="hero-art-check h-4 w-4" />
                </div>
                <div className="hero-art-deadline">
                  <Clock3 className="h-4 w-4" />
                  <span><strong>Bank Response Deadline</strong><small>36 hours remaining</small></span>
                  <span className="hero-art-priority">Needs attention</span>
                </div>
                <div className="hero-art-footer">
                  <span>⚡ Triage Complete</span>
                  <span>MOVING TO EVIDENCE</span>
                </div>
              </>
            )}

            {activeStage === 2 && (
              <>
                <div className="hero-art-summary">
                  <span className="hero-art-label">02 · EVIDENCE MATCHING</span>
                  <strong>Order #ORD-9021 Correlated</strong>
                  <small>2 of 3 Documents Auto-Retrieved</small>
                </div>
                <div className="hero-art-amount">
                  <span className="hero-art-label">EVIDENCE HEALTH</span>
                  <strong>2/3 Matched</strong>
                  <small>Locker Encrypted</small>
                </div>
                <div className="hero-art-divider" />
                <div className="hero-art-evidence-label">
                  <span>Evidence Review & PCI Scan</span>
                  <span>Passed</span>
                </div>
                <div className="hero-art-row">
                  <PackageCheck className="h-4 w-4" />
                  <span><strong>BlueDart Carrier POD</strong><small>Recipient signature verified</small></span>
                  <CircleCheck className="hero-art-check h-4 w-4" />
                </div>
                <div className="hero-art-row">
                  <FileCheck2 className="h-4 w-4" />
                  <span><strong>Order Tax Invoice</strong><small>Matches billing & shipping address</small></span>
                  <CircleCheck className="hero-art-check h-4 w-4" />
                </div>
                <div className="hero-art-row">
                  <ScanText className="h-4 w-4" />
                  <span><strong>PCI-DSS Card Shield</strong><small>0 unmasked PANs found</small></span>
                  <CircleCheck className="hero-art-check h-4 w-4" />
                </div>
                <div className="hero-art-footer">
                  <span>🛡️ Evidence Locked</span>
                  <span>READY FOR REBUTTAL</span>
                </div>
              </>
            )}

            {activeStage === 3 && (
              <>
                <div className="hero-art-summary">
                  <span className="hero-art-label">03 · REBUTTAL SYNTHESIS</span>
                  <strong>Bank-Grade Defense Draft</strong>
                  <small>Grounded in 2 Evidence Citations</small>
                </div>
                <div className="hero-art-amount">
                  <span className="hero-art-label">NETWORK RULES</span>
                  <strong>Visa / RuPay</strong>
                  <small>Compliant</small>
                </div>
                <div className="hero-art-divider" />
                <div className="hero-art-evidence-label">
                  <span>AI & Rule-Based Synthesis</span>
                  <span>Complete</span>
                </div>
                <div className="hero-art-row">
                  <FileCheck2 className="h-4 w-4" />
                  <span><strong>Acquirer Addressed</strong><small>HDFC Settlement Dept</small></span>
                  <CircleCheck className="hero-art-check h-4 w-4" />
                </div>
                <div className="hero-art-row">
                  <ScanText className="h-4 w-4" />
                  <span><strong>Evidence Citations</strong><small>Cites POD [Doc #1] & Invoice [Doc #2]</small></span>
                  <CircleCheck className="hero-art-check h-4 w-4" />
                </div>
                <div className="hero-art-row">
                  <PackageCheck className="h-4 w-4" />
                  <span><strong>Deterministic Guarantee</strong><small>100% rule fallback reliability</small></span>
                  <CircleCheck className="hero-art-check h-4 w-4" />
                </div>
                <div className="hero-art-footer">
                  <span>✍️ Draft Synthesized</span>
                  <span>AWAITING APPROVAL</span>
                </div>
              </>
            )}

            {activeStage === 4 && (
              <>
                <div className="hero-art-summary">
                  <span className="hero-art-label">04 · HUMAN AUTHORIZATION</span>
                  <strong>Single-Use Approval Token</strong>
                  <small>Reviewer: ops_reviewer <span>·</span> Two-Party</small>
                </div>
                <div className="hero-art-amount">
                  <span className="hero-art-label">SUBMISSION STATE</span>
                  <strong>Contested</strong>
                  <small>API Verified</small>
                </div>
                <div className="hero-art-divider" />
                <div className="hero-art-evidence-label">
                  <span>Cryptographic Governance</span>
                  <span>Active</span>
                </div>
                <div className="hero-art-row">
                  <LockKeyhole className="h-4 w-4" />
                  <span><strong>Payload-Bound Token</strong><small>sha256:7adc7ad6... locked</small></span>
                  <CircleCheck className="hero-art-check h-4 w-4" />
                </div>
                <div className="hero-art-row">
                  <Fingerprint className="h-4 w-4" />
                  <span><strong>Reviewer Sign-Off</strong><small>Approved by ops_reviewer</small></span>
                  <CircleCheck className="hero-art-check h-4 w-4" />
                </div>
                <div className="hero-art-row">
                  <ShieldCheck className="h-4 w-4" />
                  <span><strong>Immutable Audit Ledger</strong><small>Event #4092 committed</small></span>
                  <CircleCheck className="hero-art-check h-4 w-4" />
                </div>
                <div className="hero-art-footer">
                  <span>🔒 Contest Filed to Bank</span>
                  <span>AUDIT COMMITTED</span>
                </div>
              </>
            )}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px', padding: '0 4px' }}>
            <span className="hero-art-footnote">INTERACTIVE WORKFLOW · CLICK 01-04</span>
            <button
              type="button"
              onClick={() => setActiveStage((s) => (s % 4) + 1)}
              style={{
                fontSize: '9px',
                fontWeight: 600,
                color: '#275239',
                background: '#eef7f2',
                border: '1px solid #5e9a79',
                borderRadius: '4px',
                padding: '2px 8px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '3px',
              }}
            >
              Next Stage ➔
            </button>
          </div>
        </div>
      </section>

      <section className="landing-story">
        <div className="landing-story-intro">
          <span className="sama-section-kicker">A BETTER WAY TO WORK THROUGH A DISPUTE</span>
          <h2>Make room for<br /><em>the right decision.</em></h2>
          <p>
            Disputes can be time-sensitive and difficult to piece together.
            DisputePilot helps your team see what happened, gather the available
            evidence, and prepare a response for a person to review.
          </p>
          <button type="button" className="landing-story-link" onClick={onLaunchConsole}>
            See the merchant workspace <ArrowRight className="h-4 w-4" />
          </button>
        </div>
        <div className="landing-story-list">
          {safeguards.map(({ icon: Icon, title, detail }, index) => (
            <article className="landing-story-row" key={title}>
              <span className="landing-story-index">0{index + 1}</span>
              <span className="landing-story-icon"><Icon className="h-4 w-4" /></span>
              <span className="landing-story-copy">
                <strong>{title}</strong>
                <small>{detail}</small>
              </span>
              <Check className="landing-story-check h-4 w-4" />
            </article>
          ))}
        </div>
      </section>

      <section id="approach" className="landing-approach">
        <div className="landing-approach-heading">
          <span className="sama-section-kicker">FROM NOTICE TO NEXT STEP</span>
          <h2>A thoughtful process.<br /><em>A human decision.</em></h2>
        </div>
        <div className="landing-approach-grid">
          <article>
            <span>01</span>
            <h3>Ingest & Triage</h3>
            <p>Ingest notices via webhooks, auto-classify chargeback reasons (fraud, non-receipt, billing), score recoverability, and compute strict bank SLA deadlines.</p>
          </article>
          <article>
            <span>02</span>
            <h3>Match Evidence</h3>
            <p>Correlate order IDs to automatically pull proof-of-delivery receipts, tax invoices, and customer chat history into a secure Evidence Locker.</p>
          </article>
          <article>
            <span>03</span>
            <h3>Draft Rebuttals</h3>
            <p>Synthesize structured, citation-grounded rebuttal letters tailored to payment network rules, backed by our 100% deterministic fallback engine.</p>
          </article>
          <article>
            <span>04</span>
            <h3>Approve & Submit</h3>
            <p>An authorized reviewer examines the packet and issues a cryptographic, single-use SHA-256 approval token before the contest is submitted.</p>
          </article>
        </div>
      </section>

      <section className="landing-proof-band">
        <div className="landing-proof-heading">
          <span className="sama-section-kicker">BUILT AROUND ENTERPRISE TRUST</span>
          <h2>Technology accelerates.<br /><em>Your reviewers decide.</em></h2>
        </div>
        <div className="landing-proof-details">
          <p>
            AI and rule engines automate evidence correlation and rebuttal letter drafting, but never make unilateral financial decisions. Every contest or acceptance requires explicit, single-use cryptographic authorization from a designated reviewer.
          </p>
          <div className="landing-proof-tags">
            <span><Check className="h-3.5 w-3.5" /> PCI-DSS Card Scanning</span>
            <span><Check className="h-3.5 w-3.5" /> 100% Deterministic Fallback</span>
            <span><Check className="h-3.5 w-3.5" /> Tamper-Evident HMAC Ledger</span>
            <span><Check className="h-3.5 w-3.5" /> Dual-Gateway (Sim/Live)</span>
          </div>
        </div>
      </section>

      <section className="landing-snapshot">
        <div className="landing-snapshot-copy">
          <span className="sama-section-kicker">YOUR WORKSPACE, AT A GLANCE</span>
          <h2>Keep every open case<br />moving forward.</h2>
          <p>See your current queue, outstanding reviews, and response deadlines in one place.</p>
        </div>
        <div className="landing-snapshot-stats">
          <article>
            <span>CASES IN WORKSPACE</span>
            <strong>{disputeCount ?? '—'}</strong>
            <small>{disputeCount === null ? 'Sign in to see your case data' : 'Current workspace total'}</small>
          </article>
          <article>
            <span>RECORDED CONTEST WIN RATE</span>
            <strong>{winRate ?? '—'}</strong>
            <small>{winRate ? 'Historical outcome data' : 'Available when outcomes are recorded'}</small>
          </article>
          <small className="landing-snapshot-disclaimer">Case outcomes depend on card-scheme adjudication.</small>
        </div>
      </section>

      <section id="security" className="landing-security">
        <div className="landing-security-heading">
          <span className="sama-section-kicker">SAFEGUARDS AT EVERY STEP</span>
          <h2>Clear boundaries.<br /><em>Accountable actions.</em></h2>
        </div>
        <div className="landing-security-grid">
          <article>
            <span><LockKeyhole className="h-4 w-4" /></span>
            <h3>Separation of Duties</h3>
            <p>Enforces two-party governance so AI models cannot unilaterally submit chargeback contests to banks.</p>
          </article>
          <article>
            <span><Fingerprint className="h-4 w-4" /></span>
            <h3>Payload-Bound Tokens</h3>
            <p>Cryptographic single-use SHA-256 tokens ensure only the exact approved letter and evidence packet can be filed.</p>
          </article>
          <article>
            <span><ScanText className="h-4 w-4" /></span>
            <h3>PCI-DSS Shield</h3>
            <p>Real-time Luhn algorithm scanning scrubs and quarantines raw card numbers from uploaded documents.</p>
          </article>
          <article>
            <span><FileCheck2 className="h-4 w-4" /></span>
            <h3>Chained Audit Ledger</h3>
            <p>Immutable HMAC-chained event logging records every state change, triage decision, and human review.</p>
          </article>
        </div>
      </section>

      <section id="faq" className="landing-questions">
        <div className="landing-questions-heading">
          <span className="sama-section-kicker">A FEW USEFUL ANSWERS</span>
          <h2>Questions about<br /><em>how it works?</em></h2>
          <button type="button" className="landing-story-link" onClick={() => setActiveModal('specs')}>
            Read the technical overview <ArrowRight className="h-4 w-4" />
          </button>
        </div>
        <div className="landing-question-list">
          {faqs.map((faq, index) => {
            const expanded = openFaq === index;
            return (
              <article className={`landing-question${expanded ? ' is-expanded' : ''}`} key={faq.question}>
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setOpenFaq(expanded ? null : index)}
                >
                  <span>{faq.question}</span>
                  <ChevronDown className="h-4 w-4" />
                </button>
                {expanded && <p>{faq.answer}</p>}
              </article>
            );
          })}
        </div>
      </section>

      <section className="landing-last-call">
        <span className="sama-section-kicker">A CLEARER WORKFLOW STARTS HERE</span>
        <h2>Bring clarity to<br /><em>the next dispute.</em></h2>
        <button
          id="btn-last-call-launch-demo"
          type="button"
          disabled={launchingDemo}
          onClick={handleLaunchDemoClick}
          className="sama-last-call-button"
        >
          <Sparkles className="h-4 w-4" />
          {launchingDemo ? 'Launching demo…' : 'Launch Demo'}
          <ArrowRight className="h-4 w-4" />
        </button>
      </section>

      <footer className="landing-footer">
        <div>
          <span className="landing-footer-brand"><ShieldCheck className="h-4 w-4" /> DisputePilot</span>
          <span>Dispute operations, with people in control.</span>
        </div>
        <div className="landing-footer-links">
          <a href="#approach">Our approach</a>
          <a href="#security">Safeguards</a>
          <a href="#faq">FAQs</a>
          <button type="button" onClick={() => setActiveModal('privacy')}>Privacy & card data</button>
        </div>
      </footer>

      {activeModal && (
        <div
          className="modal-overlay landing-modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setActiveModal(null);
          }}
        >
          <section className="modal-content landing-modal" role="dialog" aria-modal="true" aria-labelledby="landing-modal-title">
            <div className="landing-modal-heading">
              <span className="landing-feature-icon is-blue">
                {activeModal === 'privacy' ? <LockKeyhole className="h-5 w-5" /> : <FileCheck2 className="h-5 w-5" />}
              </span>
              <button type="button" className="landing-modal-close" onClick={() => setActiveModal(null)} aria-label="Close">
                <X className="h-4 w-4" />
              </button>
            </div>
            <span className="sama-section-kicker">{activeModal === 'privacy' ? 'DATA PROTECTION & PCI-DSS' : 'SYSTEM ARCHITECTURE'}</span>
            <h2 id="landing-modal-title">
              {activeModal === 'privacy' ? 'Defense-in-depth for cardholder data.' : 'Autonomous, reviewable, and auditable.'}
            </h2>
            {activeModal === 'privacy' ? (
              <ul className="landing-modal-list">
                <li><Check className="h-4 w-4" /><span><strong>PCI-DSS Shield:</strong> Real-time Luhn algorithm scanning scrubs raw card numbers from uploaded documents and PDF excerpts.</span></li>
                <li><Check className="h-4 w-4" /><span><strong>Webhook Authenticity:</strong> All incoming Razorpay event notifications are validated using strict HMAC-SHA256 signatures.</span></li>
                <li><Check className="h-4 w-4" /><span><strong>Cryptographic Integrity:</strong> Evidence files are hashed at rest, guaranteeing zero post-upload document tampering.</span></li>
                <li><Check className="h-4 w-4" /><span><strong>Secure Session Cookies:</strong> Encrypted, HttpOnly, SameSite=None/Lax cookies with CSRF token protection.</span></li>
              </ul>
            ) : (
              <ul className="landing-modal-list">
                <li><Check className="h-4 w-4" /><span><strong>Modern Full-Stack:</strong> React + Vite SPA backed by Python 3.12 FastAPI with async SQLite storage.</span></li>
                <li><Check className="h-4 w-4" /><span><strong>Dual-Gateway Pipeline:</strong> Instant offline simulation via SimGateway or production contests via RazorpayGateway.</span></li>
                <li><Check className="h-4 w-4" /><span><strong>Hybrid Rebuttal Studio:</strong> Google Gemini 2.5 generative drafting paired with a 100% deterministic rule fallback engine.</span></li>
                <li><Check className="h-4 w-4" /><span><strong>Cryptographic Approval Gate:</strong> Single-use SHA-256 payload authorization tokens with independent reviewer enforcement.</span></li>
                <li><Check className="h-4 w-4" /><span><strong>Immutable Audit Ledger:</strong> Append-only event tracking for compliance, SOC2 readiness, and dispute reconciliation.</span></li>
              </ul>
            )}
            <button type="button" onClick={() => setActiveModal(null)} className="landing-button landing-button-primary landing-modal-done">
              Done <ArrowRight className="h-4 w-4" />
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
