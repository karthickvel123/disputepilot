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
  Sparkles
} from 'lucide-react';
import { listDisputes } from '../api';

export default function DisputesView({ onSelectCase, initialFilter = 'all' }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState(initialFilter);
  const [reasonFilter, setReasonFilter] = useState('all');
  const [search, setSearch] = useState('');

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
    <div className="space-y-6 animate-fade-in">
      {/* Header and Filter Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
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

        {/* Search Input */}
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            id="input-search-disputes"
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search by case ID, dispute, reason..."
            className="input-control pl-9 text-xs"
          />
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
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

        {/* Reason Class Filter */}
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
            <option value="all">All Reason Classes</option>
            <option value="fraudulent">Fraudulent</option>
            <option value="product_not_received">Product Not Received</option>
            <option value="subscription_cancelled">Subscription Cancelled</option>
            <option value="unrecognized">Unrecognized</option>
            <option value="credit_not_processed">Credit Not Processed</option>
            <option value="general">General</option>
          </select>
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
    </div>
  );
}
