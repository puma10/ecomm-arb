"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import {
  getScoredProducts,
  getScoredProduct,
  approveProduct,
  rejectProduct,
  seedDemoProducts,
  clearScoredProducts,
  getScoringSettings,
  updateScoringSettings,
  discoverProducts,
  ScoredProduct,
  ScoredProductFull,
  ScoringSettings,
} from "@/lib/api";

const RECOMMENDATIONS = ["STRONG BUY", "VIABLE", "MARGINAL", "WEAK", "REJECT"];

function RecommendationBadge({ rec }: { rec: string }) {
  const colors: Record<string, string> = {
    "STRONG BUY": "bg-green-100 text-green-800 border-green-300",
    VIABLE: "bg-blue-100 text-blue-800 border-blue-300",
    MARGINAL: "bg-yellow-100 text-yellow-800 border-yellow-300",
    WEAK: "bg-orange-100 text-orange-800 border-orange-300",
    REJECT: "bg-red-100 text-red-800 border-red-300",
  };

  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-xs font-semibold ${colors[rec] || "bg-gray-100 text-gray-800"}`}
    >
      {rec}
    </span>
  );
}

function MarginIndicator({ margin }: { margin: number }) {
  const pct = (margin * 100).toFixed(1);
  let color = "text-red-600";
  if (margin >= 0.4) color = "text-green-600";
  else if (margin >= 0.25) color = "text-blue-600";
  else if (margin >= 0.15) color = "text-yellow-600";

  return <span className={`font-mono font-bold ${color}`}>{pct}%</span>;
}

function WarehouseBadge({ country }: { country: string | null }) {
  if (!country) return <span className="text-xs text-gray-400">-</span>;

  const colors: Record<string, string> = {
    US: "bg-green-100 text-green-800 border-green-300",
    CN: "bg-amber-100 text-amber-800 border-amber-300",
    HK: "bg-amber-100 text-amber-800 border-amber-300",
  };

  const labels: Record<string, string> = {
    US: "US",
    CN: "China",
    HK: "HK",
  };

  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 text-xs font-medium ${colors[country] || "bg-gray-100 text-gray-700 border-gray-300"}`}
    >
      {labels[country] || country}
    </span>
  );
}

interface SettingInputProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  suffix?: string;
  step?: number;
  min?: number;
  max?: number;
  isPercent?: boolean;
}

function SettingInput({
  label,
  value,
  onChange,
  suffix = "",
  step = 0.01,
  min = 0,
  max,
  isPercent = false,
}: SettingInputProps) {
  const displayValue = isPercent ? value * 100 : value;

  return (
    <div className="flex items-center justify-between gap-4">
      <label className="text-sm text-gray-600">{label}</label>
      <div className="flex items-center gap-1">
        <input
          type="number"
          value={displayValue}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            onChange(isPercent ? v / 100 : v);
          }}
          step={isPercent ? step * 100 : step}
          min={isPercent ? (min !== undefined ? min * 100 : undefined) : min}
          max={isPercent ? (max !== undefined ? max * 100 : undefined) : max}
          className="w-20 rounded border border-gray-300 px-2 py-1 text-right text-sm font-mono"
        />
        <span className="w-8 text-xs text-gray-500">{suffix}</span>
      </div>
    </div>
  );
}

function DiscoverPanel({
  onDiscover,
  onSeedDemo,
  onClose,
  discovering,
}: {
  onDiscover: (keywords: string[], limit: number) => Promise<void>;
  onSeedDemo: () => Promise<void>;
  onClose: () => void;
  discovering: boolean;
}) {
  const [keywords, setKeywords] = useState<string>("garden tools\nkitchen gadgets\npet supplies");
  const [limit, setLimit] = useState(10);
  const [mode, setMode] = useState<"cj" | "demo">("cj");

  const handleDiscover = async () => {
    if (mode === "demo") {
      await onSeedDemo();
    } else {
      const keywordList = keywords
        .split("\n")
        .map((k) => k.trim())
        .filter((k) => k.length > 0);
      if (keywordList.length === 0) {
        alert("Please enter at least one keyword");
        return;
      }
      await onDiscover(keywordList, limit);
    }
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <Card
        className="w-full max-w-lg bg-white p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-bold">Discover Products</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>

        {/* Mode Selector */}
        <div className="mb-4 flex rounded-lg border border-gray-200 p-1">
          <button
            onClick={() => setMode("cj")}
            className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition ${
              mode === "cj"
                ? "bg-blue-600 text-white"
                : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            CJ Dropshipping
          </button>
          <button
            onClick={() => setMode("demo")}
            className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition ${
              mode === "demo"
                ? "bg-blue-600 text-white"
                : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            Demo Data
          </button>
        </div>

        {mode === "cj" ? (
          <>
            <div className="mb-4">
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Search Keywords (one per line)
              </label>
              <textarea
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                rows={5}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="garden tools&#10;kitchen gadgets&#10;pet supplies"
              />
            </div>

            <div className="mb-4">
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Products per keyword
              </label>
              <input
                type="number"
                value={limit}
                onChange={(e) => setLimit(parseInt(e.target.value) || 10)}
                min={1}
                max={50}
                className="w-24 rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </div>

            <div className="mb-4 rounded-lg bg-blue-50 p-3 text-sm text-blue-800">
              <strong>What happens:</strong>
              <ol className="mt-2 list-inside list-decimal space-y-1">
                <li>Search CJ Dropshipping for products matching your keywords</li>
                <li>Calculate real shipping costs via CJ Freight API</li>
                <li>Get real CPC estimates from Google Ads (if configured)</li>
                <li>Score each product against your criteria</li>
                <li>Save results for review</li>
              </ol>
            </div>

            <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
              <strong>Requirements:</strong>
              <ul className="mt-1 list-inside list-disc">
                <li>CJ_API_KEY environment variable must be set</li>
                <li>Google Ads credentials (optional, for real CPC)</li>
              </ul>
            </div>
          </>
        ) : (
          <div className="mb-4 rounded-lg bg-gray-50 p-4 text-sm text-gray-700">
            <p className="mb-2">
              <strong>Demo Mode:</strong> Generate sample products with realistic
              scoring data for testing the dashboard.
            </p>
            <p>
              If Google Ads credentials are configured, demo products will use
              real CPC data from Google Ads Keyword Planner.
            </p>
          </div>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleDiscover}
            disabled={discovering}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {discovering
              ? "Discovering..."
              : mode === "cj"
                ? "Search CJ Products"
                : "Generate Demo Products"}
          </button>
        </div>
      </Card>
    </div>
  );
}

function SettingsPanel({
  settings,
  onUpdate,
  onClose,
}: {
  settings: ScoringSettings;
  onUpdate: (settings: Partial<ScoringSettings>) => Promise<void>;
  onClose: () => void;
}) {
  const [localSettings, setLocalSettings] = useState(settings);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await onUpdate(localSettings);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const update = (key: keyof ScoringSettings, value: number) => {
    setLocalSettings((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <Card
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto bg-white p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-bold">Scoring Settings</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded bg-red-50 p-3 text-red-600">{error}</div>
        )}

        <div className="grid gap-6 md:grid-cols-2">
          {/* Hard Filters */}
          <div>
            <h3 className="mb-3 font-semibold text-gray-800">Hard Filters</h3>
            <div className="space-y-3 rounded-lg bg-gray-50 p-4">
              <SettingInput
                label="Max CPC Threshold"
                value={localSettings.max_cpc_threshold}
                onChange={(v) => update("max_cpc_threshold", v)}
                suffix="$"
                step={0.05}
              />
              <SettingInput
                label="Min Gross Margin"
                value={localSettings.min_gross_margin}
                onChange={(v) => update("min_gross_margin", v)}
                suffix="%"
                isPercent
                step={0.01}
                max={1}
              />
              <SettingInput
                label="Min Selling Price"
                value={localSettings.min_selling_price}
                onChange={(v) => update("min_selling_price", v)}
                suffix="$"
                step={5}
              />
              <SettingInput
                label="Max Selling Price"
                value={localSettings.max_selling_price}
                onChange={(v) => update("max_selling_price", v)}
                suffix="$"
                step={10}
              />
              <SettingInput
                label="Min CPC Buffer"
                value={localSettings.min_cpc_buffer}
                onChange={(v) => update("min_cpc_buffer", v)}
                suffix="x"
                step={0.1}
              />
              <SettingInput
                label="Max Shipping Days"
                value={localSettings.max_shipping_days}
                onChange={(v) => update("max_shipping_days", v)}
                suffix="days"
                step={1}
              />
              <SettingInput
                label="Max Weight"
                value={localSettings.max_weight_grams}
                onChange={(v) => update("max_weight_grams", v)}
                suffix="g"
                step={100}
              />
            </div>
          </div>

          {/* Supplier & Competition */}
          <div>
            <h3 className="mb-3 font-semibold text-gray-800">
              Supplier & Competition
            </h3>
            <div className="space-y-3 rounded-lg bg-gray-50 p-4">
              <SettingInput
                label="Min Supplier Rating"
                value={localSettings.min_supplier_rating}
                onChange={(v) => update("min_supplier_rating", v)}
                suffix="★"
                step={0.1}
                min={0}
                max={5}
              />
              <SettingInput
                label="Min Supplier Age"
                value={localSettings.min_supplier_age_months}
                onChange={(v) => update("min_supplier_age_months", v)}
                suffix="mo"
                step={1}
              />
              <SettingInput
                label="Min Supplier Feedback"
                value={localSettings.min_supplier_feedback}
                onChange={(v) => update("min_supplier_feedback", v)}
                suffix=""
                step={50}
              />
              <SettingInput
                label="Max Amazon Reviews"
                value={localSettings.max_amazon_reviews_for_competition}
                onChange={(v) => update("max_amazon_reviews_for_competition", v)}
                suffix=""
                step={50}
              />
            </div>

            <h3 className="mb-3 mt-6 font-semibold text-gray-800">
              Fee Assumptions
            </h3>
            <div className="space-y-3 rounded-lg bg-gray-50 p-4">
              <SettingInput
                label="Payment Fee"
                value={localSettings.payment_fee_rate}
                onChange={(v) => update("payment_fee_rate", v)}
                suffix="%"
                isPercent
                step={0.01}
                max={1}
              />
              <SettingInput
                label="Chargeback Rate"
                value={localSettings.chargeback_rate}
                onChange={(v) => update("chargeback_rate", v)}
                suffix="%"
                isPercent
                step={0.001}
                max={1}
              />
              <SettingInput
                label="Default Refund Rate"
                value={localSettings.default_refund_rate}
                onChange={(v) => update("default_refund_rate", v)}
                suffix="%"
                isPercent
                step={0.01}
                max={1}
              />
              <SettingInput
                label="Conversion Rate"
                value={localSettings.cvr}
                onChange={(v) => update("cvr", v)}
                suffix="%"
                isPercent
                step={0.001}
                max={1}
              />
              <SettingInput
                label="CPC Multiplier (new acct)"
                value={localSettings.cpc_multiplier}
                onChange={(v) => update("cpc_multiplier", v)}
                suffix="x"
                step={0.1}
                min={1}
                max={5}
              />
            </div>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </div>
      </Card>
    </div>
  );
}

function ProductDetailModal({
  product,
  onClose,
  onApprove,
  onReject,
}: {
  product: ScoredProductFull;
  onClose: () => void;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  const profit = product.selling_price - product.cogs;
  const adCostPerSale = product.estimated_cpc / 0.01; // Assuming 1% CVR

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <Card
        className="max-h-[90vh] w-full max-w-4xl overflow-y-auto bg-white p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">{product.name}</h2>
            <div className="mt-1 flex items-center gap-3">
              <span className="text-sm text-gray-500">{product.category}</span>
              <span className="text-sm text-gray-400">•</span>
              <span className="text-sm text-gray-500">
                Source: {product.source}
              </span>
              <RecommendationBadge rec={product.recommendation} />
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-2xl text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>

        {/* Verdict Banner */}
        <div
          className={`mb-6 rounded-lg p-4 ${
            product.passed_filters
              ? "border border-green-200 bg-green-50"
              : "border border-red-200 bg-red-50"
          }`}
        >
          <div className="flex items-center justify-between">
            <div>
              <h3
                className={`font-bold ${product.passed_filters ? "text-green-800" : "text-red-800"}`}
              >
                {product.passed_filters
                  ? `✅ PASSED - ${product.recommendation}`
                  : "❌ REJECTED"}
              </h3>
              {!product.passed_filters && product.rejection_reasons?.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {product.rejection_reasons.map((reason, i) => (
                    <li key={i} className="text-sm text-red-700">
                      • {reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {product.passed_filters && (
              <div className="text-right">
                <div className="text-3xl font-bold text-green-700">
                  {product.points}
                </div>
                <div className="text-sm text-green-600">points</div>
              </div>
            )}
          </div>
        </div>

        {/* Financial Analysis */}
        <div className="mb-6 grid gap-4 md:grid-cols-3">
          {/* Unit Economics */}
          <div className="rounded-lg border bg-gray-50 p-4">
            <h4 className="mb-3 font-semibold text-gray-800">
              Unit Economics
            </h4>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Selling Price</span>
                <span className="font-mono font-bold">
                  ${product.selling_price.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Product Cost</span>
                <span className="font-mono text-red-600">
                  -${product.product_cost.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Shipping Cost</span>
                <span className="font-mono text-red-600">
                  -${product.shipping_cost.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between border-t pt-2">
                <span className="text-gray-700 font-medium">COGS</span>
                <span className="font-mono font-bold">
                  ${product.cogs.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-700 font-medium">Gross Profit</span>
                <span className="font-mono font-bold text-green-600">
                  ${profit.toFixed(2)}
                </span>
              </div>
            </div>
          </div>

          {/* Margins */}
          <div className="rounded-lg border bg-gray-50 p-4">
            <h4 className="mb-3 font-semibold text-gray-800">Margins</h4>
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Gross Margin</span>
                  <MarginIndicator margin={product.gross_margin} />
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-200">
                  <div
                    className="h-full bg-blue-500"
                    style={{ width: `${Math.min(product.gross_margin * 100, 100)}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Net Margin</span>
                  <MarginIndicator margin={product.net_margin} />
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-200">
                  <div
                    className="h-full bg-green-500"
                    style={{ width: `${Math.min(product.net_margin * 100, 100)}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  After fees, refunds, chargebacks
                </p>
              </div>
            </div>
          </div>

          {/* Ad Economics */}
          <div className="rounded-lg border bg-gray-50 p-4">
            <h4 className="mb-3 font-semibold text-gray-800">
              Advertising Analysis
            </h4>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Est. CPC (Google Ads)</span>
                <span className="font-mono font-bold">
                  ${product.estimated_cpc.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Max Affordable CPC</span>
                <span className="font-mono">
                  ${product.max_cpc.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between border-t pt-2">
                <span className="text-gray-700 font-medium">CPC Buffer</span>
                <span
                  className={`font-mono font-bold ${product.cpc_buffer >= 1.5 ? "text-green-600" : "text-red-600"}`}
                >
                  {product.cpc_buffer.toFixed(2)}x
                </span>
              </div>
              <p className="text-xs text-gray-500">
                {product.cpc_buffer >= 1.5
                  ? "✅ Room for CPC fluctuation"
                  : "❌ Too tight - risk of unprofitable ads"}
              </p>
              <div className="mt-2 border-t pt-2">
                <div className="flex justify-between">
                  <span className="text-gray-600">Est. Ad Cost per Sale</span>
                  <span className="font-mono">
                    ${adCostPerSale.toFixed(2)}
                  </span>
                </div>
                <p className="text-xs text-gray-500">
                  At 1% conversion rate
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Supplier & Logistics */}
        <div className="mb-6 grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border bg-gray-50 p-4">
            <h4 className="mb-3 font-semibold text-gray-800">
              Warehouse & Shipping
            </h4>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between items-center">
                <span className="text-gray-600">Warehouse Location</span>
                <WarehouseBadge country={product.warehouse_country} />
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Shipping Time</span>
                <span className="font-mono">
                  {product.shipping_days_min && product.shipping_days_max
                    ? `${product.shipping_days_min}-${product.shipping_days_max} days`
                    : "-"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Weight</span>
                <span className="font-mono">
                  {product.weight_grams ? `${product.weight_grams}g` : "-"}
                </span>
              </div>
              {product.warehouse_country === "CN" && (
                <div className="mt-2 rounded bg-amber-100 p-2 text-xs text-amber-800">
                  Ships from China - expect longer delivery times
                </div>
              )}
              {product.warehouse_country === "US" && (
                <div className="mt-2 rounded bg-green-100 p-2 text-xs text-green-800">
                  Ships from US - fast domestic delivery
                </div>
              )}
            </div>
          </div>

          <div className="rounded-lg border bg-gray-50 p-4">
            <h4 className="mb-3 font-semibold text-gray-800">
              Supplier Info
            </h4>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Supplier</span>
                <span className="font-medium">
                  {product.supplier_name || product.source.toUpperCase()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Available Stock</span>
                <span className={`font-mono font-bold ${
                  product.inventory_count && product.inventory_count > 100 ? "text-green-600" : "text-amber-600"
                }`}>
                  {product.inventory_count?.toLocaleString() || "-"}
                </span>
              </div>
              {product.source_url && (
                <div className="mt-2 border-t pt-2">
                  <a
                    href={product.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline text-xs"
                    onClick={(e) => e.stopPropagation()}
                  >
                    View on {product.source.toUpperCase()} →
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Point Breakdown */}
        {product.point_breakdown && Object.keys(product.point_breakdown).length > 0 && (
          <div className="mb-6">
            <h4 className="mb-3 font-semibold text-gray-800">Score Breakdown</h4>
            <div className="grid gap-2 md:grid-cols-4">
              {Object.entries(product.point_breakdown).map(([key, value]) => (
                <div
                  key={key}
                  className="flex items-center justify-between rounded-lg border bg-white p-3"
                >
                  <span className="text-sm text-gray-600">
                    {key.replace(/_/g, " ")}
                  </span>
                  <span className="font-mono font-bold text-blue-600">
                    +{value}
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-2 flex justify-end">
              <div className="rounded-lg bg-blue-100 px-4 py-2">
                <span className="text-sm text-blue-800">Total Points: </span>
                <span className="font-mono text-lg font-bold text-blue-900">
                  {product.points}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Ad Campaign Projections */}
        <div className="mb-6 rounded-lg border bg-amber-50 p-4">
          <h4 className="mb-3 font-semibold text-amber-800">
            Ad Campaign Projections (at 1% CVR)
          </h4>
          <div className="grid gap-4 text-sm md:grid-cols-3">
            <div>
              <div className="text-gray-600">Clicks needed per sale</div>
              <div className="text-2xl font-bold text-amber-700">100</div>
              <div className="text-xs text-gray-500">1% of visitors buy</div>
            </div>
            <div>
              <div className="text-gray-600">Ad cost per sale</div>
              <div className="text-2xl font-bold text-amber-700">
                ${(product.estimated_cpc * 100).toFixed(2)}
              </div>
              <div className="text-xs text-gray-500">
                100 clicks × ${product.estimated_cpc.toFixed(2)} CPC
              </div>
            </div>
            <div>
              <div className="text-gray-600">Profit after ads</div>
              <div
                className={`text-2xl font-bold ${
                  profit - product.estimated_cpc * 100 > 0
                    ? "text-green-600"
                    : "text-red-600"
                }`}
              >
                ${(profit - product.estimated_cpc * 100).toFixed(2)}
              </div>
              <div className="text-xs text-gray-500">
                ${profit.toFixed(2)} gross profit − ${(product.estimated_cpc * 100).toFixed(2)} ads
              </div>
            </div>
          </div>
          <div className="mt-3 rounded bg-amber-100 p-2 text-xs text-amber-800">
            <strong>Note:</strong> CVR (Conversion Rate) of 1% is typical for cold traffic.
            Warm/retargeting traffic can hit 2-5%. These projections assume cold traffic.
          </div>
        </div>

        {/* Rank Score Explanation */}
        {product.rank_score && (
          <div className="mb-6 rounded-lg border bg-blue-50 p-4">
            <h4 className="mb-2 font-semibold text-blue-800">Rank Score Calculation</h4>
            <div className="text-sm text-blue-700">
              <code className="rounded bg-blue-100 px-2 py-1">
                Rank Score = Points × 0.6 + CPC Buffer × 25
              </code>
              <p className="mt-2">
                = {product.points} × 0.6 + {product.cpc_buffer.toFixed(2)} × 25 ={" "}
                <strong>{product.rank_score.toFixed(2)}</strong>
              </p>
            </div>
          </div>
        )}

        {/* Key Terms & Notes */}
        <div className="mb-6 rounded-lg border bg-gray-100 p-4">
          <h4 className="mb-3 font-semibold text-gray-800">Key Terms</h4>
          <div className="grid gap-x-6 gap-y-2 text-sm md:grid-cols-2">
            <div>
              <strong className="text-gray-700">CPC</strong>
              <span className="text-gray-600"> – Cost Per Click. What you pay each time someone clicks your ad.</span>
            </div>
            <div>
              <strong className="text-gray-700">COGS</strong>
              <span className="text-gray-600"> – Cost of Goods Sold. Product cost + shipping cost.</span>
            </div>
            <div>
              <strong className="text-gray-700">AOV</strong>
              <span className="text-gray-600"> – Average Order Value. The selling price per order.</span>
            </div>
            <div>
              <strong className="text-gray-700">CVR</strong>
              <span className="text-gray-600"> – Conversion Rate. % of visitors who buy (typically 1%).</span>
            </div>
            <div>
              <strong className="text-gray-700">Max CPC</strong>
              <span className="text-gray-600"> – Maximum you can pay per click and remain profitable.</span>
            </div>
            <div>
              <strong className="text-gray-700">CPC Buffer</strong>
              <span className="text-gray-600"> – Safety margin: Max CPC ÷ Estimated CPC.</span>
            </div>
          </div>

          <div className="mt-4 border-t border-gray-200 pt-4">
            <h5 className="mb-2 font-semibold text-gray-700">About CPC Buffer</h5>
            <p className="text-sm text-gray-600">
              CPC Buffer measures how much room you have before ads become unprofitable.
              This product's <strong>{product.cpc_buffer.toFixed(2)}x buffer</strong> means
              CPC could increase {((product.cpc_buffer - 1) * 100).toFixed(0)}% before you'd lose money.
            </p>
            <div className="mt-2 text-sm text-gray-600">
              <div className="font-medium">Calculation:</div>
              <code className="text-xs">
                Buffer = Max CPC ÷ Est. CPC = ${product.max_cpc.toFixed(2)} ÷ ${product.estimated_cpc.toFixed(2)} = {product.cpc_buffer.toFixed(2)}x
              </code>
            </div>
            <ul className="mt-3 space-y-1 text-sm text-gray-600">
              <li className={product.cpc_buffer < 1 ? "font-bold text-red-600" : ""}>
                • <strong>&lt; 1.0x</strong> – Already unprofitable (CPC exceeds what you can afford)
              </li>
              <li className={product.cpc_buffer >= 1 && product.cpc_buffer < 1.5 ? "font-bold text-amber-600" : ""}>
                • <strong>1.0–1.5x</strong> – Risky (small CPC spike wipes out profit)
              </li>
              <li className={product.cpc_buffer >= 1.5 ? "font-bold text-green-600" : ""}>
                • <strong>1.5x+</strong> – Safe (room for competition & seasonal fluctuations)
              </li>
            </ul>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 border-t pt-4">
          <button
            onClick={onClose}
            className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-gray-50"
          >
            Close
          </button>
          <button
            onClick={() => {
              onReject(product.id);
              onClose();
            }}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Reject Product
          </button>
          <button
            onClick={() => {
              onApprove(product.id);
              onClose();
            }}
            className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
          >
            Approve for Storefront
          </button>
        </div>
      </Card>
    </div>
  );
}

function ProductRow({
  product,
  onSelect,
  onApprove,
  onReject,
}: {
  product: ScoredProduct;
  onSelect: (id: string) => void;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
  const shippingDays = product.shipping_days_min && product.shipping_days_max
    ? `${product.shipping_days_min}-${product.shipping_days_max}d`
    : "-";

  return (
    <tr
      className="cursor-pointer border-b hover:bg-gray-50"
      onClick={() => onSelect(product.id)}
    >
      <td className="px-4 py-3">
        <div className="max-w-xs truncate font-medium" title={product.name}>
          {product.name}
        </div>
        <div className="text-xs text-gray-500">{product.category}</div>
      </td>
      <td className="px-4 py-3 text-right">
        <RecommendationBadge rec={product.recommendation} />
      </td>
      <td className="px-4 py-3 text-right font-mono">
        {product.rank_score?.toFixed(1) || "-"}
      </td>
      <td className="px-4 py-3 text-right">
        <MarginIndicator margin={product.net_margin} />
      </td>
      <td className="px-4 py-3 text-right font-mono">
        ${product.selling_price.toFixed(2)}
      </td>
      <td className="px-4 py-3 text-center">
        <WarehouseBadge country={product.warehouse_country} />
        <div className="text-xs text-gray-500 mt-0.5">{shippingDays}</div>
      </td>
      <td className="px-4 py-3 text-right font-mono text-gray-600">
        {product.inventory_count?.toLocaleString() || "-"}
      </td>
      <td className="px-4 py-3">
        <div className="flex gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onApprove(product.id);
            }}
            className="rounded bg-green-600 px-3 py-1 text-sm font-medium text-white hover:bg-green-700"
          >
            Approve
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onReject(product.id);
            }}
            className="rounded bg-red-600 px-3 py-1 text-sm font-medium text-white hover:bg-red-700"
          >
            Reject
          </button>
        </div>
      </td>
    </tr>
  );
}

export default function AdminPage() {
  const [products, setProducts] = useState<ScoredProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("");
  const [total, setTotal] = useState(0);
  const [actionMessage, setActionMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showDiscover, setShowDiscover] = useState(false);
  const [settings, setSettings] = useState<ScoringSettings | null>(null);
  const [selectedProduct, setSelectedProduct] = useState<ScoredProductFull | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [discovering, setDiscovering] = useState(false);

  const loadProducts = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await getScoredProducts({
        recommendation: filter || undefined,
        limit: 50,
      });
      setProducts(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load products");
    } finally {
      setLoading(false);
    }
  };

  const loadSettings = async () => {
    try {
      const s = await getScoringSettings();
      setSettings(s);
    } catch (err) {
      console.error("Failed to load settings:", err);
    }
  };

  useEffect(() => {
    loadProducts();
    loadSettings();
  }, [filter]);

  const handleOpenSettings = async () => {
    await loadSettings();
    setShowSettings(true);
  };

  const handleUpdateSettings = async (newSettings: Partial<ScoringSettings>) => {
    const updated = await updateScoringSettings(newSettings);
    setSettings(updated);
    setActionMessage({ type: "success", text: "Settings saved! Re-run Discover to apply." });
    setTimeout(() => setActionMessage(null), 4000);
  };

  const handleSelectProduct = async (id: string) => {
    setLoadingDetail(true);
    try {
      const product = await getScoredProduct(id);
      setSelectedProduct(product);
    } catch (err) {
      setActionMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to load product details",
      });
      setTimeout(() => setActionMessage(null), 3000);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleSeedDemo = async () => {
    setSeeding(true);
    setDiscovering(true);
    try {
      const result = await seedDemoProducts(25);
      setActionMessage({ type: "success", text: result.message });
      loadProducts();
    } catch (err) {
      setActionMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to seed products",
      });
    } finally {
      setSeeding(false);
      setDiscovering(false);
    }
    setTimeout(() => setActionMessage(null), 5000);
  };

  const handleDiscoverFromCJ = async (keywords: string[], limit: number) => {
    setDiscovering(true);
    try {
      const result = await discoverProducts({
        keywords,
        limit_per_keyword: limit,
      });
      setActionMessage({ type: "success", text: result.message });
      loadProducts();
    } catch (err) {
      setActionMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to discover products",
      });
    } finally {
      setDiscovering(false);
    }
    setTimeout(() => setActionMessage(null), 5000);
  };

  const handleClearAll = async () => {
    if (!confirm("Are you sure you want to clear ALL scored products?")) return;
    try {
      await clearScoredProducts();
      setActionMessage({ type: "success", text: "All scored products cleared" });
      loadProducts();
    } catch (err) {
      setActionMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to clear products",
      });
    }
    setTimeout(() => setActionMessage(null), 3000);
  };

  const handleApprove = async (id: string) => {
    try {
      const result = await approveProduct(id);
      setActionMessage({ type: "success", text: result.message });
      setProducts((prev) => prev.filter((p) => p.id !== id));
      setTotal((prev) => prev - 1);
      setSelectedProduct(null);
    } catch (err) {
      setActionMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to approve",
      });
    }
    setTimeout(() => setActionMessage(null), 3000);
  };

  const handleReject = async (id: string) => {
    if (!confirm("Are you sure you want to reject this product?")) return;
    try {
      await rejectProduct(id);
      setActionMessage({ type: "success", text: "Product rejected" });
      setProducts((prev) => prev.filter((p) => p.id !== id));
      setTotal((prev) => prev - 1);
      setSelectedProduct(null);
    } catch (err) {
      setActionMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to reject",
      });
    }
    setTimeout(() => setActionMessage(null), 3000);
  };

  return (
    <main className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="border-b bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Arbitrage Dashboard
            </h1>
            <p className="text-sm text-gray-500">
              Review and approve products for the storefront
            </p>
          </div>
          <div className="flex items-center gap-4">
            <Link
              href="/admin/crawl"
              className="flex items-center gap-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Crawl Management
            </Link>
            <button
              onClick={handleOpenSettings}
              className="flex items-center gap-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Settings
            </button>
            <Link
              href="/"
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline"
            >
              View Storefront
            </Link>
          </div>
        </div>
      </header>

      {/* Settings Modal */}
      {showSettings && settings && (
        <SettingsPanel
          settings={settings}
          onUpdate={handleUpdateSettings}
          onClose={() => setShowSettings(false)}
        />
      )}

      {/* Discover Modal */}
      {showDiscover && (
        <DiscoverPanel
          onDiscover={handleDiscoverFromCJ}
          onSeedDemo={handleSeedDemo}
          onClose={() => setShowDiscover(false)}
          discovering={discovering}
        />
      )}

      {/* Product Detail Modal */}
      {selectedProduct && (
        <ProductDetailModal
          product={selectedProduct}
          onClose={() => setSelectedProduct(null)}
          onApprove={handleApprove}
          onReject={handleReject}
        />
      )}

      {/* Loading Detail Overlay */}
      {loadingDetail && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="rounded-lg bg-white p-6 shadow-xl">
            <div className="text-gray-600">Loading product details...</div>
          </div>
        </div>
      )}

      {/* Action Message */}
      {actionMessage && (
        <div
          className={`mx-auto mt-4 max-w-7xl px-4 ${
            actionMessage.type === "success" ? "text-green-600" : "text-red-600"
          }`}
        >
          <div
            className={`rounded-lg p-3 ${
              actionMessage.type === "success" ? "bg-green-50" : "bg-red-50"
            }`}
          >
            {actionMessage.text}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="mx-auto max-w-7xl px-4 py-4">
        <Card className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            <label className="text-sm font-medium text-gray-700">
              Filter by Recommendation:
            </label>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="">All</option>
              {RECOMMENDATIONS.map((rec) => (
                <option key={rec} value={rec}>
                  {rec}
                </option>
              ))}
            </select>
            <span className="text-sm text-gray-500">
              Showing {products.length} of {total} products
            </span>
            <div className="ml-auto flex gap-2">
              <button
                onClick={() => setShowDiscover(true)}
                disabled={discovering}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {discovering ? "Discovering..." : "Discover Products"}
              </button>
              <button
                onClick={handleClearAll}
                className="rounded-md bg-gray-200 px-4 py-2 text-sm font-medium hover:bg-gray-300"
              >
                Clear All
              </button>
              <button
                onClick={loadProducts}
                className="rounded-md bg-gray-200 px-4 py-2 text-sm font-medium hover:bg-gray-300"
              >
                Refresh
              </button>
            </div>
          </div>
        </Card>
      </div>

      {/* Products Table */}
      <div className="mx-auto max-w-7xl px-4 pb-8">
        <Card className="overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-gray-500">
              Loading products...
            </div>
          ) : error ? (
            <div className="p-8 text-center text-red-600">
              {error}
              <button
                onClick={loadProducts}
                className="ml-4 text-blue-600 underline"
              >
                Retry
              </button>
            </div>
          ) : products.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              No products found
              {filter && " for this filter"}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 text-left text-sm font-medium text-gray-600">
                  <tr>
                    <th className="px-4 py-3">Product</th>
                    <th className="px-4 py-3 text-right">Recommendation</th>
                    <th className="px-4 py-3 text-right">Rank</th>
                    <th className="px-4 py-3 text-right">Net Margin</th>
                    <th className="px-4 py-3 text-right">Price</th>
                    <th className="px-4 py-3 text-center">Warehouse</th>
                    <th className="px-4 py-3 text-right">Stock</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((product) => (
                    <ProductRow
                      key={product.id}
                      product={product}
                      onSelect={handleSelectProduct}
                      onApprove={handleApprove}
                      onReject={handleReject}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </main>
  );
}
