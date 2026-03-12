"use client";

import { useState } from "react";
import Link from "next/link";
import {
  calculateProfit,
  type ProfitCalculatorInput,
  type ProfitCalculatorResult,
} from "@/lib/api";

const defaultInput: ProfitCalculatorInput = {
  product_cost: 15,
  selling_price: 49.99,
  shipping_cost: 5,
  ad_spend_monthly: 500,
  cpc: 0.5,
  cvr: 0.02,
  payment_fee_rate: 0.03,
  refund_rate: 0.08,
  fixed_costs_monthly: 0,
};

function InputField({
  label,
  name,
  value,
  onChange,
  prefix,
  suffix,
  step,
  min,
  helpText,
}: {
  label: string;
  name: string;
  value: number;
  onChange: (name: string, value: number) => void;
  prefix?: string;
  suffix?: string;
  step?: string;
  min?: string;
  helpText?: string;
}) {
  return (
    <div>
      <label
        htmlFor={name}
        className="block text-sm font-medium text-gray-700 mb-1"
      >
        {label}
      </label>
      <div className="relative">
        {prefix && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm">
            {prefix}
          </span>
        )}
        <input
          id={name}
          type="number"
          value={value}
          onChange={(e) => onChange(name, parseFloat(e.target.value) || 0)}
          step={step || "0.01"}
          min={min || "0"}
          className={`w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 ${
            prefix ? "pl-7" : ""
          } ${suffix ? "pr-8" : ""}`}
        />
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm">
            {suffix}
          </span>
        )}
      </div>
      {helpText && <p className="mt-1 text-xs text-gray-500">{helpText}</p>}
    </div>
  );
}

function MetricCard({
  label,
  value,
  subtext,
  color,
}: {
  label: string;
  value: string;
  subtext?: string;
  color?: "green" | "red" | "blue" | "amber" | "gray";
}) {
  const colorClasses = {
    green: "bg-green-50 border-green-200 text-green-700",
    red: "bg-red-50 border-red-200 text-red-700",
    blue: "bg-blue-50 border-blue-200 text-blue-700",
    amber: "bg-amber-50 border-amber-200 text-amber-700",
    gray: "bg-gray-50 border-gray-200 text-gray-700",
  };
  const cls = colorClasses[color || "gray"];

  return (
    <div className={`rounded-lg border p-4 ${cls}`}>
      <p className="text-xs font-medium uppercase tracking-wide opacity-75">
        {label}
      </p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
      {subtext && <p className="mt-1 text-xs opacity-75">{subtext}</p>}
    </div>
  );
}

function fmt(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function CalculatorPage() {
  const [input, setInput] = useState<ProfitCalculatorInput>(defaultInput);
  const [result, setResult] = useState<ProfitCalculatorResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (name: string, value: number) => {
    setInput((prev) => ({ ...prev, [name]: value }));
  };

  const handleCalculate = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await calculateProfit(input);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Calculation failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b bg-white">
        <div className="mx-auto max-w-6xl px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Profit Calculator
            </h1>
            <p className="text-sm text-gray-500">
              Margin, break-even &amp; ROI analysis
            </p>
          </div>
          <Link
            href="/admin"
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            Back to Admin
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="grid gap-8 lg:grid-cols-5">
          {/* Input Form */}
          <div className="lg:col-span-2 space-y-6">
            {/* Product Costs */}
            <div className="rounded-xl border bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-4">
                Product Costs
              </h2>
              <div className="space-y-4">
                <InputField
                  label="Product Cost"
                  name="product_cost"
                  value={input.product_cost}
                  onChange={handleChange}
                  prefix="$"
                  helpText="What you pay the supplier"
                />
                <InputField
                  label="Selling Price"
                  name="selling_price"
                  value={input.selling_price}
                  onChange={handleChange}
                  prefix="$"
                  helpText="What the customer pays"
                />
                <InputField
                  label="Shipping Cost"
                  name="shipping_cost"
                  value={input.shipping_cost}
                  onChange={handleChange}
                  prefix="$"
                  helpText="Shipping cost per unit"
                />
              </div>
            </div>

            {/* Advertising */}
            <div className="rounded-xl border bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-4">
                Advertising
              </h2>
              <div className="space-y-4">
                <InputField
                  label="Monthly Ad Spend"
                  name="ad_spend_monthly"
                  value={input.ad_spend_monthly}
                  onChange={handleChange}
                  prefix="$"
                />
                <InputField
                  label="Cost Per Click (CPC)"
                  name="cpc"
                  value={input.cpc}
                  onChange={handleChange}
                  prefix="$"
                />
                <InputField
                  label="Conversion Rate"
                  name="cvr"
                  value={input.cvr}
                  onChange={handleChange}
                  suffix="%"
                  step="0.001"
                  helpText="As decimal: 0.02 = 2%"
                />
              </div>
            </div>

            {/* Fees & Overheads */}
            <div className="rounded-xl border bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-4">
                Fees &amp; Overheads
              </h2>
              <div className="space-y-4">
                <InputField
                  label="Payment Fee Rate"
                  name="payment_fee_rate"
                  value={input.payment_fee_rate}
                  onChange={handleChange}
                  step="0.001"
                  helpText="As decimal: 0.03 = 3% (Stripe/PayPal)"
                />
                <InputField
                  label="Refund Rate"
                  name="refund_rate"
                  value={input.refund_rate}
                  onChange={handleChange}
                  step="0.001"
                  helpText="As decimal: 0.08 = 8%"
                />
                <InputField
                  label="Monthly Fixed Costs"
                  name="fixed_costs_monthly"
                  value={input.fixed_costs_monthly}
                  onChange={handleChange}
                  prefix="$"
                  helpText="Tools, subscriptions, etc."
                />
              </div>
            </div>

            <button
              onClick={handleCalculate}
              disabled={loading}
              className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {loading ? "Calculating..." : "Calculate Profit"}
            </button>

            {error && (
              <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                {error}
              </div>
            )}
          </div>

          {/* Results */}
          <div className="lg:col-span-3 space-y-6">
            {!result ? (
              <div className="rounded-xl border bg-white p-12 text-center shadow-sm">
                <div className="text-gray-400 text-4xl mb-3">
                  &#x1f4ca;
                </div>
                <p className="text-gray-500 text-sm">
                  Enter your product details and click Calculate to see the
                  profitability analysis.
                </p>
              </div>
            ) : (
              <>
                {/* Summary Metrics */}
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <MetricCard
                    label="Net Margin"
                    value={`${result.profit.net_margin_pct}%`}
                    color={
                      result.profit.net_margin_pct >= 50
                        ? "green"
                        : result.profit.net_margin_pct >= 30
                          ? "blue"
                          : result.profit.net_margin_pct >= 0
                            ? "amber"
                            : "red"
                    }
                  />
                  <MetricCard
                    label="Profit / Unit"
                    value={`$${fmt(result.profit.net_profit_per_unit)}`}
                    color={
                      result.profit.net_profit_per_unit > 0 ? "green" : "red"
                    }
                  />
                  <MetricCard
                    label="ROI"
                    value={`${result.roi_pct}%`}
                    subtext="per unit invested"
                    color={result.roi_pct > 0 ? "blue" : "red"}
                  />
                  <MetricCard
                    label="Max CPC"
                    value={`$${fmt(result.max_cpc)}`}
                    subtext="break-even CPC"
                    color={
                      result.max_cpc > input.cpc
                        ? "green"
                        : result.max_cpc > 0
                          ? "amber"
                          : "red"
                    }
                  />
                </div>

                {/* Profit Breakdown */}
                <div className="rounded-xl border bg-white p-6 shadow-sm">
                  <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-4">
                    Per-Unit Profit Breakdown
                  </h2>
                  <div className="space-y-3">
                    <Row
                      label="Revenue (selling price)"
                      value={`$${fmt(result.profit.revenue)}`}
                    />
                    <Row
                      label="COGS (product + shipping)"
                      value={`-$${fmt(result.profit.cogs)}`}
                      negative
                    />
                    <Divider />
                    <Row
                      label="Gross Profit"
                      value={`$${fmt(result.profit.gross_profit)}`}
                      bold
                      sub={`${result.profit.gross_margin_pct}% margin`}
                    />
                    <Row
                      label="Payment Fees"
                      value={`-$${fmt(result.profit.payment_fees)}`}
                      negative
                    />
                    <Row
                      label="Refund Cost"
                      value={`-$${fmt(result.profit.refund_cost)}`}
                      negative
                    />
                    <Divider />
                    <Row
                      label="Net Profit"
                      value={`$${fmt(result.profit.net_profit_per_unit)}`}
                      bold
                      highlight={result.profit.net_profit_per_unit > 0}
                      sub={`${result.profit.net_margin_pct}% margin`}
                    />
                  </div>
                </div>

                {/* Ad Metrics */}
                {result.ads && (
                  <div className="rounded-xl border bg-white p-6 shadow-sm">
                    <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-4">
                      Advertising Metrics
                    </h2>
                    <div className="space-y-3">
                      <Row
                        label="Cost Per Acquisition (CPA)"
                        value={`$${fmt(result.ads.cost_per_acquisition)}`}
                      />
                      <Row
                        label="Clicks Per Sale"
                        value={result.ads.clicks_per_sale.toFixed(0)}
                      />
                      <Row
                        label="Monthly Clicks"
                        value={result.ads.monthly_clicks.toLocaleString()}
                      />
                      <Row
                        label="Monthly Sales (from ads)"
                        value={result.ads.monthly_sales_from_ads.toFixed(1)}
                      />
                      {result.ads.roas !== null && (
                        <Row
                          label="ROAS"
                          value={`${result.ads.roas}x`}
                          sub={
                            result.ads.roas >= 3
                              ? "Excellent"
                              : result.ads.roas >= 2
                                ? "Good"
                                : result.ads.roas >= 1
                                  ? "Break-even"
                                  : "Losing money"
                          }
                        />
                      )}
                      <Divider />
                      <Row
                        label="Profit After Ads (per unit)"
                        value={`$${fmt(result.ads.profit_after_ads_per_unit)}`}
                        bold
                        highlight={result.ads.ad_profitable}
                      />
                      <div className="mt-2">
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            result.ads.ad_profitable
                              ? "bg-green-100 text-green-800"
                              : "bg-red-100 text-red-800"
                          }`}
                        >
                          {result.ads.ad_profitable
                            ? "Ads are profitable"
                            : "Ads are NOT profitable"}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Break-Even */}
                <div className="rounded-xl border bg-white p-6 shadow-sm">
                  <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-4">
                    Break-Even Analysis
                  </h2>
                  {result.break_even.break_even_units < 0 ? (
                    <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
                      Cannot break even — each unit sold loses money after
                      accounting for all costs.
                    </div>
                  ) : result.break_even.break_even_units === 0 ? (
                    <div className="rounded-lg bg-green-50 border border-green-200 p-4 text-sm text-green-700">
                      No fixed costs to cover — every unit sold is profitable.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <Row
                        label="Monthly Fixed Costs"
                        value={`$${fmt(result.break_even.monthly_fixed_costs)}`}
                      />
                      <Divider />
                      <Row
                        label="Break-Even Units"
                        value={result.break_even.break_even_units.toLocaleString()}
                        bold
                        sub="units per month to cover costs"
                      />
                      <Row
                        label="Break-Even Revenue"
                        value={`$${fmt(result.break_even.break_even_revenue)}`}
                        sub="monthly revenue at break-even"
                      />
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

function Row({
  label,
  value,
  negative,
  bold,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  negative?: boolean;
  bold?: boolean;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <span
          className={`text-sm ${bold ? "font-semibold text-gray-900" : "text-gray-600"}`}
        >
          {label}
        </span>
        {sub && <span className="ml-2 text-xs text-gray-400">{sub}</span>}
      </div>
      <span
        className={`text-sm font-mono ${
          bold ? "font-semibold" : ""
        } ${
          highlight === true
            ? "text-green-600"
            : highlight === false
              ? "text-red-600"
              : negative
                ? "text-red-500"
                : "text-gray-900"
        }`}
      >
        {value}
      </span>
    </div>
  );
}

function Divider() {
  return <div className="border-t border-gray-100" />;
}
