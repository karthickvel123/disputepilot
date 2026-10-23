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
    question: 'Can AI submit a dispute without a person reviewing it?',
    answer: 'No. A named reviewer must inspect the case and approve the exact submission. The approval is bound to the payload hash and can only be used once.',
  },
  {
    question: 'How does DisputePilot handle sensitive card data?',
    answer: 'Evidence is checked for unmasked card numbers before it is stored. Documents that fail the card-data scan are rejected or quarantined.',
  },
  {
    question: 'What if the AI provider is unavailable?',
    answer: 'The workflow can fall back to deterministic rules for triage and evidence checks. AI-generated content is not required for an approval or submission.',
  },
  {
    question: 'Can I import an existing dispute history?',
    answer: 'Yes. The worklist supports CSV import with a dry-run preview and row-level validation before records are created.',
  },
];

const safeguards = [
  {
    icon: ScanText,
    title: 'Evidence stays in context',
    detail: 'Bring order, delivery, and customer records together around the dispute.',
  },
  {
    icon: Clock3,
    title: 'Deadlines stay visible',
    detail: 'Make response windows clear so your team knows what needs attention.',
  },
  {
    icon: Fingerprint,
    title: 'Your team stays in control',
    detail: 'A reviewer checks the exact response before any decision is submitted.',
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
            PAYMENT DISPUTES, WITH CLARITY
          </span>
          <h1>Facts first.<br /><em>Fair responses.</em></h1>
          <p>
            A calmer way to manage payment disputes.
            Give your team the evidence, time, and confidence
            to make the right call.
          </p>
          <div className="sama-hero-actions">
            <button
              id="btn-hero-launch"
              type="button"
              onClick={isDemoAllowed ? (onQuickDemoLogin || onLaunchConsole) : onLaunchConsole}
              className="sama-hero-primary"
            >
              {isDemoAllowed ? 'Explore the demo' : 'Open merchant console'}
              <ArrowRight className="h-4 w-4" />
            </button>
            <a className="sama-hero-secondary" href="#approach">
              How it works <ArrowDown className="h-4 w-4" />
            </a>
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
            <span><i /> CASE IN REVIEW</span>
            <span>MERCHANT WORKSPACE</span>
          </div>
          <div className="hero-art-card">
            <div className="hero-art-summary">
              <span className="hero-art-label">DISPUTE REASON</span>
              <strong>Item not received</strong>
              <small>Case DP-0184 <span>·</span> Open</small>
            </div>
            <div className="hero-art-amount">
              <span className="hero-art-label">AMOUNT</span>
              <strong>₹4,899</strong>
              <small>INR</small>
            </div>
            <div className="hero-art-divider" />
            <div className="hero-art-evidence-label">
              <span>Evidence review</span>
              <span>2 of 3 matched</span>
            </div>
            <div className="hero-art-row">
              <PackageCheck className="h-4 w-4" />
              <span><strong>Delivery record</strong><small>Carrier confirmation</small></span>
              <CircleCheck className="hero-art-check h-4 w-4" />
            </div>
            <div className="hero-art-row">
              <FileCheck2 className="h-4 w-4" />
              <span><strong>Order invoice</strong><small>Purchase details</small></span>
              <CircleCheck className="hero-art-check h-4 w-4" />
            </div>
            <div className="hero-art-row hero-art-row-pending">
              <ScanText className="h-4 w-4" />
              <span><strong>Customer correspondence</strong><small>Review recommended</small></span>
              <span className="hero-art-pending">Review</span>
            </div>
            <div className="hero-art-deadline">
              <Clock3 className="h-4 w-4" />
              <span><strong>Response deadline</strong><small>36 hours remaining</small></span>
              <span className="hero-art-priority">Needs attention</span>
            </div>
            <div className="hero-art-footer">
              <span><LockKeyhole className="h-3.5 w-3.5" /> Awaiting reviewer approval</span>
              <span>NOT AUTO-SUBMITTED</span>
            </div>
          </div>
          <span className="hero-art-footnote">ILLUSTRATIVE CASE · SYNTHETIC DETAILS</span>
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
            <h3>Understand the case</h3>
            <p>See the dispute reason, amount, current status, and response deadline together.</p>
          </article>
          <article>
            <span>02</span>
            <h3>Bring facts together</h3>
            <p>Review relevant order details, customer records, and delivery evidence in context.</p>
          </article>
          <article>
            <span>03</span>
            <h3>Prepare a response</h3>
            <p>Create a fact-grounded draft and identify evidence that still needs attention.</p>
          </article>
          <article>
            <span>04</span>
            <h3>Approve before action</h3>
            <p>An authorized reviewer checks the exact payload before anything is submitted.</p>
          </article>
        </div>
      </section>

      <section className="landing-proof-band">
        <div className="landing-proof-heading">
          <span className="sama-section-kicker">BUILT AROUND TRUST</span>
          <h2>Technology can help.<br /><em>Your people decide.</em></h2>
        </div>
        <div className="landing-proof-details">
          <p>
            AI can help organize facts and prepare a draft. It cannot make the
            final decision or submit a dispute on its own. Every consequential
            action stays with an authorized human reviewer.
          </p>
          <div className="landing-proof-tags">
            <span><Check className="h-3.5 w-3.5" /> Evidence checks</span>
            <span><Check className="h-3.5 w-3.5" /> Card-data scanning</span>
            <span><Check className="h-3.5 w-3.5" /> Tamper-evident audit trail</span>
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
            <h3>Human authorization</h3>
            <p>Only an authorized reviewer can approve a contest or acceptance request.</p>
          </article>
          <article>
            <span><Fingerprint className="h-4 w-4" /></span>
            <h3>Payload-bound approval</h3>
            <p>Approval tokens are tied to the exact payload that the reviewer examined.</p>
          </article>
          <article>
            <span><ScanText className="h-4 w-4" /></span>
            <h3>Sensitive-data checks</h3>
            <p>Evidence is scanned for unmasked payment-card data before storage.</p>
          </article>
          <article>
            <span><FileCheck2 className="h-4 w-4" /></span>
            <h3>Auditable history</h3>
            <p>Important actions are recorded in a tamper-evident audit ledger.</p>
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
          type="button"
          onClick={isDemoAllowed ? (onQuickDemoLogin || onLaunchConsole) : onLaunchConsole}
          className="sama-last-call-button"
        >
          {isDemoAllowed ? 'Explore the demo' : 'Open merchant console'}
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
            <span className="sama-section-kicker">{activeModal === 'privacy' ? 'DATA PROTECTION' : 'PLATFORM OVERVIEW'}</span>
            <h2 id="landing-modal-title">
              {activeModal === 'privacy' ? 'Sensitive data stays protected.' : 'A reviewable, auditable workflow.'}
            </h2>
            {activeModal === 'privacy' ? (
              <ul className="landing-modal-list">
                <li><Check className="h-4 w-4" /><span>Card data scanning helps prevent unmasked numbers from being stored.</span></li>
                <li><Check className="h-4 w-4" /><span>Incoming webhooks are authenticated with HMAC verification.</span></li>
                <li><Check className="h-4 w-4" /><span>Evidence integrity is tracked with cryptographic hashes.</span></li>
              </ul>
            ) : (
              <ul className="landing-modal-list">
                <li><Check className="h-4 w-4" /><span>React-based merchant console backed by a FastAPI JSON API.</span></li>
                <li><Check className="h-4 w-4" /><span>AI-assisted drafting with deterministic verification and fallback.</span></li>
                <li><Check className="h-4 w-4" /><span>Human approval gates and a tamper-evident audit ledger.</span></li>
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
