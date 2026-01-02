"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import {
  CrawlConfig,
  CrawlJob,
  CrawlLogEntry,
  ExclusionRule,
  startCrawl,
  getCrawlJob,
  getCrawlJobs,
  getCrawlLogs,
  cancelCrawl,
  getExclusionRules,
  addExclusionRule,
  deleteExclusionRule,
  StartCrawlResponse,
} from "@/lib/api";

// ============================================================================
// Helper Components
// ============================================================================

function StatusBadge({ status }: { status: CrawlJob['status'] }) {
  const colors: Record<CrawlJob['status'], string> = {
    pending: "bg-gray-100 text-gray-800 border-gray-300",
    running: "bg-blue-100 text-blue-800 border-blue-300",
    completed: "bg-green-100 text-green-800 border-green-300",
    failed: "bg-red-100 text-red-800 border-red-300",
    cancelled: "bg-yellow-100 text-yellow-800 border-yellow-300",
  };

  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-xs font-semibold ${colors[status]}`}
    >
      {status.toUpperCase()}
    </span>
  );
}

function RuleTypeBadge({ ruleType }: { ruleType: ExclusionRule['rule_type'] }) {
  const colors: Record<ExclusionRule['rule_type'], string> = {
    country: "bg-blue-100 text-blue-800",
    category: "bg-purple-100 text-purple-800",
    supplier: "bg-amber-100 text-amber-800",
    keyword: "bg-green-100 text-green-800",
  };

  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${colors[ruleType]}`}>
      {ruleType}
    </span>
  );
}

// ============================================================================
// Start New Crawl Section
// ============================================================================

interface NewCrawlFormProps {
  excludedCountries: string[];
  onStartCrawl: (config: CrawlConfig) => Promise<void>;
  isStarting: boolean;
}

function NewCrawlForm({ excludedCountries, onStartCrawl, isStarting }: NewCrawlFormProps) {
  const [keywords, setKeywords] = useState<string>("");
  const [priceMin, setPriceMin] = useState<number>(5);
  const [priceMax, setPriceMax] = useState<number>(100);
  const [warehouses, setWarehouses] = useState<Record<string, boolean>>({
    US: true,
    CN: true,
  });
  const [categories, setCategories] = useState<string>("");

  // Uncheck warehouses that are in the exclusion list
  useEffect(() => {
    const newWarehouses = { ...warehouses };
    excludedCountries.forEach((country) => {
      if (country in newWarehouses) {
        newWarehouses[country] = false;
      }
    });
    setWarehouses(newWarehouses);
  }, [excludedCountries]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const keywordList = keywords
      .split(/[,\n]/)
      .map((k) => k.trim())
      .filter((k) => k.length > 0);

    if (keywordList.length === 0) {
      alert("Please enter at least one keyword");
      return;
    }

    const includeWarehouses = Object.entries(warehouses)
      .filter(([_, checked]) => checked)
      .map(([code]) => code);

    const categoryList = categories
      .split(/[,\n]/)
      .map((c) => c.trim())
      .filter((c) => c.length > 0);

    const config: CrawlConfig = {
      keywords: keywordList,
      price_min: priceMin,
      price_max: priceMax,
      include_warehouses: includeWarehouses,
      exclude_warehouses: excludedCountries,
      include_categories: categoryList,
      exclude_categories: [],
    };

    await onStartCrawl(config);
    setKeywords("");
  };

  return (
    <Card className="p-6">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">Start New Crawl</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Keywords */}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Keywords (comma or newline separated)
          </label>
          <textarea
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            rows={3}
            placeholder="garden tools, kitchen gadgets, pet supplies"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* Price Range */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Min Price ($)
            </label>
            <input
              type="number"
              value={priceMin}
              onChange={(e) => setPriceMin(parseFloat(e.target.value) || 0)}
              min={0}
              step={0.01}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Max Price ($)
            </label>
            <input
              type="number"
              value={priceMax}
              onChange={(e) => setPriceMax(parseFloat(e.target.value) || 0)}
              min={0}
              step={0.01}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
        </div>

        {/* Warehouses */}
        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700">
            Warehouses
          </label>
          <div className="flex flex-wrap gap-4">
            {["US", "CN", "EU", "UK", "DE", "FR"].map((warehouse) => {
              const isExcluded = excludedCountries.includes(warehouse);
              return (
                <label key={warehouse} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={warehouses[warehouse] || false}
                    onChange={(e) =>
                      setWarehouses((prev) => ({
                        ...prev,
                        [warehouse]: e.target.checked,
                      }))
                    }
                    disabled={isExcluded}
                    className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
                  />
                  <span className={`text-sm ${isExcluded ? "text-gray-400 line-through" : "text-gray-700"}`}>
                    {warehouse}
                    {isExcluded && " (excluded)"}
                  </span>
                </label>
              );
            })}
          </div>
        </div>

        {/* Categories */}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Categories (optional, comma separated)
          </label>
          <input
            type="text"
            value={categories}
            onChange={(e) => setCategories(e.target.value)}
            placeholder="Home & Garden, Electronics"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={isStarting}
          className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {isStarting ? "Starting Crawl..." : "Start Crawl"}
        </button>
      </form>
    </Card>
  );
}

// ============================================================================
// Live Log Panel
// ============================================================================

interface LiveLogPanelProps {
  jobId: string;
  isRunning: boolean;
}

function LiveLogPanel({ jobId, isRunning }: LiveLogPanelProps) {
  const [logs, setLogs] = useState<CrawlLogEntry[]>([]);
  const [isExpanded, setIsExpanded] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const logCountRef = useRef(0);

  useEffect(() => {
    if (!isRunning && logs.length > 0) return;

    const pollLogs = async () => {
      try {
        const response = await getCrawlLogs(jobId, logCountRef.current);
        if (response.logs.length > 0) {
          setLogs((prev) => [...prev, ...response.logs]);
          logCountRef.current += response.logs.length;
        }
      } catch (error) {
        console.error("Failed to fetch logs:", error);
      }
    };

    // Initial fetch
    pollLogs();

    // Poll while running
    if (isRunning) {
      const interval = setInterval(pollLogs, 2000);
      return () => clearInterval(interval);
    }
  }, [jobId, isRunning]);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (logContainerRef.current && isExpanded) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, isExpanded]);

  const getLevelColor = (level: string) => {
    switch (level) {
      case "error":
        return "text-red-600";
      case "warn":
        return "text-yellow-600";
      case "info":
        return "text-gray-700";
      default:
        return "text-gray-500";
    }
  };

  const formatTime = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleTimeString();
  };

  if (logs.length === 0 && !isRunning) return null;

  return (
    <div className="mt-3 border-t pt-3">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between text-xs font-medium text-gray-600 hover:text-gray-800"
      >
        <span>Live Logs ({logs.length})</span>
        <span>{isExpanded ? "▼" : "▶"}</span>
      </button>
      {isExpanded && (
        <div
          ref={logContainerRef}
          className="mt-2 max-h-48 overflow-y-auto rounded bg-gray-900 p-2 font-mono text-xs"
        >
          {logs.length === 0 ? (
            <div className="text-gray-500">Waiting for logs...</div>
          ) : (
            logs.map((log, idx) => (
              <div key={idx} className={`${getLevelColor(log.level)} leading-5`}>
                <span className="text-gray-500">{formatTime(log.ts)}</span>{" "}
                {log.msg}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Crawl Jobs Section
// ============================================================================

interface CrawlJobCardProps {
  job: CrawlJob;
  onCancel: (jobId: string) => void;
  isCancelling: boolean;
}

function CrawlJobCard({ job, onCancel, isCancelling }: CrawlJobCardProps) {
  const progress = job.progress;
  const isRunning = job.status === "running";

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-gray-600">{job.id.slice(0, 8)}</span>
            <StatusBadge status={job.status} />
          </div>
          <div className="mt-1 text-xs text-gray-500">
            Keywords: {job.config.keywords.join(", ")}
          </div>
        </div>
        {isRunning && (
          <button
            onClick={() => onCancel(job.id)}
            disabled={isCancelling}
            className="rounded bg-red-100 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-200 disabled:opacity-50"
          >
            {isCancelling ? "Cancelling..." : "Cancel"}
          </button>
        )}
      </div>

      {/* Progress Stats */}
      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-4">
        <div>
          <span className="text-gray-500">Found:</span>
          <span className="ml-1 font-mono font-medium">{progress.product_urls_found}</span>
        </div>
        <div>
          <span className="text-gray-500">Skipped (existing):</span>
          <span className="ml-1 font-mono font-medium">{progress.product_urls_skipped_existing}</span>
        </div>
        <div>
          <span className="text-gray-500">Scored:</span>
          <span className="ml-1 font-mono font-medium">{progress.products_scored}</span>
        </div>
        <div>
          <span className="text-gray-500">Passed:</span>
          <span className="ml-1 font-mono font-medium text-green-600">{progress.products_passed_scoring}</span>
        </div>
        <div>
          <span className="text-gray-500">Searches:</span>
          <span className="ml-1 font-mono font-medium">
            {progress.search_urls_completed}/{progress.search_urls_submitted}
          </span>
        </div>
        <div>
          <span className="text-gray-500">Products:</span>
          <span className="ml-1 font-mono font-medium">
            {progress.product_urls_completed}/{progress.product_urls_submitted}
          </span>
        </div>
        <div>
          <span className="text-gray-500">Filtered:</span>
          <span className="ml-1 font-mono font-medium">{progress.products_skipped_filtered}</span>
        </div>
        <div>
          <span className="text-gray-500">Errors:</span>
          <span className={`ml-1 font-mono font-medium ${progress.errors > 0 ? "text-red-600" : ""}`}>
            {progress.errors}
          </span>
        </div>
      </div>

      {/* Error Message */}
      {job.error_message && (
        <div className="mt-3 rounded bg-red-50 p-2 text-xs text-red-700">
          {job.error_message}
        </div>
      )}

      {/* Timestamps */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
        <span>Created: {formatDate(job.created_at)}</span>
        {job.started_at && <span>Started: {formatDate(job.started_at)}</span>}
        {job.completed_at && <span>Completed: {formatDate(job.completed_at)}</span>}
      </div>

      {/* Live Log Panel */}
      <LiveLogPanel jobId={job.id} isRunning={isRunning} />
    </Card>
  );
}

interface CrawlJobsListProps {
  jobs: CrawlJob[];
  onCancel: (jobId: string) => void;
  cancellingJobId: string | null;
  isLoading: boolean;
  onRefresh: () => void;
}

function CrawlJobsList({ jobs, onCancel, cancellingJobId, isLoading, onRefresh }: CrawlJobsListProps) {
  return (
    <Card className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Crawl Jobs</h2>
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="rounded bg-gray-100 px-3 py-1 text-sm font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50"
        >
          {isLoading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {jobs.length === 0 ? (
        <div className="py-8 text-center text-gray-500">
          No crawl jobs yet. Start one above!
        </div>
      ) : (
        <div className="space-y-4">
          {jobs.map((job) => (
            <CrawlJobCard
              key={job.id}
              job={job}
              onCancel={onCancel}
              isCancelling={cancellingJobId === job.id}
            />
          ))}
        </div>
      )}
    </Card>
  );
}

// ============================================================================
// Exclusion Rules Section
// ============================================================================

interface ExclusionRulesManagerProps {
  rules: ExclusionRule[];
  onAddRule: (rule: { rule_type: string; value: string; reason?: string }) => Promise<void>;
  onDeleteRule: (id: string) => Promise<void>;
  isLoading: boolean;
  addingRule: boolean;
  deletingRuleId: string | null;
}

function ExclusionRulesManager({
  rules,
  onAddRule,
  onDeleteRule,
  isLoading,
  addingRule,
  deletingRuleId,
}: ExclusionRulesManagerProps) {
  const [ruleType, setRuleType] = useState<string>("country");
  const [value, setValue] = useState<string>("");
  const [reason, setReason] = useState<string>("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) {
      alert("Please enter a value");
      return;
    }
    await onAddRule({
      rule_type: ruleType,
      value: value.trim(),
      reason: reason.trim() || undefined,
    });
    setValue("");
    setReason("");
  };

  // Group rules by type
  const rulesByType = rules.reduce(
    (acc, rule) => {
      if (!acc[rule.rule_type]) {
        acc[rule.rule_type] = [];
      }
      acc[rule.rule_type].push(rule);
      return acc;
    },
    {} as Record<string, ExclusionRule[]>
  );

  const ruleTypes: ExclusionRule['rule_type'][] = ["country", "category", "supplier", "keyword"];

  return (
    <Card className="p-6">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">Exclusion Rules</h2>

      {/* Add Rule Form */}
      <form onSubmit={handleSubmit} className="mb-6 rounded-lg bg-gray-50 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">Type</label>
            <select
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="country">Country</option>
              <option value="category">Category</option>
              <option value="supplier">Supplier</option>
              <option value="keyword">Keyword</option>
            </select>
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-gray-600">Value</label>
            <input
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={
                ruleType === "country"
                  ? "DE, FR, UK..."
                  : ruleType === "category"
                    ? "Clothing, Jewelry..."
                    : ruleType === "supplier"
                      ? "Supplier ID..."
                      : "replica, fake..."
              }
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-gray-600">
              Reason (optional)
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why exclude this?"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={addingRule}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {addingRule ? "Adding..." : "Add Rule"}
          </button>
        </div>
      </form>

      {/* Rules List */}
      {isLoading ? (
        <div className="py-4 text-center text-gray-500">Loading rules...</div>
      ) : rules.length === 0 ? (
        <div className="py-4 text-center text-gray-500">No exclusion rules yet.</div>
      ) : (
        <div className="space-y-4">
          {ruleTypes.map((type) => {
            const typeRules = rulesByType[type];
            if (!typeRules || typeRules.length === 0) return null;

            return (
              <div key={type}>
                <h3 className="mb-2 text-sm font-medium capitalize text-gray-700">
                  {type} Rules ({typeRules.length})
                </h3>
                <div className="flex flex-wrap gap-2">
                  {typeRules.map((rule) => (
                    <div
                      key={rule.id}
                      className="group flex items-center gap-2 rounded-full border bg-white px-3 py-1"
                    >
                      <RuleTypeBadge ruleType={rule.rule_type} />
                      <span className="text-sm font-medium">{rule.value}</span>
                      {rule.reason && (
                        <span className="text-xs text-gray-400" title={rule.reason}>
                          ({rule.reason})
                        </span>
                      )}
                      <button
                        onClick={() => onDeleteRule(rule.id)}
                        disabled={deletingRuleId === rule.id}
                        className="ml-1 text-gray-400 hover:text-red-600 disabled:opacity-50"
                        title="Delete rule"
                      >
                        {deletingRuleId === rule.id ? "..." : "x"}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

// ============================================================================
// Main Page Component
// ============================================================================

export default function CrawlPage() {
  // Jobs state
  const [jobs, setJobs] = useState<CrawlJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [startingCrawl, setStartingCrawl] = useState(false);
  const [cancellingJobId, setCancellingJobId] = useState<string | null>(null);

  // Exclusion rules state
  const [rules, setRules] = useState<ExclusionRule[]>([]);
  const [loadingRules, setLoadingRules] = useState(true);
  const [addingRule, setAddingRule] = useState(false);
  const [deletingRuleId, setDeletingRuleId] = useState<string | null>(null);

  // Messages
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Get excluded countries from rules
  const excludedCountries = rules
    .filter((r) => r.rule_type === "country")
    .map((r) => r.value);

  // Load jobs
  const loadJobs = useCallback(async () => {
    setLoadingJobs(true);
    try {
      const data = await getCrawlJobs();
      setJobs(data);
    } catch (err) {
      console.error("Failed to load jobs:", err);
    } finally {
      setLoadingJobs(false);
    }
  }, []);

  // Load rules
  const loadRules = useCallback(async () => {
    setLoadingRules(true);
    try {
      const data = await getExclusionRules();
      setRules(data);
    } catch (err) {
      console.error("Failed to load rules:", err);
    } finally {
      setLoadingRules(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadJobs();
    loadRules();
  }, [loadJobs, loadRules]);

  // Poll for running jobs
  useEffect(() => {
    const hasRunningJob = jobs.some((job) => job.status === "running" || job.status === "pending");
    if (!hasRunningJob) return;

    const interval = setInterval(async () => {
      try {
        const updatedJobs = await getCrawlJobs();
        setJobs(updatedJobs);
      } catch (err) {
        console.error("Failed to poll jobs:", err);
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [jobs]);

  // Handlers
  const handleStartCrawl = async (config: CrawlConfig) => {
    setStartingCrawl(true);
    try {
      const response = await startCrawl(config);
      // Fetch the full job to add to the list
      const job = await getCrawlJob(response.job_id);
      setJobs((prev) => [job, ...prev]);
      setMessage({ type: "success", text: `Crawl job ${response.job_id.slice(0, 8)} started!` });
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to start crawl",
      });
    } finally {
      setStartingCrawl(false);
    }
    setTimeout(() => setMessage(null), 5000);
  };

  const handleCancelCrawl = async (jobId: string) => {
    setCancellingJobId(jobId);
    try {
      await cancelCrawl(jobId);
      setJobs((prev) =>
        prev.map((job) =>
          job.id === jobId ? { ...job, status: "cancelled" as const } : job
        )
      );
      setMessage({ type: "success", text: "Crawl cancelled" });
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to cancel crawl",
      });
    } finally {
      setCancellingJobId(null);
    }
    setTimeout(() => setMessage(null), 3000);
  };

  const handleAddRule = async (rule: { rule_type: string; value: string; reason?: string }) => {
    setAddingRule(true);
    try {
      const newRule = await addExclusionRule(rule);
      setRules((prev) => [...prev, newRule]);
      setMessage({ type: "success", text: "Rule added" });
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to add rule",
      });
    } finally {
      setAddingRule(false);
    }
    setTimeout(() => setMessage(null), 3000);
  };

  const handleDeleteRule = async (id: string) => {
    setDeletingRuleId(id);
    try {
      await deleteExclusionRule(id);
      setRules((prev) => prev.filter((r) => r.id !== id));
      setMessage({ type: "success", text: "Rule deleted" });
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to delete rule",
      });
    } finally {
      setDeletingRuleId(null);
    }
    setTimeout(() => setMessage(null), 3000);
  };

  return (
    <main className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="border-b bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Crawl Management</h1>
            <p className="text-sm text-gray-500">
              Configure and monitor CJ Dropshipping product crawls
            </p>
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/admin"
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline"
            >
              Back to Dashboard
            </Link>
          </div>
        </div>
      </header>

      {/* Message */}
      {message && (
        <div className="mx-auto mt-4 max-w-7xl px-4">
          <div
            className={`rounded-lg p-3 ${
              message.type === "success"
                ? "bg-green-50 text-green-600"
                : "bg-red-50 text-red-600"
            }`}
          >
            {message.text}
          </div>
        </div>
      )}

      {/* Content */}
      <div className="mx-auto max-w-7xl px-4 py-6">
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Left Column */}
          <div className="space-y-6">
            <NewCrawlForm
              excludedCountries={excludedCountries}
              onStartCrawl={handleStartCrawl}
              isStarting={startingCrawl}
            />
            <ExclusionRulesManager
              rules={rules}
              onAddRule={handleAddRule}
              onDeleteRule={handleDeleteRule}
              isLoading={loadingRules}
              addingRule={addingRule}
              deletingRuleId={deletingRuleId}
            />
          </div>

          {/* Right Column */}
          <div>
            <CrawlJobsList
              jobs={jobs}
              onCancel={handleCancelCrawl}
              cancellingJobId={cancellingJobId}
              isLoading={loadingJobs}
              onRefresh={loadJobs}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
