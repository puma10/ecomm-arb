"use client";

import { useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { scanProductUrl, ScannedProduct } from "@/lib/api";

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

function SupplierBadge({ source }: { source: string }) {
  const colors: Record<string, string> = {
    cj: "bg-purple-100 text-purple-800 border-purple-300",
    aliexpress: "bg-orange-100 text-orange-800 border-orange-300",
    amazon: "bg-yellow-100 text-yellow-800 border-yellow-300",
    temu: "bg-pink-100 text-pink-800 border-pink-300",
    ebay: "bg-blue-100 text-blue-800 border-blue-300",
  };

  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-xs font-semibold uppercase ${colors[source] || "bg-gray-100 text-gray-800"}`}
    >
      {source}
    </span>
  );
}

function WarehouseBadge({ country }: { country: string | null }) {
  if (!country) return <span className="text-xs text-gray-400">Unknown</span>;
  const colors: Record<string, string> = {
    US: "bg-green-100 text-green-800",
    CN: "bg-amber-100 text-amber-800",
  };
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${colors[country] || "bg-gray-100 text-gray-700"}`}
    >
      {country}
    </span>
  );
}

export default function ScannerPage() {
  const [url, setUrl] = useState("");
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScannedProduct | null>(null);

  // Editable form fields (populated from scan result)
  const [formName, setFormName] = useState("");
  const [formSlug, setFormSlug] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formPrice, setFormPrice] = useState("");
  const [formCompareAt, setFormCompareAt] = useState("");
  const [formCost, setFormCost] = useState("");
  const [formShipMin, setFormShipMin] = useState("7");
  const [formShipMax, setFormShipMax] = useState("14");

  const [creating, setCreating] = useState(false);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);

  async function handleScan() {
    if (!url.trim()) return;

    setScanning(true);
    setError(null);
    setResult(null);
    setCreateSuccess(null);

    try {
      const data = await scanProductUrl(url.trim());
      setResult(data);

      // Pre-fill form
      setFormName(data.name);
      setFormSlug(slugify(data.name));
      setFormDescription(data.description);
      setFormPrice(data.suggested_price.toFixed(2));
      setFormCompareAt("");
      setFormCost(data.cost.toFixed(2));
      setFormShipMin(String(data.shipping_days_min));
      setFormShipMax(String(data.shipping_days_max));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  async function handleCreate() {
    if (!result) return;

    setCreating(true);
    setError(null);

    try {
      const API_URL =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:6025/api";

      const body = {
        slug: formSlug,
        name: formName,
        description: formDescription,
        price: formPrice,
        compare_at_price: formCompareAt || null,
        cost: formCost,
        images: result.images,
        supplier_source: result.supplier_source,
        supplier_sku: result.supplier_sku,
        supplier_url: result.supplier_url,
        shipping_cost: "0",
        shipping_days_min: parseInt(formShipMin) || 7,
        shipping_days_max: parseInt(formShipMax) || 14,
      };

      const res = await fetch(`${API_URL}/products`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to create product");
      }

      const product = await res.json();
      setCreateSuccess(product.slug);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Product Scanner</h1>
          <p className="text-sm text-gray-500">
            Paste a supplier URL to extract product details
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/admin">
            <Button variant="outline" size="sm">
              Dashboard
            </Button>
          </Link>
          <Link href="/admin/crawl">
            <Button variant="outline" size="sm">
              Crawl
            </Button>
          </Link>
        </div>
      </div>

      {/* URL Input */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex gap-3">
            <div className="flex-1">
              <Input
                placeholder="https://cjdropshipping.com/product/..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleScan()}
                disabled={scanning}
              />
            </div>
            <Button onClick={handleScan} disabled={scanning || !url.trim()}>
              {scanning ? (
                <>
                  <span className="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Scanning...
                </>
              ) : (
                "Scan URL"
              )}
            </Button>
          </div>
          <p className="mt-2 text-xs text-gray-400">
            Supported: CJ Dropshipping. More suppliers coming soon.
          </p>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Success */}
      {createSuccess && (
        <div className="mb-6 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          Product created!{" "}
          <Link
            href={`/p/${createSuccess}`}
            className="font-medium underline"
          >
            View product
          </Link>
        </div>
      )}

      {/* Scan Results */}
      {result && (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Left: Extracted Info */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Extracted Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Images */}
              {result.images.length > 0 && (
                <div>
                  <Label className="text-xs text-gray-500">
                    Images ({result.images.length})
                  </Label>
                  <div className="mt-1 flex gap-2 overflow-x-auto pb-2">
                    {result.images.slice(0, 6).map((img, i) => (
                      <img
                        key={i}
                        src={img}
                        alt={`Product ${i + 1}`}
                        className="h-20 w-20 flex-shrink-0 rounded border object-cover"
                      />
                    ))}
                    {result.images.length > 6 && (
                      <div className="flex h-20 w-20 flex-shrink-0 items-center justify-center rounded border bg-gray-50 text-xs text-gray-500">
                        +{result.images.length - 6}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Metadata grid */}
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-xs text-gray-500">Supplier</span>
                  <div className="mt-0.5">
                    <SupplierBadge source={result.supplier_source} />
                    {result.supplier_name && (
                      <span className="ml-2 text-gray-600">
                        {result.supplier_name}
                      </span>
                    )}
                  </div>
                </div>
                <div>
                  <span className="text-xs text-gray-500">SKU</span>
                  <div className="mt-0.5 font-mono text-xs">
                    {result.supplier_sku || "-"}
                  </div>
                </div>
                <div>
                  <span className="text-xs text-gray-500">Warehouse</span>
                  <div className="mt-0.5">
                    <WarehouseBadge country={result.warehouse_country} />
                  </div>
                </div>
                <div>
                  <span className="text-xs text-gray-500">Inventory</span>
                  <div className="mt-0.5">
                    {result.inventory_count != null
                      ? result.inventory_count.toLocaleString()
                      : "-"}
                  </div>
                </div>
                <div>
                  <span className="text-xs text-gray-500">Weight</span>
                  <div className="mt-0.5">
                    {result.weight_grams
                      ? `${result.weight_grams}g`
                      : "-"}
                  </div>
                </div>
                <div>
                  <span className="text-xs text-gray-500">Variants</span>
                  <div className="mt-0.5">{result.variants_count}</div>
                </div>
                {result.categories.length > 0 && (
                  <div className="col-span-2">
                    <span className="text-xs text-gray-500">Categories</span>
                    <div className="mt-0.5 flex flex-wrap gap-1">
                      {result.categories.map((cat, i) => (
                        <span
                          key={i}
                          className="rounded bg-gray-100 px-1.5 py-0.5 text-xs"
                        >
                          {cat}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Pricing summary */}
              <div className="rounded-lg bg-gray-50 p-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">Supplier Cost</span>
                  <span className="font-mono font-bold">
                    ${result.cost.toFixed(2)}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between text-sm">
                  <span className="text-gray-600">Suggested Price</span>
                  <span className="font-mono font-bold text-green-700">
                    ${result.suggested_price.toFixed(2)}
                  </span>
                </div>
                {result.cost > 0 && (
                  <div className="mt-1 flex items-center justify-between text-sm">
                    <span className="text-gray-600">Margin</span>
                    <span className="font-mono text-blue-700">
                      {(
                        ((result.suggested_price - result.cost) /
                          result.suggested_price) *
                        100
                      ).toFixed(0)}
                      %
                    </span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Right: Product Creation Form */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Create Product</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  value={formName}
                  onChange={(e) => {
                    setFormName(e.target.value);
                    setFormSlug(slugify(e.target.value));
                  }}
                />
              </div>

              <div>
                <Label htmlFor="slug">Slug</Label>
                <Input
                  id="slug"
                  value={formSlug}
                  onChange={(e) => setFormSlug(e.target.value)}
                  className="font-mono text-sm"
                />
              </div>

              <div>
                <Label htmlFor="description">Description</Label>
                <textarea
                  id="description"
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  rows={3}
                  className="border-input w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label htmlFor="price">Price ($)</Label>
                  <Input
                    id="price"
                    type="number"
                    step="0.01"
                    value={formPrice}
                    onChange={(e) => setFormPrice(e.target.value)}
                    className="font-mono"
                  />
                </div>
                <div>
                  <Label htmlFor="compareAt">Compare At ($)</Label>
                  <Input
                    id="compareAt"
                    type="number"
                    step="0.01"
                    value={formCompareAt}
                    onChange={(e) => setFormCompareAt(e.target.value)}
                    className="font-mono"
                    placeholder="Optional"
                  />
                </div>
                <div>
                  <Label htmlFor="cost">Cost ($)</Label>
                  <Input
                    id="cost"
                    type="number"
                    step="0.01"
                    value={formCost}
                    onChange={(e) => setFormCost(e.target.value)}
                    className="font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label htmlFor="shipMin">Ship Days (Min)</Label>
                  <Input
                    id="shipMin"
                    type="number"
                    value={formShipMin}
                    onChange={(e) => setFormShipMin(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="shipMax">Ship Days (Max)</Label>
                  <Input
                    id="shipMax"
                    type="number"
                    value={formShipMax}
                    onChange={(e) => setFormShipMax(e.target.value)}
                  />
                </div>
              </div>

              {/* Margin preview */}
              {parseFloat(formPrice) > 0 && parseFloat(formCost) > 0 && (
                <div className="rounded bg-gray-50 px-3 py-2 text-sm">
                  <span className="text-gray-500">Margin: </span>
                  <span
                    className={`font-mono font-bold ${
                      (parseFloat(formPrice) - parseFloat(formCost)) /
                        parseFloat(formPrice) >=
                      0.5
                        ? "text-green-700"
                        : (parseFloat(formPrice) - parseFloat(formCost)) /
                              parseFloat(formPrice) >=
                            0.3
                          ? "text-blue-700"
                          : "text-red-700"
                    }`}
                  >
                    {(
                      ((parseFloat(formPrice) - parseFloat(formCost)) /
                        parseFloat(formPrice)) *
                      100
                    ).toFixed(1)}
                    %
                  </span>
                  <span className="ml-2 text-gray-400">
                    (${(parseFloat(formPrice) - parseFloat(formCost)).toFixed(2)}{" "}
                    profit)
                  </span>
                </div>
              )}

              <Button
                onClick={handleCreate}
                disabled={creating || !formName || !formSlug || !formPrice}
                className="w-full"
              >
                {creating ? "Creating..." : "Create Product"}
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
