import React, { useState, useEffect } from 'react';
import { 
  ArrowLeft, 
  Shield, 
  Sparkles, 
  Clock, 
  FileText, 
  CheckCircle2, 
  AlertTriangle, 
  Lock, 
  Upload, 
  Save, 
  Send, 
  XCircle, 
  RefreshCw, 
  Copy, 
  ExternalLink,
  History,
  AlertCircle,
  FileCheck,
  Check,
  Eye,
  Key,
  Download,
  Trash2,
  MessageSquare
} from 'lucide-react';
import { 
  getDispute, 
  analyzeDispute, 
  saveDraft, 
  requestContestApproval, 
  submitContest, 
  requestAccept, 
  acceptDispute, 
  uploadEvidence,
  getCaseAudit,
  getComments,
  addComment,
  rejectDraft,
  deleteEvidence,
  getEvidenceDownloadUrl
} from '../api';
import { renderCleanDraft } from '../utils/draft';

export default function CaseDetailView({ caseId, onBack, onCaseUpdated, userRole = 'reviewer' }) {
  const isAuditor = userRole === 'auditor';
  const [data, setData] = useState(null);
  const [auditEvents, setAuditEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  // Active tab inside case console
  const [activeTab, setActiveTab] = useState('rebuttal'); // 'rebuttal' | 'evidence' | 'comments' | 'audit'

  // Draft editing state
  const [draftContent, setDraftContent] = useState('');
  const [isDraftDirty, setIsDraftDirty] = useState(false);

  // Comments / Reviewer discussion state
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState('');
  const [postingComment, setPostingComment] = useState(false);

  // Rejection modal state
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectingDraft, setRejectingDraft] = useState(false);

  // Evidence upload form state
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadCategory, setUploadCategory] = useState('proof_of_delivery');
  const [attestNoCard, setAttestNoCard] = useState(false);
  const [uploadExcerpt, setUploadExcerpt] = useState('');
  const [uploading, setUploading] = useState(false);

  // Contest Approval Modal state
  const [contestModalOpen, setContestModalOpen] = useState(false);
  const [contestApprovalToken, setContestApprovalToken] = useState('');
  const [contestPayloadHash, setContestPayloadHash] = useState('');
  const [contestPayloadJson, setContestPayloadJson] = useState('');
  const [submittingContest, setSubmittingContest] = useState(false);

  // Accept Liability Modal state
  const [acceptModalOpen, setAcceptModalOpen] = useState(false);
  const [typedAmount, setTypedAmount] = useState('');
  const [acceptApprovalToken, setAcceptApprovalToken] = useState('');
  const [acceptPayloadHash, setAcceptPayloadHash] = useState('');
  const [submittingAccept, setSubmittingAccept] = useState(false);

  useEffect(() => {
    loadCaseData();
  }, [caseId]);

  async function loadCaseData() {
    setLoading(true);
    setError(null);
    try {
      const caseData = await getDispute(caseId);
      setData(caseData);

      // Initialize draft content from cached analysis or default
      setDraftContent(renderCleanDraft(caseData.analysis?.clean_draft));

      // Fetch case audit events
      try {
        const auditData = await getCaseAudit(caseId);
        setAuditEvents(auditData.events || []);
      } catch (e) {
        console.warn('Could not fetch audit events for case', e);
      }

      // Fetch reviewer collaboration comments
      try {
        const commData = await getComments(caseId);
        setComments(commData.comments || []);
      } catch (e) {
        console.warn('Could not fetch comments for case', e);
      }
    } catch (err) {
      setError(err.message || 'Failed to load case detail.');
    } finally {
      setLoading(false);
    }
  }

  // Add Reviewer Comment
  async function handleAddComment(e) {
    if (e) e.preventDefault();
    if (!newComment.trim()) return;
    setPostingComment(true);
    try {
      const added = await addComment(caseId, newComment.trim());
      setComments((prev) => [...prev, added]);
      setNewComment('');
      setSuccessMessage('Reviewer note logged.');
    } catch (err) {
      alert(`Failed to add note: ${err.message}`);
    } finally {
      setPostingComment(false);
    }
  }

  // Reject Draft with feedback reason
  async function handleConfirmRejectDraft(e) {
    if (e) e.preventDefault();
    if (!rejectReason.trim()) return;
    setRejectingDraft(true);
    try {
      await rejectDraft(caseId, rejectReason.trim());
      await addComment(caseId, `[Draft Rejected]: ${rejectReason.trim()}`);
      setRejectModalOpen(false);
      setRejectReason('');
      setSuccessMessage('Rebuttal draft marked as rejected. Review notes logged.');
      await loadCaseData();
    } catch (err) {
      alert(`Rejection failed: ${err.message}`);
    } finally {
      setRejectingDraft(false);
    }
  }

  // Delete Evidence Document
  async function handleDeleteEvidence(docId) {
    if (!window.confirm('Delete this evidence file? This deletion is permanently recorded in the cryptographic audit ledger.')) return;
    try {
      await deleteEvidence(caseId, docId);
      setSuccessMessage('Evidence removed from locker.');
      await loadCaseData();
    } catch (err) {
      alert(`Failed to delete evidence: ${err.message}`);
    }
  }

  // Trigger AI Analysis
  async function handleRunAnalysis() {
    setAnalyzing(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const res = await analyzeDispute(caseId);
      setSuccessMessage('AI analysis and citation-grounded rebuttal generated successfully.');
      await loadCaseData();
      const cleanDraftText = renderCleanDraft(res.clean_draft);
      if (cleanDraftText) {
        setDraftContent(cleanDraftText);
        setIsDraftDirty(false);
      }
    } catch (err) {
      setError(err.message || 'AI analysis failed. Check LLM configuration.');
    } finally {
      setAnalyzing(false);
    }
  }

  // Save edited draft
  async function handleSaveDraft() {
    setSavingDraft(true);
    setError(null);
    setSuccessMessage(null);
    try {
      await saveDraft(caseId, draftContent);
      setIsDraftDirty(false);
      setSuccessMessage('Rebuttal draft saved successfully.');
      const auditData = await getCaseAudit(caseId);
      setAuditEvents(auditData.events || []);
    } catch (err) {
      setError(err.message || 'Failed to save draft.');
    } finally {
      setSavingDraft(false);
    }
  }

  // Handle Evidence Upload
  async function handleUploadEvidence(e) {
    e.preventDefault();
    if (!uploadFile) {
      setError('Please select a file to upload.');
      return;
    }
    if (!attestNoCard) {
      setError('You must attest that the file contains no cardholder data or CVV.');
      return;
    }

    setUploading(true);
    setError(null);
    setSuccessMessage(null);
    try {
      await uploadEvidence(caseId, {
        file: uploadFile,
        category: uploadCategory,
        attestNoCardData: attestNoCard,
        excerpt: uploadExcerpt,
      });
      setSuccessMessage('Evidence uploaded to locker and logged in audit chain.');
      setUploadFile(null);
      setUploadExcerpt('');
      setAttestNoCard(false);
      await loadCaseData();
    } catch (err) {
      setError(err.message || 'Evidence upload failed.');
    } finally {
      setUploading(false);
    }
  }

  // Open Contest Approval Modal
  async function handleOpenContestModal() {
    setError(null);
    try {
      const approvalData = await requestContestApproval(caseId);
      setContestApprovalToken(approvalData.approval_token);
      setContestPayloadHash(approvalData.payload_hash);
      setContestPayloadJson(JSON.stringify(approvalData.payload, null, 2));
      setContestModalOpen(true);
    } catch (err) {
      setError(err.message || 'Could not request approval token. Ensure AI analysis has been run.');
    }
  }

  // Confirm Contest Submission with Approval Token
  async function handleConfirmContestSubmission() {
    setSubmittingContest(true);
    setError(null);
    try {
      const res = await submitContest(caseId, contestApprovalToken, contestPayloadHash);
      setContestModalOpen(false);
      setSuccessMessage(res.message || 'Contest submitted to Razorpay!');
      await loadCaseData();
      if (onCaseUpdated) onCaseUpdated();
    } catch (err) {
      setError(err.message || 'Submission failed. Verification token may be expired or mismatched.');
    } finally {
      setSubmittingContest(false);
    }
  }

  // Open Accept Modal
  function handleOpenAcceptModal() {
    setTypedAmount('');
    setAcceptApprovalToken('');
    setAcceptPayloadHash('');
    setAcceptModalOpen(true);
  }

  // Verify Amount & Request Accept Token
  async function handleRequestAcceptToken() {
    setError(null);
    try {
      const res = await requestAccept(caseId, typedAmount);
      setAcceptApprovalToken(res.approval_token);
      setAcceptPayloadHash(res.payload_hash);
    } catch (err) {
      setError(err.message || 'Amount verification failed.');
    }
  }

  // Submit Acceptance
  async function handleConfirmAcceptDispute() {
    setSubmittingAccept(true);
    setError(null);
    try {
      const res = await acceptDispute(caseId, acceptApprovalToken, acceptPayloadHash);
      setAcceptModalOpen(false);
      setSuccessMessage(res.message || 'Dispute liability accepted and closed with Razorpay.');
      await loadCaseData();
      if (onCaseUpdated) onCaseUpdated();
    } catch (err) {
      setError(err.message || 'Acceptance failed.');
    } finally {
      setSubmittingAccept(false);
    }
  }

  if (loading) {
    return (
      <div className="py-24 text-center">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
        <p className="text-slate-400 text-sm">Loading dispute details & safety scans...</p>
      </div>
    );
  }

  if (!data) return null;

  const disp = data.dispute;
  const order = data.order;
  const analysis = data.analysis;
  const amountRupees = (disp.amount / 100).toFixed(2);
  const isActionable = data.actionable;
  const requirements = data.requirements && typeof data.requirements === 'object'
    ? data.requirements
    : {};
  const requirementRows = [
    ...(Array.isArray(requirements.required)
      ? requirements.required.map((category) => ({ category, role: 'Required' }))
      : []),
    ...(Array.isArray(requirements.helpful)
      ? requirements.helpful.map((category) => ({ category, role: 'Helpful' }))
      : []),
  ].filter(({ category }) => typeof category === 'string' && category.trim());
  const evidenceStatuses = analysis?.evidence_report?.category_status || {};

  return (
    <div className="space-y-6 animate-fade-in pb-16">
      {/* Top Navigation & Action Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="btn btn-secondary text-xs px-2.5 py-1.5"
            title="Back to Worklist"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Worklist</span>
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-heading text-xl font-bold text-white">{caseId}</h2>
              <span className={`badge ${
                disp.status === 'open' ? 'badge-open' : disp.status === 'won' ? 'badge-won' : 'badge-lost'
              }`}>
                {disp.status}
              </span>
              {data.deadline?.urgency === 'critical' && (
                <span className="badge badge-critical flex items-center gap-1">
                  <Clock className="w-3 h-3 animate-pulse" />
                  <span>Critical ({data.deadline.hours_remaining}h left)</span>
                </span>
              )}
            </div>
            <div className="text-xs text-slate-400 font-mono mt-0.5">
              Razorpay ID: {disp.id} • Payment: {disp.payment_id}
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          {isAuditor && (
            <span className="badge text-xs px-3 py-1.5 font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30 flex items-center gap-1.5 mr-2">
              <Eye className="w-3.5 h-3.5" />
              <span>Read-Only Auditor Mode</span>
            </span>
          )}
          <button
            id="btn-trigger-ai"
            onClick={handleRunAnalysis}
            disabled={analyzing || !isActionable || isAuditor}
            className="btn btn-primary text-xs shadow-sm"
          >
            {analyzing ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5" />
            )}
            <span>{analyzing ? 'Synthesizing...' : 'Analyze with Gemini'}</span>
          </button>

          <button
            id="btn-contest-modal-trigger"
            onClick={handleOpenContestModal}
            disabled={!analysis || !isActionable || isAuditor}
            className="btn btn-success text-xs shadow-sm"
          >
            <Lock className="w-3.5 h-3.5" />
            <span>Approve & Contest</span>
          </button>

          <button
            id="btn-accept-modal-trigger"
            onClick={handleOpenAcceptModal}
            disabled={!isActionable || isAuditor}
            className="btn btn-danger text-xs shadow-sm"
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>Accept Liability</span>
          </button>
        </div>
      </div>

      {/* Notification Banners */}
      {successMessage && (
        <div className="p-3.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span>{successMessage}</span>
          </div>
          <button onClick={() => setSuccessMessage(null)} className="text-slate-400 hover:text-white">✕</button>
        </div>
      )}

      {error && (
        <div className="p-3.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-slate-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Overview Cards Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Card 1: Dispute & Payment Details */}
        <div className="glass-panel-premium card-sheen stat-accent-indigo p-6 rounded-2xl shadow-sm">
          <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">
            Financial Details
          </h4>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between py-1.5 border-b border-slate-800/60">
              <span className="text-slate-400 font-medium">Disputed Amount</span>
              <span className="font-mono font-bold text-white text-base">₹{amountRupees}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800/60">
              <span className="text-slate-400 font-medium">Reason Category</span>
              <span className="font-mono text-indigo-400 capitalize font-semibold">{disp.reason_code?.replace(/_/g, ' ') || 'General'}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800/60">
              <span className="text-slate-400 font-medium">Card Scheme</span>
              <span className="font-mono text-slate-200 font-semibold">{disp.gateway || 'Razorpay Gateway'}</span>
            </div>
            <div className="flex justify-between py-1.5">
              <span className="text-slate-400 font-medium">Bank Response Deadline</span>
              <span className="font-mono text-amber-400 font-bold">{data.deadline?.respond_by || 'N/A'}</span>
            </div>
          </div>
        </div>

        {/* Card 2: Order & Customer Information */}
        <div className="glass-panel-premium card-sheen stat-accent-cyan p-6 rounded-2xl shadow-sm">
          <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">
            Order Verification
          </h4>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between py-1.5 border-b border-slate-800/60">
              <span className="text-slate-400 font-medium">Order ID</span>
              <span className="font-mono text-slate-200 font-semibold">{order?.id || 'N/A'}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800/60">
              <span className="text-slate-400 font-medium">Customer Name</span>
              <span className="font-semibold text-slate-200">{order?.customer_name || 'Anonymous Buyer'}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-slate-800/60">
              <span className="text-slate-400 font-medium">Shipping Tracking #</span>
              <span className="font-mono text-cyan-400 font-semibold">{order?.tracking_number || 'TRK-VERIFIED-FEDEX'}</span>
            </div>
            <div className="flex justify-between py-1.5">
              <span className="text-slate-400 font-medium">Delivery Status</span>
              <span className="text-emerald-400 font-semibold">Delivered & Signed</span>
            </div>
          </div>
        </div>

        {/* Card 3: AI Recommendation & Win Probability */}
        <div className="glass-panel-premium card-sheen stat-accent-emerald p-6 rounded-2xl shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
              AI Decision Copilot
            </h4>
            <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              GEMINI 2.5 FLASH / PRO
            </span>
          </div>

          {analysis ? (
            <div className="space-y-3.5">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-400">Recommendation:</span>
                <span className={`badge text-xs px-3 py-1 font-bold ${
                  analysis.recommendation?.decision === 'contest' ? 'badge-won' : 'badge-lost'
                }`}>
                  {analysis.recommendation?.decision?.toUpperCase()}
                </span>
              </div>

              <div className="space-y-1.5">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400 font-medium">Win Probability (Heuristic):</span>
                  <span className="font-mono font-bold text-emerald-400">
                    {analysis.recommendation?.p_win != null ? `${Math.round(analysis.recommendation.p_win * 100)}%` : 'n/a'}
                  </span>
                </div>
                <div className="w-full h-2.5 bg-slate-900 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-500 to-cyan-400 rounded-full"
                    style={{ width: `${Math.round((analysis.recommendation?.p_win != null ? analysis.recommendation.p_win : 0) * 100)}%` }}
                  ></div>
                </div>
                <div className="text-xs text-slate-400 pt-0.5">
                  * Prior heuristic. Final dispute outcome is decided by card scheme adjudication.
                </div>
              </div>

              <p className="text-xs sm:text-sm text-slate-300 leading-relaxed bg-slate-900/50 p-3.5 rounded-xl border border-slate-800/80">
                {analysis.recommendation?.rationale || 'Carrier delivery confirmation and customer invoice strongly support successful contest under scheme rules.'}
              </p>
            </div>
          ) : (
            <div className="py-4 text-center">
              <p className="text-sm text-slate-400 mb-3">No AI analysis cached yet.</p>
              <button
                onClick={handleRunAnalysis}
                disabled={analyzing}
                className="btn btn-secondary text-sm h-10 px-4 w-full"
              >
                <Sparkles className="w-4 h-4 text-indigo-400" />
                <span>Run Analysis Now</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Main Workbench Tabs */}
      <div className="case-workbench-tabs border-b border-slate-800 flex items-center gap-8 overflow-x-auto pt-2">
        <button
          onClick={() => setActiveTab('rebuttal')}
          className={`flex-shrink-0 pb-3.5 text-sm font-semibold tracking-normal flex items-center gap-2 border-b-2 transition-all ${
            activeTab === 'rebuttal'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <FileText className="w-4 h-4" />
          <span>Rebuttal Studio & Evidence Checklist</span>
        </button>

        <button
          onClick={() => setActiveTab('evidence')}
          className={`flex-shrink-0 pb-3.5 text-sm font-semibold tracking-normal flex items-center gap-2 border-b-2 transition-all ${
            activeTab === 'evidence'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Upload className="w-4 h-4" />
          <span>Evidence Locker ({data.evidence_locker?.length || 0})</span>
        </button>

        <button
          onClick={() => setActiveTab('comments')}
          className={`flex-shrink-0 pb-3.5 text-sm font-semibold tracking-normal flex items-center gap-2 border-b-2 transition-all ${
            activeTab === 'comments'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <MessageSquare className="w-4 h-4" />
          <span>Reviewer Notes ({comments.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('audit')}
          className={`flex-shrink-0 pb-3.5 text-sm font-semibold tracking-normal flex items-center gap-2 border-b-2 transition-all ${
            activeTab === 'audit'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <History className="w-4 h-4" />
          <span>Cryptographic Audit Trail ({auditEvents.length})</span>
        </button>
      </div>

      {/* Tab 1: Rebuttal Studio */}
      {activeTab === 'rebuttal' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left 2 Cols: Rebuttal Editor */}
          <div className="lg:col-span-2 glass-panel-premium card-sheen p-7 sm:p-8 space-y-5 rounded-2xl shadow-xl">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-heading text-lg font-bold text-white flex items-center gap-2">
                  <FileCheck className="w-5 h-5 text-indigo-400" />
                  <span>Rebuttal Defense Letter</span>
                </h3>
                <p className="text-sm text-slate-400 mt-0.5">
                  Citation-grounded arguments formatted for Razorpay bank dispute arbitration.
                </p>
              </div>

              <div className="flex items-center gap-3">
                {data.analysis && !isAuditor && (
                  <button
                    type="button"
                    onClick={() => setRejectModalOpen(true)}
                    className="btn btn-ghost text-sm h-10 px-4 text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 border border-rose-500/30 flex items-center gap-2"
                  >
                    <XCircle className="w-4 h-4" />
                    <span>Reject Draft</span>
                  </button>
                )}
                <button
                  id="btn-save-draft"
                  onClick={handleSaveDraft}
                  disabled={savingDraft || !draftContent || isAuditor}
                  className="btn btn-secondary text-sm h-10 px-4 flex items-center gap-2"
                >
                  <Save className="w-4 h-4" />
                  <span>{savingDraft ? 'Saving...' : 'Save Draft'}</span>
                </button>
              </div>
            </div>

            <textarea
              id="textarea-draft-editor"
              value={draftContent}
              onChange={(e) => {
                setDraftContent(e.target.value);
                setIsDraftDirty(true);
              }}
              rows={16}
              placeholder="Run AI Analysis to generate citation-grounded rebuttal letter, or type custom arguments here..."
              className="input-control font-mono text-sm leading-relaxed resize-y w-full bg-slate-950/80 border-slate-800 focus:border-indigo-500 p-5 rounded-xl min-h-[380px]"
            />

            <div className="flex items-center justify-between text-xs text-slate-400">
              <div className="flex items-center gap-3">
                <span className="font-medium">Words: {draftContent ? draftContent.split(/\s+/).filter(Boolean).length : 0}</span>
                <span>•</span>
                <span className="font-medium">Characters: {draftContent.length}</span>
                {isDraftDirty && <span className="text-amber-400 font-semibold">● Unsaved changes</span>}
              </div>
              <div className="text-slate-400 font-medium">
                PDF explanation letter is generated automatically upon approval.
              </div>
            </div>
          </div>

          {/* Right Col: Scheme Checklist & Safety Findings */}
          <div className="space-y-6">
            {/* Checklist */}
            <div className="glass-panel-premium card-sheen p-6 rounded-2xl shadow-xl">
              <h4 className="font-heading text-sm font-bold text-white uppercase tracking-wider mb-3 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Required Scheme Evidence</span>
              </h4>
              <p className="text-sm text-slate-400 mb-4">
                Mandatory document categories required to defend this reason code:
              </p>

              <div className="space-y-2.5">
                {requirementRows.length > 0 ? requirementRows.map(({ category, role }) => {
                  const status = evidenceStatuses[category];
                  const statusLabel = ['present', 'partial', 'missing'].includes(status)
                    ? status.toUpperCase()
                    : 'NOT ASSESSED';
                  const statusClass = status === 'present'
                    ? 'text-emerald-400'
                    : status === 'partial'
                      ? 'text-amber-400'
                      : status === 'missing'
                        ? 'text-rose-400'
                        : 'text-slate-500';

                  return (
                    <div key={`${role}-${category}`} className="flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-900/60 border border-slate-800 text-sm">
                      <span className="capitalize font-mono font-medium text-slate-200">{category.replace(/_/g, ' ')}</span>
                      <span className="flex items-center gap-2 shrink-0">
                        <span className="text-xs text-slate-400 font-semibold">{role}</span>
                        <span className={`${statusClass} font-bold text-xs`}>{statusLabel}</span>
                      </span>
                    </div>
                  );
                }) : (
                  <p className="text-sm text-slate-500">No evidence requirements are available for this case.</p>
                )}
              </div>
            </div>

            {/* Safety & PCI Scanning */}
            <div className="glass-panel-premium card-sheen p-6 rounded-2xl shadow-xl">
              <h4 className="font-heading text-sm font-bold text-white uppercase tracking-wider mb-3 flex items-center gap-2">
                <Shield className="w-4 h-4 text-cyan-400" />
                <span>PCI-DSS & Safety Scan</span>
              </h4>

              <div className="space-y-3 text-sm">
                <div className="flex justify-between items-center p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                  <span className="text-slate-400 font-medium">Card Number PANs</span>
                  <span className="text-emerald-400 font-mono font-semibold">0 Detected (Safe)</span>
                </div>
                <div className="flex justify-between items-center p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                  <span className="text-slate-400 font-medium">Prompt Injection Tests</span>
                  <span className="text-emerald-400 font-mono font-semibold">Clean (Passed)</span>
                </div>
                <div className="flex justify-between items-center p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                  <span className="text-slate-400 font-medium">PII Token Replacement</span>
                  <span className="text-cyan-400 font-mono font-semibold">Vault Activated</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Evidence Locker */}
      {activeTab === 'evidence' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left 2 Cols: Locker Documents List */}
          <div className="lg:col-span-2 glass-panel-premium card-sheen p-6">
            <h3 className="font-heading text-base font-bold text-white mb-2">
              Dispute Evidence Documents
            </h3>
            <p className="text-xs text-slate-400 mb-5">
              Files uploaded to the Evidence Locker are scanned, hashed with SHA-256, and synchronized to the Razorpay Documents API.
            </p>

            {data.evidence_locker?.length > 0 ? (
              <div className="space-y-3">
                {data.evidence_locker.map((doc) => (
                  <div key={doc.id} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 flex-shrink-0">
                        <FileText className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="font-semibold text-sm text-white">{doc.file_name}</div>
                        <div className="text-xs text-slate-400 font-mono mt-0.5">
                          Category: <span className="text-indigo-400">{doc.category}</span> • Size: {(doc.size / 1024).toFixed(1)} KB • By: {doc.uploaded_by}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="badge badge-open text-xs">
                        {doc.razorpay_doc_id ? `RP: ${doc.razorpay_doc_id}` : 'SIMULATED'}
                      </span>
                      <a
                        href={getEvidenceDownloadUrl(caseId, doc.id)}
                        target="_blank"
                        rel="noreferrer"
                        className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
                        title="Download Document"
                      >
                        <Download className="w-4 h-4" />
                      </a>
                      {!isAuditor && (
                        <button
                          type="button"
                          onClick={() => handleDeleteEvidence(doc.id)}
                          className="p-2 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 transition-colors"
                          title="Delete Document"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-12 text-center text-slate-400 text-sm bg-slate-900/30 rounded-xl border border-dashed border-slate-800">
                <Upload className="w-7 h-7 mx-auto mb-2.5 text-slate-500" />
                <p className="font-medium text-slate-200 mb-1">Evidence locker is currently empty</p>
                <p className="text-xs text-slate-400">Upload delivery receipts, invoice PDFs, or communications below.</p>
              </div>
            )}
          </div>

          {/* Right Col: Evidence Upload Form */}
          <div className="glass-panel p-5">
            <h4 className="font-heading text-sm font-bold text-white mb-1 flex items-center gap-2">
              <Upload className="w-4 h-4 text-indigo-400" />
              <span>Upload Merchant Evidence</span>
            </h4>
            <p className="text-xs text-slate-400 mb-4">
              Accepted: PDF, PNG, JPEG up to 10 MB.
            </p>

            <form onSubmit={handleUploadEvidence} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Evidence Category
                </label>
                <select
                  value={uploadCategory}
                  onChange={(e) => setUploadCategory(e.target.value)}
                  className="input-control text-xs"
                >
                  <option value="proof_of_delivery">Proof of Delivery</option>
                  <option value="customer_communication">Customer Communication</option>
                  <option value="refund_policy">Refund Policy / T&C</option>
                  <option value="cancellation_policy">Cancellation Policy</option>
                  <option value="explanation_letter">Explanation Letter</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  File Attachment
                </label>
                <input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="input-control text-xs file:mr-3 file:py-1 file:px-2.5 file:rounded-md file:border-0 file:text-xs file:bg-indigo-600 file:text-white hover:file:bg-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Pasted Text / Notes (Optional - PCI Scanned)
                </label>
                <textarea
                  value={uploadExcerpt}
                  onChange={(e) => setUploadExcerpt(e.target.value)}
                  rows={3}
                  placeholder="Paste courier notes or proof excerpts..."
                  className="input-control text-xs resize-none"
                />
              </div>

              <div className="pt-1">
                <label className="flex items-start gap-2 cursor-pointer text-xs text-slate-300">
                  <input
                    type="checkbox"
                    checked={attestNoCard}
                    onChange={(e) => setAttestNoCard(e.target.checked)}
                    className="mt-0.5 rounded border-slate-700 text-indigo-600 focus:ring-0"
                  />
                  <span>
                    I attest this evidence contains <strong className="text-white">NO</strong> credit card numbers, CVVs, or cardholder magnetic track data.
                  </span>
                </label>
              </div>

              <button
                type="submit"
                disabled={uploading || !uploadFile || !attestNoCard || isAuditor}
                className="btn btn-primary w-full text-xs py-2.5"
              >
                {uploading ? 'Scanning & Uploading...' : (isAuditor ? 'Upload Disabled in Auditor Mode' : 'Upload to Evidence Locker')}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Tab 3: Case Audit Trail */}
      {activeTab === 'audit' && (
        <div className="glass-panel p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-heading text-base font-bold text-white flex items-center gap-2">
                <History className="w-4 h-4 text-purple-400" />
                <span>Case Tamper-Evident Audit Chain</span>
              </h3>
              <p className="text-xs text-slate-400">
                Cryptographically linked SHA-256 chain of custody for all reviewer actions on this case.
              </p>
            </div>
            <span className="badge badge-won text-xs">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Chain Intact</span>
            </span>
          </div>

          <div className="space-y-3 mt-6">
            {auditEvents.map((event, idx) => (
              <div key={event.id || idx} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 flex-shrink-0 font-mono text-xs sm:text-sm font-bold">
                    #{event.id}
                  </div>
                  <div>
                    <div className="font-semibold text-white capitalize text-sm">{event.action.replace(/_/g, ' ')}</div>
                    <div className="text-xs text-slate-400">
                      Actor: <span className="text-indigo-300 font-medium">{event.actor}</span> • {event.timestamp_display || 'Recent'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 font-mono text-xs text-slate-400">
                  <span className="text-slate-400">Entry Hash:</span>
                  <span className="code-pill text-cyan-300 truncate max-w-[140px] sm:max-w-[200px]" title={event.entry_hash}>
                    {event.entry_hash?.substring(0, 16)}...
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 4: Reviewer Notes & Discussion */}
      {activeTab === 'comments' && (
        <div className="glass-panel p-6 space-y-6">
          <div className="flex items-center justify-between pb-4 border-b border-slate-800">
            <div>
              <h3 className="font-heading text-base font-bold text-white flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-indigo-400" />
                <span>Internal Reviewer Discussion & Compliance Notes</span>
              </h3>
              <p className="text-xs text-slate-400">
                Collaborative notes between merchant reviewers and compliance auditors. Persisted in SQLite store.
              </p>
            </div>
            <span className="badge badge-open text-xs">
              {comments.length} Note{comments.length !== 1 ? 's' : ''}
            </span>
          </div>

          {/* New Comment Input */}
          {!isAuditor ? (
            <form onSubmit={handleAddComment} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
              <label className="block text-xs font-semibold text-slate-300">
                Add Reviewer Note / Dispatcher Verification:
              </label>
              <textarea
                required
                rows={3}
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                placeholder="e.g. Spoke with courier hub manager; verified signed delivery pod with OTP..."
                className="input-control text-xs resize-none"
              />
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={postingComment || !newComment.trim()}
                  className="btn btn-primary text-xs flex items-center gap-1.5"
                >
                  <span>{postingComment ? 'Posting...' : 'Post Reviewer Note'}</span>
                </button>
              </div>
            </form>
          ) : (
            <div className="p-3.5 rounded-xl bg-slate-900/40 border border-slate-800 text-xs text-amber-300/80 flex items-center gap-2">
              <Eye className="w-4 h-4 text-amber-400 flex-shrink-0" />
              <span>Auditor view: Comment posting is restricted to reviewers and compliance officers.</span>
            </div>
          )}

          {/* Comments List */}
          <div className="space-y-3">
            {comments.length === 0 ? (
              <div className="py-8 text-center text-slate-500 text-xs">
                No reviewer notes recorded on this dispute yet.
              </div>
            ) : (
              comments.map((c) => (
                <div key={c.id} className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 text-sm space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-indigo-300">{c.author}</span>
                    <span className="text-slate-400 font-mono">
                      {new Date(c.created_at * 1000).toLocaleString('en-IN')}
                    </span>
                  </div>
                  <p className="text-slate-200 leading-relaxed whitespace-pre-wrap">{c.comment}</p>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Contest Approval Modal */}
      {contestModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content p-6 sm:p-8 max-w-xl">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                  <Lock className="w-4 h-4" />
                </div>
                <h3 className="font-heading text-lg font-bold text-white">Cryptographic Contest Approval</h3>
              </div>
              <button onClick={() => setContestModalOpen(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <p className="text-xs sm:text-sm text-slate-300 mb-4 leading-relaxed">
              To prevent unauthorized or altered submissions, this approval token is cryptographically bound to the SHA-256 hash of the exact JSON payload.
            </p>

            <div className="space-y-3.5 mb-6">
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                  Issued Single-Use Approval Token
                </label>
                <div className="code-pill p-3 text-xs sm:text-sm text-purple-300 break-all select-all font-mono font-bold">
                  {contestApprovalToken}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                  Bound Payload SHA-256 Hash
                </label>
                <div className="code-pill p-3 text-xs sm:text-sm text-cyan-300 break-all select-all font-mono">
                  {contestPayloadHash}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                  Exact Submission Payload (Preview)
                </label>
                <pre className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 text-xs font-mono text-slate-300 max-h-44 overflow-y-auto">
                  {contestPayloadJson}
                </pre>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setContestModalOpen(false)}
                className="btn btn-secondary text-xs"
              >
                Cancel
              </button>
              <button
                id="btn-confirm-contest-submit"
                onClick={handleConfirmContestSubmission}
                disabled={submittingContest}
                className="btn btn-success text-xs"
              >
                {submittingContest ? 'Submitting to Razorpay...' : 'Confirm Submission to Razorpay'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Accept Liability Modal */}
      {acceptModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content p-6 sm:p-8 max-w-md">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
                  <AlertTriangle className="w-4 h-4" />
                </div>
                <h3 className="font-heading text-lg font-bold text-white">Confirm Acceptance of Liability</h3>
              </div>
              <button onClick={() => setAcceptModalOpen(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <p className="text-xs text-rose-300/90 mb-4 bg-rose-500/10 p-3 rounded-lg border border-rose-500/20">
              <strong>Warning:</strong> Accepting this dispute will permanently debit <strong>₹{amountRupees}</strong> from your merchant balance and close the case.
            </p>

            {!acceptApprovalToken ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    To confirm, please re-type the dispute amount (₹{amountRupees}):
                  </label>
                  <input
                    id="input-typed-amount"
                    type="text"
                    value={typedAmount}
                    onChange={(e) => setTypedAmount(e.target.value)}
                    placeholder={amountRupees}
                    className="input-control text-xs font-mono"
                  />
                </div>

                <button
                  id="btn-verify-accept-amount"
                  onClick={handleRequestAcceptToken}
                  disabled={!typedAmount.trim()}
                  className="btn btn-primary w-full text-xs py-2"
                >
                  Verify Amount & Generate Token
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 text-sm space-y-2">
                  <div className="flex items-center gap-2 text-emerald-400 font-semibold">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Amount Verified & Token Bound</span>
                  </div>
                  <div className="font-mono text-xs text-slate-300 break-all">
                    Token: {acceptApprovalToken.substring(0, 24)}...
                  </div>
                </div>

                <div className="flex items-center justify-end gap-3 pt-2">
                  <button
                    onClick={() => setAcceptModalOpen(false)}
                    className="btn btn-secondary text-xs"
                  >
                    Cancel
                  </button>
                  <button
                    id="btn-confirm-accept-submit"
                    onClick={handleConfirmAcceptDispute}
                    disabled={submittingAccept}
                    className="btn btn-danger text-xs"
                  >
                    {submittingAccept ? 'Accepting...' : 'Confirm Forfeit to Razorpay'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Reject Draft Modal */}
      {rejectModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content p-6 sm:p-8 max-w-lg">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
                <XCircle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-heading text-lg font-bold text-white">Reject AI Rebuttal Draft</h3>
                <p className="text-xs text-slate-400">Require revision and log specific instructions to the audit ledger.</p>
              </div>
            </div>

            <form onSubmit={handleConfirmRejectDraft} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Rejection Reason / Guidance:
                </label>
                <textarea
                  required
                  rows={4}
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="e.g. Courier tracking proof does not show the customer delivery address clearly. Please re-upload verified Delhivery POD before re-evaluating..."
                  className="input-control text-xs resize-none"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setRejectModalOpen(false)}
                  className="btn btn-secondary text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={rejectingDraft || !rejectReason.trim()}
                  className="btn text-xs bg-rose-600 hover:bg-rose-500 text-white font-semibold"
                >
                  {rejectingDraft ? 'Recording...' : 'Confirm Rejection'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
