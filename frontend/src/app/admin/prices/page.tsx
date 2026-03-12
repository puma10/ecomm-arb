"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import { Card } from "@/components/ui/card";
import {
  getPriceStats,
  getPriceComparison,
  getPriceHistory,
  getPriceAlerts,
  createPriceAlert,
  dismissPriceAlert,
  snapshotPrices,
  PriceStatsResponse,
  PriceComparisonItem,
  PriceHistoryResponse,
  PriceAlertItem,
} from "@/lib/api";

// ============================================================================
// Stat Card
// ============================================================================

function StatCard({
  label,
  value,
  sub,
  color = "text-gray-900",
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  return (
    <Card className="p-4">
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </Card>
  );
}

// ============================================================================
// Price Change Badge
// ============================================================================

function PriceChangeBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-xs text-gray-400">-</span>;
  const isUp = pct > 0;
  const isDown = pct < 0;
  const color = isDown
    ? "text-green-700 bg-green-50"
    : isUp
      ? "text-red-700 bg-red-50"
      : "text-gray-700 bg-gray-50";
  const arrow = isDown ? "\u2193" : isUp ? "\u2191" : "";
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>
      {arrow} {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

// ============================================================================
// Alert Status Badge
// ============================================================================

function AlertStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    active: "bg-blue-100 text-blue-800",
    triggered: "bg-red-100 text-red-800",
    dismissed: "bg-gray-100 text-gray-500",
  };
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${colors[status] || "bg-gray-100"}`}
    >
      {status}
    </span>
  );
}

// ============================================================================
// Price History Chart
// ============================================================================

function PriceChart({ data }: { data: PriceHistoryResponse | null }) {
  if (!data || data.items.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        No price history data. Take a snapshot to begin tracking.
      </div>
    );
  }

  const chartData = data.items.map((item) => ({
    date: new Date(item.recorded_at).toLocaleDateString(),
    price: item.price,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" tick={{ fontSize: 12 }} />
        <YAxis
          tick={{ fontSize: 12 }}
          tickFormatter={(v: number) => `$${v}`}
          domain={["auto", "auto"]}
        />
        <Tooltip
          formatter={(value) => [`$${Number(value).toFixed(2)}`, "Price"]}
        />
        <Line
          type="monotone"
          dataKey="price"
          stroke="#2563eb"
          strokeWidth={2}
          dot={{ r: 3 }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ============================================================================
// Main Dashboard
// ============================================================================

export default function PriceMonitoringPage() {
  const [stats, setStats] = useState<PriceStatsResponse | null>(null);
  const [comparison, setComparison] = useState<PriceComparisonItem[]>([]);
  const [comparisonTotal, setComparisonTotal] = useState(0);
  const [alerts, setAlerts] = useState<PriceAlertItem[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<string | null>(null);
  const [priceHistory, setPriceHistory] = useState<PriceHistoryResponse | null>(null);
  const [search, setSearch] = useState("");
  const [historyDays, setHistoryDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotResult, setSnapshotResult] = useState<string | null>(null);
  const [alertForm, setAlertForm] = useState({
    product_ref: "",
    condition: "below",
    threshold: 0,
  });
  const [tab, setTab] = useState<"overview" | "comparison" | "alerts">("overview");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsData, compData, alertsData] = await Promise.all([
        getPriceStats(),
        getPriceComparison({ search: search || undefined, limit: 50 }),
        getPriceAlerts(),
      ]);
      setStats(statsData);
      setComparison(compData.items);
      setComparisonTotal(compData.total);
      setAlerts(alertsData.items);
    } catch (err) {
      console.error("Failed to load price data:", err);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const loadHistory = useCallback(
    async (productRef: string) => {
      try {
        const data = await getPriceHistory(productRef, historyDays);
        setPriceHistory(data);
      } catch (err) {
        console.error("Failed to load price history:", err);
      }
    },
    [historyDays]
  );

  useEffect(() => {
    if (selectedProduct) {
      loadHistory(selectedProduct);
    }
  }, [selectedProduct, loadHistory]);

  const handleSnapshot = async () => {
    setSnapshotLoading(true);
    setSnapshotResult(null);
    try {
      const result = await snapshotPrices();
      setSnapshotResult(
        `Checked ${result.products_checked} products, recorded ${result.prices_recorded} price changes`
      );
      await loadData();
    } catch (err) {
      setSnapshotResult(`Error: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setSnapshotLoading(false);
    }
  };

  const handleCreateAlert = async () => {
    if (!alertForm.product_ref || alertForm.threshold <= 0) return;
    try {
      await createPriceAlert({
        product_ref: alertForm.product_ref,
        condition: alertForm.condition,
        threshold: alertForm.threshold,
      });
      setAlertForm({ product_ref: "", condition: "below", threshold: 0 });
      await loadData();
    } catch (err) {
      console.error("Failed to create alert:", err);
    }
  };

  const handleDismissAlert = async (id: string) => {
    try {
      await dismissPriceAlert(id);
      await loadData();
    } catch (err) {
      console.error("Failed to dismiss alert:", err);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/admin" className="text-sm text-blue-600 hover:underline">
              &larr; Admin
            </Link>
            <h1 className="text-xl font-bold text-gray-900">Price Monitor</h1>
          </div>
          <button
            onClick={handleSnapshot}
            disabled={snapshotLoading}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {snapshotLoading ? "Taking Snapshot..." : "Take Price Snapshot"}
          </button>
        </div>
        {snapshotResult && (
          <div className="max-w-7xl mx-auto px-4 pb-3">
            <p className="text-sm text-green-700 bg-green-50 rounded px-3 py-1">
              {snapshotResult}
            </p>
          </div>
        )}
      </div>

      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <StatCard label="Tracked Products" value={stats.total_tracked} />
            <StatCard label="Observations" value={stats.total_observations} />
            <StatCard
              label="Active Alerts"
              value={stats.active_alerts}
              color="text-blue-600"
            />
            <StatCard
              label="Triggered Alerts"
              value={stats.triggered_alerts}
              color="text-red-600"
            />
            <StatCard
              label="Price Drops"
              value={stats.products_with_price_drops}
              color="text-green-600"
            />
            <StatCard
              label="Price Increases"
              value={stats.products_with_price_increases}
              color="text-orange-600"
            />
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 border-b">
          {(["overview", "comparison", "alerts"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                tab === t
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t === "overview"
                ? "Overview"
                : t === "comparison"
                  ? "Comparison Table"
                  : "Alerts"}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {loading ? (
          <div className="text-center py-12 text-gray-400">Loading...</div>
        ) : (
          <>
            {/* ============================================================ */}
            {/* Overview Tab */}
            {/* ============================================================ */}
            {tab === "overview" && (
              <div className="space-y-6">
                {/* Product selector + chart */}
                <Card className="p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="font-semibold text-gray-900">Price History</h2>
                    <div className="flex gap-2">
                      <select
                        value={historyDays}
                        onChange={(e) => setHistoryDays(Number(e.target.value))}
                        className="rounded border px-2 py-1 text-sm"
                      >
                        <option value={7}>7 days</option>
                        <option value={30}>30 days</option>
                        <option value={90}>90 days</option>
                        <option value={365}>1 year</option>
                      </select>
                    </div>
                  </div>

                  {/* Product chips */}
                  {comparison.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-4">
                      {comparison.slice(0, 20).map((p) => (
                        <button
                          key={p.product_ref}
                          onClick={() => setSelectedProduct(p.product_ref)}
                          className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                            selectedProduct === p.product_ref
                              ? "bg-blue-600 text-white border-blue-600"
                              : "bg-white text-gray-700 hover:bg-gray-100"
                          }`}
                        >
                          {p.product_name.length > 40
                            ? p.product_name.slice(0, 40) + "..."
                            : p.product_name}
                        </button>
                      ))}
                    </div>
                  )}

                  <PriceChart data={priceHistory} />

                  {priceHistory && priceHistory.items.length > 0 && (
                    <div className="grid grid-cols-4 gap-4 mt-4 text-center">
                      <div>
                        <p className="text-xs text-gray-500">Current</p>
                        <p className="font-bold">
                          ${priceHistory.current_price?.toFixed(2) ?? "-"}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Min</p>
                        <p className="font-bold text-green-600">
                          ${priceHistory.price_min?.toFixed(2) ?? "-"}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Max</p>
                        <p className="font-bold text-red-600">
                          ${priceHistory.price_max?.toFixed(2) ?? "-"}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Change</p>
                        <PriceChangeBadge pct={priceHistory.price_change_pct} />
                      </div>
                    </div>
                  )}
                </Card>

                {/* Recent triggered alerts */}
                {alerts.filter((a) => a.status === "triggered").length > 0 && (
                  <Card className="p-6">
                    <h2 className="font-semibold text-red-600 mb-3">Triggered Alerts</h2>
                    <div className="space-y-2">
                      {alerts
                        .filter((a) => a.status === "triggered")
                        .map((a) => (
                          <div
                            key={a.id}
                            className="flex items-center justify-between bg-red-50 rounded p-3"
                          >
                            <div>
                              <p className="text-sm font-medium">{a.product_name}</p>
                              <p className="text-xs text-gray-500">
                                {a.condition} ${a.threshold.toFixed(2)} &mdash; triggered at $
                                {a.triggered_price?.toFixed(2)}
                              </p>
                            </div>
                            <button
                              onClick={() => handleDismissAlert(a.id)}
                              className="text-xs text-gray-500 hover:text-red-600"
                            >
                              Dismiss
                            </button>
                          </div>
                        ))}
                    </div>
                  </Card>
                )}
              </div>
            )}

            {/* ============================================================ */}
            {/* Comparison Table Tab */}
            {/* ============================================================ */}
            {tab === "comparison" && (
              <Card className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-semibold text-gray-900">
                    Price Comparison ({comparisonTotal} products)
                  </h2>
                  <input
                    type="text"
                    placeholder="Search products..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="rounded border px-3 py-1.5 text-sm w-64"
                  />
                </div>

                {comparison.length === 0 ? (
                  <p className="text-center text-gray-400 py-8">
                    No price data yet. Take a snapshot to begin tracking prices.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-gray-500">
                          <th className="pb-2 pr-4">Product</th>
                          <th className="pb-2 pr-4 text-right">Current</th>
                          <th className="pb-2 pr-4 text-right">Previous</th>
                          <th className="pb-2 pr-4 text-right">Change</th>
                          <th className="pb-2 pr-4 text-right">30d Min</th>
                          <th className="pb-2 pr-4 text-right">30d Max</th>
                          <th className="pb-2 pr-4">Source</th>
                          <th className="pb-2">Updated</th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparison.map((item) => (
                          <tr
                            key={item.product_ref}
                            className="border-b hover:bg-gray-50 cursor-pointer"
                            onClick={() => {
                              setSelectedProduct(item.product_ref);
                              setTab("overview");
                            }}
                          >
                            <td className="py-2 pr-4 max-w-xs truncate" title={item.product_name}>
                              {item.product_name}
                            </td>
                            <td className="py-2 pr-4 text-right font-mono font-bold">
                              ${item.current_price?.toFixed(2) ?? "-"}
                            </td>
                            <td className="py-2 pr-4 text-right font-mono text-gray-500">
                              {item.previous_price != null
                                ? `$${item.previous_price.toFixed(2)}`
                                : "-"}
                            </td>
                            <td className="py-2 pr-4 text-right">
                              <PriceChangeBadge pct={item.price_change_pct} />
                            </td>
                            <td className="py-2 pr-4 text-right font-mono text-green-600">
                              {item.price_min_30d != null
                                ? `$${item.price_min_30d.toFixed(2)}`
                                : "-"}
                            </td>
                            <td className="py-2 pr-4 text-right font-mono text-red-600">
                              {item.price_max_30d != null
                                ? `$${item.price_max_30d.toFixed(2)}`
                                : "-"}
                            </td>
                            <td className="py-2 pr-4 text-xs text-gray-500">
                              {item.source ?? "-"}
                            </td>
                            <td className="py-2 text-xs text-gray-400">
                              {item.last_updated
                                ? new Date(item.last_updated).toLocaleDateString()
                                : "-"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            )}

            {/* ============================================================ */}
            {/* Alerts Tab */}
            {/* ============================================================ */}
            {tab === "alerts" && (
              <div className="space-y-6">
                {/* Create Alert */}
                <Card className="p-6">
                  <h2 className="font-semibold text-gray-900 mb-4">Create Alert</h2>
                  <div className="flex flex-wrap gap-3 items-end">
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">Product Ref</label>
                      <input
                        type="text"
                        value={alertForm.product_ref}
                        onChange={(e) =>
                          setAlertForm({ ...alertForm, product_ref: e.target.value })
                        }
                        placeholder="source_product_id"
                        className="rounded border px-3 py-1.5 text-sm w-48"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">Condition</label>
                      <select
                        value={alertForm.condition}
                        onChange={(e) =>
                          setAlertForm({ ...alertForm, condition: e.target.value })
                        }
                        className="rounded border px-3 py-1.5 text-sm"
                      >
                        <option value="below">Price drops below</option>
                        <option value="above">Price rises above</option>
                        <option value="change_pct">Change exceeds %</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">
                        Threshold {alertForm.condition === "change_pct" ? "(%)" : "($)"}
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        value={alertForm.threshold || ""}
                        onChange={(e) =>
                          setAlertForm({
                            ...alertForm,
                            threshold: parseFloat(e.target.value) || 0,
                          })
                        }
                        className="rounded border px-3 py-1.5 text-sm w-28"
                      />
                    </div>
                    <button
                      onClick={handleCreateAlert}
                      className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
                    >
                      Create
                    </button>
                  </div>
                </Card>

                {/* Alert List */}
                <Card className="p-6">
                  <h2 className="font-semibold text-gray-900 mb-4">
                    All Alerts ({alerts.length})
                  </h2>
                  {alerts.length === 0 ? (
                    <p className="text-center text-gray-400 py-8">
                      No alerts configured yet.
                    </p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left text-gray-500">
                            <th className="pb-2 pr-4">Product</th>
                            <th className="pb-2 pr-4">Condition</th>
                            <th className="pb-2 pr-4 text-right">Threshold</th>
                            <th className="pb-2 pr-4">Status</th>
                            <th className="pb-2 pr-4 text-right">Triggered Price</th>
                            <th className="pb-2 pr-4">Created</th>
                            <th className="pb-2"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {alerts.map((a) => (
                            <tr key={a.id} className="border-b hover:bg-gray-50">
                              <td className="py-2 pr-4 max-w-xs truncate">
                                {a.product_name || a.product_ref}
                              </td>
                              <td className="py-2 pr-4 text-xs">
                                {a.condition === "below"
                                  ? "Below"
                                  : a.condition === "above"
                                    ? "Above"
                                    : "Change %"}
                              </td>
                              <td className="py-2 pr-4 text-right font-mono">
                                {a.condition === "change_pct"
                                  ? `${a.threshold}%`
                                  : `$${a.threshold.toFixed(2)}`}
                              </td>
                              <td className="py-2 pr-4">
                                <AlertStatusBadge status={a.status} />
                              </td>
                              <td className="py-2 pr-4 text-right font-mono">
                                {a.triggered_price != null
                                  ? `$${a.triggered_price.toFixed(2)}`
                                  : "-"}
                              </td>
                              <td className="py-2 pr-4 text-xs text-gray-400">
                                {new Date(a.created_at).toLocaleDateString()}
                              </td>
                              <td className="py-2 text-right">
                                {a.status !== "dismissed" && (
                                  <button
                                    onClick={() => handleDismissAlert(a.id)}
                                    className="text-xs text-gray-500 hover:text-red-600"
                                  >
                                    Dismiss
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
