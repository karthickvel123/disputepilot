import React, { useState, useEffect } from 'react';
import { 
  Search, 
  Filter, 
  Clock, 
  ChevronLeft, 
  ChevronRight, 
  ArrowUpRight, 
  CheckCircle2, 
  AlertTriangle,
  FileText,
  RotateCcw,
  Sparkles,
  Plus,
  Upload,
  Download,
  X,
  FileSpreadsheet
} from 'lucide-react';
import { 
  listDisputes, 
  createDispute, 
  importDisputesCsv, 
  getDisputesExportUrl 
} from '../api';

export default function DisputesView({ onSelectCase, initialFilter = 'all' }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [bannerMessage, setBannerMessage] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState(initialFilter);
  const [reasonFilter, setReasonFilter] = useState('all');
  const [search, setSearch] = useState('');

  // Create Dispute Modal
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createForm, setCreateForm] = useState({
    dispute_id: '',
    amount_rupees: '',
    currency: 'INR',
    reason_code: 'item_not_received',
    reason_description: '',
    customer_name: '',
    customer_email: '',
    customer_phone: '',
    shipping_carrier: 'Delhivery',
    tracking_number: '',
    days_to_respond: 7,
  });

  // Import CSV Modal
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [csvText, setCsvText] = useState('');
  const [dryRunResult, setDryRunResult] = useState(null);
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    fetchDisputes();
  }, [page, statusFilter, reasonFilter, search]);

  async function fetchDisputes() {
    setLoading(true);
    setError(null);
    try {
      const data = await listDisputes({
        page,
        per_page: 15,
        status_filter: statusFilter,
        reason_filter: reasonFilter,
        search,
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);
    } catch (err) {
      setError(err.message || 'Failed to fetch disputes.');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateSubmit(e) {
    if (e) e.preventDefault();
    setCreating(true);
    try {
      const payload = {
        ...createForm,
        dispute_id: createForm.dispute_id || `disp_${Date.now().toString().slice(-6)}`,
        amount_rupees: parseFloat(createForm.amount_rupees),
      };
      const res = await createDispute(payload);
      setBannerMessage(`Dispute '${res.dispute_id}' created successfully and queued for automated triage.`);
      setCreateModalOpen(false);
      setCreateForm({
        dispute_id: '',
        amount_rupees: '',
        currency: 'INR',
        reason_code: 'item_not_received',
        reason_description: '',
        customer_name: '',
        customer_email: '',
        customer_phone: '',
        shipping_carrier: 'Delhivery',
        tracking_number: '',
        days_to_respond: 7,
      });
      await fetchDisputes();
    } catch (err) {
      alert(`Failed to create dispute: ${err.message}`);
    } finally {
      setCreating(false);
    }
  }

  async function handlePreviewCsv() {
    if (!csvText.trim()) return;
    setImporting(true);
    try {
      const result = await importDisputesCsv({ csv_data: csvText, dry_run: true });
      setDryRunResult(result);
    } catch (err) {
      alert(`CSV validation error: ${err.message}`);
    } finally {
      setImporting(false);
    }
  }

  async function handleExecuteCsvImport() {
    if (!csvText.trim()) return;
    setImporting(true);
    try {
      const result = await importDisputesCsv({ csv_data: csvText, dry_run: false });
      setBannerMessage(`Imported ${result.imported_count} dispute cases successfully!`);
      setImportModalOpen(false);
      setCsvText('');
      setDryRunResult(null);
      await fetchDisputes();
    } catch (err) {
      alert(`Import failed: ${err.message}`);
    } finally {
      setImporting(false);
    }
  }

  function handleFillCsvTemplate() {
    const template = `dispute_id,amount,reason_code,reason_description,customer_name,customer_email,tracking_number
disp_demo_${Math.floor(Math.random() * 9000 + 1000)},2499.00,item_not_received,Customer claims shoes never arrived,Rohan Mehra,rohan@example.com,DEL123456789
disp_demo_${Math.floor(Math.random() * 9000 + 1000)},1850.50,not_as_described,Product size differs from invoice,Pooja Verma,pooja@example.com,BD987654321
`;
    setCsvText(template);
    setDryRunResult(null);
  }

  function getUrgencyBadge(urgency, hours) {
    if (urgency === 'critical' || hours <= 24) {
      return (
        <span className="badge badge-critical flex items-center gap-1">
          <Clock className="w-3 h-3 animate-pulse" />
          <span>{hours > 0 ? `${hours}h left` : 'Expired'}</span>
        </span>
      );
    }
    if (urgency === 'high' || hours <= 48) {
      return (
        <span className="badge badge-urgent flex items-center gap-1">
          <Clock className="w-3 h-3" />
          <span>{hours}h left</span>
        </span>
      );
    }
    return (
      <span className="badge badge-open flex items-center gap-1">
        <Clock className="w-3 h-3" />
        <span>{hours}h left</span>
      </span>
    );
  }

  function getRecommendationBadge(rec) {
    if (!rec) return null;
    if (rec.decision === 'contest') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <CheckCircle2 className="w-3 h-3" />
          <span>Contest</span>
          {rec.is_uncertain && <span className="text-[10px] text-amber-400">(Uncertain)</span>}
        </span>
      );
    }
    if (rec.decision === 'accept') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
          <AlertTriangle className="w-3 h-3" />
          <span>Accept Liability</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-800 text-slate-300">
        Review
      </span>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in pb-16">
      {/* Header and Action Controls */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h2 className="font-heading text-2xl font-bold text-white flex items-center gap-2">
            <span>Dispute Triage Worklist</span>
            <span className="text-xs font-mono font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">
              {total} disputes
            </span>
          </h2>
          <p className="text-xs text-slate-400">
            Prioritized by bank response deadline and automated win probability scoring.
          </p>
        </div>

        {/* Action Buttons: Create Dispute, Import CSV, Export CSV */}
        <div className="flex flex-wrap items-center gap-2.5">
          <a
            href={getDisputesExportUrl()}
            download="disputepilot_cases.csv"
            className="btn btn-secondary text-xs flex items-center gap-1.5"
            title="Export CSV"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export CSV</span>
          </a>

          <button
            onClick={() => setImportModalOpen(true)}
            className="btn btn-secondary text-xs flex items-center gap-1.5"
          >
            <Upload className="w-3.5 h-3.5" />
            <span>Import CSV</span>
          </button>

          <button
            onClick={() => setCreateModalOpen(true)}
            className="btn btn-primary text-xs flex items-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Dispute</span>
          </button>
        </div>
      </div>

      {bannerMessage && (
        <div className="p-3.5 rounded-xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span>{bannerMessage}</span>
          </div>
          <button onClick={() => setBannerMessage(null)} className="text-indigo-400 hover:text-white">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        {/* Filter Tabs */}
        <div className="flex flex-wrap items-center gap-1.5">
          {[
            { id: 'all', label: 'All Cases' },
            { id: 'urgent', label: 'Urgent (<48h)' },
            { id: 'pending', label: 'Needs AI Analysis' },
            { id: 'analyzed', label: 'Analyzed & Drafted' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setStatusFilter(tab.id);
                setPage(1);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                statusFilter === tab.id
                  ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          {/* Reason Filter */}
          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              id="select-reason-filter"
              value={reasonFilter}
              onChange={(e) => {
                setReasonFilter(e.target.value);
                setPage(1);
              }}
              className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 outline-none focus:border-indigo-500"
            >
              <option value="all">All Reason Codes</option>
              <option value="item_not_received">Item Not Received</option>
              <option value="not_as_described">Not As Described</option>
              <option value="unauthorised">Unauthorised Charge</option>
              <option value="duplicate_charge">Duplicate Charge</option>
              <option value="subscription_cancelled">Subscription Cancelled</option>
              <option value="refund_not_received">Refund Not Received</option>
              <option value="other">Other Inquiry</option>
            </select>
          </div>

          {/* Search Input */}
          <div className="relative w-full sm:w-64">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              id="input-search-disputes"
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search case, ID, reason..."
              className="input-control pl-9 text-xs"
            />
          </div>
        </div>
      </div>

      {/* Table Content */}
      <div className="glass-panel overflow-hidden border border-slate-800">
        {loading ? (
          <div className="py-16 text-center">
            <div className="w-7 h-7 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
            <p className="text-slate-400 text-xs">Loading triage worklist...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-rose-400 text-xs">
            <AlertTriangle className="w-6 h-6 mx-auto mb-2 text-rose-400" />
            <p>{error}</p>
          </div>
        ) : items.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-xs">
            <FileText className="w-8 h-8 mx-auto mb-2 text-slate-600" />
            <p className="font-medium text-slate-300 mb-1">No matching disputes found</p>
            <p className="text-[11px] text-slate-500">Try adjusting your search query or status filter.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-800/80 bg-slate-900/40 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                  <th className="py-3 px-4">Case & Dispute ID</th>
                  <th className="py-3 px-4">Amount</th>
                  <th className="py-3 px-4">Reason Class</th>
                  <th className="py-3 px-4">Deadline Urgency</th>
                  <th className="py-3 px-4">Win Probability</th>
                  <th className="py-3 px-4">AI Recommendation</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40">
                {items.map((item) => (
                  <tr
                    key={item.case_id}
                    onClick={() => onSelectCase(item.case_id)}
                    className="hover:bg-slate-800/30 cursor-pointer transition-colors group"
                  >
                    {/* Case & Dispute ID */}
                    <td className="py-3.5 px-4">
                      <div className="font-mono font-medium text-slate-200 group-hover:text-indigo-300 transition-colors">
                        {item.case_id}
                      </div>
                      <div className="font-mono text-[10px] text-slate-500">
                        {item.dispute_id}
                      </div>
                    </td>

                    {/* Amount */}
                    <td className="py-3.5 px-4 font-mono font-semibold text-white">
                      {item.amount_display}
                    </td>

                    {/* Reason Class */}
                    <td className="py-3.5 px-4">
                      <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-slate-800/60 text-slate-300 border border-slate-700/50 capitalize">
                        {item.reason_class.replace(/_/g, ' ')}
                      </span>
                    </td>

                    {/* Deadline Urgency */}
                    <td className="py-3.5 px-4">
                      {getUrgencyBadge(item.urgency, item.hours_remaining)}
                    </td>

                    {/* Win Probability */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              item.p_win >= 0.6
                                ? 'bg-emerald-400'
                                : item.p_win >= 0.4
                                ? 'bg-amber-400'
                                : 'bg-rose-400'
                            }`}
                            style={{ width: `${Math.round(item.p_win * 100)}%` }}
                          ></div>
                        </div>
                        <span className="font-mono text-[11px] text-slate-300">
                          {Math.round(item.p_win * 100)}%
                        </span>
                      </div>
                    </td>

                    {/* AI Recommendation */}
                    <td className="py-3.5 px-4">
                      {getRecommendationBadge(item.recommendation)}
                    </td>

                    {/* Action Link */}
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectCase(item.case_id);
                        }}
                        className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 group-hover:translate-x-0.5 transition-all font-medium"
                      >
                        <span>Review</span>
                        <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-slate-800/80 bg-slate-900/30 flex items-center justify-between text-xs text-slate-400">
            <div>
              Showing page <span className="font-medium text-white">{page}</span> of{' '}
              <span className="font-medium text-white">{totalPages}</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="btn btn-secondary text-xs px-2.5 py-1"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>Prev</span>
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="btn btn-secondary text-xs px-2.5 py-1"
              >
                <span>Next</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal: Create Dispute */}
      {createModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content p-6 sm:p-8 max-w-xl">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                  <Plus className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-heading text-lg font-bold text-white">Create Dispute Case</h3>
                  <p className="text-xs text-slate-400">Queue a new chargeback for automated AI triage and fact extraction.</p>
                </div>
              </div>
              <button onClick={() => setCreateModalOpen(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="space-y-4 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">Dispute ID (optional)</label>
                  <input
                    type="text"
                    value={createForm.dispute_id}
                    onChange={(e) => setCreateForm({ ...createForm, dispute_id: e.target.value })}
                    placeholder="e.g. disp_992144"
                    className="input-control text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">Disputed Amount (INR) *</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={createForm.amount_rupees}
                    onChange={(e) => setCreateForm({ ...createForm, amount_rupees: e.target.value })}
                    placeholder="e.g. 2499.00"
                    className="input-control text-xs"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">Reason Code *</label>
                  <select
                    value={createForm.reason_code}
                    onChange={(e) => setCreateForm({ ...createForm, reason_code: e.target.value })}
                    className="input-control text-xs"
                  >
                    <option value="item_not_received">Item Not Received</option>
                    <option value="not_as_described">Not As Described</option>
                    <option value="unauthorised">Unauthorised Transaction</option>
                    <option value="duplicate_charge">Duplicate Charge</option>
                    <option value="subscription_cancelled">Subscription Cancelled</option>
                    <option value="refund_not_received">Refund Not Received</option>
                    <option value="other">Other Reason</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">Days to Respond</label>
                  <input
                    type="number"
                    min="1"
                    max="30"
                    value={createForm.days_to_respond}
                    onChange={(e) => setCreateForm({ ...createForm, days_to_respond: parseInt(e.target.value) || 7 })}
                    className="input-control text-xs"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-300 mb-1">Reason Description</label>
                <input
                  type="text"
                  value={createForm.reason_description}
                  onChange={(e) => setCreateForm({ ...createForm, reason_description: e.target.value })}
                  placeholder="e.g. Buyer claims delivery package was never received at doorstep."
                  className="input-control text-xs"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">Customer Full Name *</label>
                  <input
                    type="text"
                    required
                    value={createForm.customer_name}
                    onChange={(e) => setCreateForm({ ...createForm, customer_name: e.target.value })}
                    placeholder="e.g. Rohan Mehra"
                    className="input-control text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">Customer Email</label>
                  <input
                    type="email"
                    value={createForm.customer_email}
                    onChange={(e) => setCreateForm({ ...createForm, customer_email: e.target.value })}
                    placeholder="rohan@example.com"
                    className="input-control text-xs"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">Shipping Carrier</label>
                  <input
                    type="text"
                    value={createForm.shipping_carrier}
                    onChange={(e) => setCreateForm({ ...createForm, shipping_carrier: e.target.value })}
                    placeholder="Delhivery / Blue Dart"
                    className="input-control text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">Courier Tracking Number</label>
                  <input
                    type="text"
                    value={createForm.tracking_number}
                    onChange={(e) => setCreateForm({ ...createForm, tracking_number: e.target.value })}
                    placeholder="e.g. DEL99881122"
                    className="input-control text-xs"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setCreateModalOpen(false)}
                  className="btn btn-secondary text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="btn btn-primary text-xs flex items-center gap-2"
                >
                  {creating ? 'Creating Case...' : 'Create & Triage Dispute'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Import CSV */}
      {importModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content p-6 sm:p-8 max-w-2xl">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                  <FileSpreadsheet className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-heading text-lg font-bold text-white">Import Disputes from CSV</h3>
                  <p className="text-xs text-slate-400">Batch ingest chargebacks with row-level preview and schema validation.</p>
                </div>
              </div>
              <button onClick={() => setImportModalOpen(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div className="flex items-center justify-between">
                <label className="text-[11px] font-semibold text-slate-300">
                  CSV Data (comma-separated):
                </label>
                <button
                  type="button"
                  onClick={handleFillCsvTemplate}
                  className="text-xs text-cyan-400 hover:text-cyan-300 underline font-medium"
                >
                  Fill Sample Template
                </button>
              </div>

              <textarea
                rows={6}
                value={csvText}
                onChange={(e) => {
                  setCsvText(e.target.value);
                  setDryRunResult(null);
                }}
                placeholder="dispute_id,amount,reason_code,reason_description,customer_name,customer_email,tracking_number..."
                className="input-control font-mono text-xs resize-none"
              />

              {/* Dry run preview box */}
              {dryRunResult && (
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-200">Pre-Import Validation Summary</span>
                    <div className="flex items-center gap-3">
                      <span className="text-emerald-400 font-bold">{dryRunResult.valid_count} Valid</span>
                      <span className="text-rose-400 font-bold">{dryRunResult.error_count} Errors</span>
                    </div>
                  </div>

                  {dryRunResult.errors?.length > 0 && (
                    <div className="space-y-1 text-[11px] text-rose-300">
                      {dryRunResult.errors.map((err, i) => (
                        <div key={i} className="flex items-center gap-1.5">
                          <AlertTriangle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
                          <span>Row {err.row}: {err.error}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {dryRunResult.preview?.length > 0 && (
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-slate-500 block mb-1">
                        Row Preview (first {dryRunResult.preview.length} rows):
                      </span>
                      <div className="space-y-1">
                        {dryRunResult.preview.map((p, idx) => (
                          <div key={idx} className="p-2 rounded bg-slate-900 border border-slate-800/80 font-mono text-[11px] text-slate-300 flex justify-between">
                            <span>{p.dispute_id} ({p.customer_name})</span>
                            <span className="text-indigo-400 font-semibold">{p.amount_display}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center justify-between pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={handlePreviewCsv}
                  disabled={importing || !csvText.trim()}
                  className="btn btn-secondary text-xs"
                >
                  {importing ? 'Validating...' : 'Validate CSV (Dry Run)'}
                </button>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setImportModalOpen(false)}
                    className="btn btn-secondary text-xs"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleExecuteCsvImport}
                    disabled={importing || !csvText.trim() || (dryRunResult && dryRunResult.valid_count === 0)}
                    className="btn btn-primary text-xs"
                  >
                    {importing ? 'Importing...' : 'Commit Batch Import'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
