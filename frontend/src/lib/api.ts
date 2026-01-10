/**
 * API client for backend communication.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:6025/api";

export interface Product {
  id: string;
  slug: string;
  name: string;
  description: string;
  price: number;
  compare_at_price: number | null;
  images: string[];
  shipping_days_min: number;
  shipping_days_max: number;
}

export interface ShippingAddress {
  first_name: string;
  last_name: string;
  address_line1: string;
  address_line2?: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
}

export interface CheckoutResponse {
  checkout_url: string;
  session_id: string;
}

export interface Order {
  id: string;
  order_number: string;
  status: string;
  quantity: number;
  subtotal: number;
  shipping_cost: number;
  total: number;
  shipping_address: ShippingAddress;
  tracking_number: string | null;
  tracking_url: string | null;
  created_at: string;
  paid_at: string | null;
  shipped_at: string | null;
  product: {
    name: string;
    images: string[];
  };
}

export interface ProductListResponse {
  items: Product[];
  total: number;
}

export async function getProducts(): Promise<ProductListResponse> {
  const res = await fetch(`${API_URL}/products`, {
    next: { revalidate: 60 }, // Cache for 1 minute
  });

  if (!res.ok) {
    throw new Error("Failed to fetch products");
  }

  const data = await res.json();
  return {
    items: data.items.map((item: Record<string, unknown>) => ({
      ...item,
      price: Number(item.price),
      compare_at_price: item.compare_at_price ? Number(item.compare_at_price) : null,
    })),
    total: data.total,
  };
}

export async function getProduct(slug: string): Promise<Product> {
  const res = await fetch(`${API_URL}/products/${slug}`, {
    next: { revalidate: 60 }, // Cache for 1 minute
  });

  if (!res.ok) {
    throw new Error("Product not found");
  }

  const data = await res.json();
  // Convert string prices to numbers
  return {
    ...data,
    price: Number(data.price),
    compare_at_price: data.compare_at_price ? Number(data.compare_at_price) : null,
  };
}

export async function createCheckoutSession(
  productSlug: string,
  email: string,
  shippingAddress: ShippingAddress,
  quantity: number = 1
): Promise<CheckoutResponse> {
  const res = await fetch(`${API_URL}/checkout/session`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      product_slug: productSlug,
      email,
      shipping_address: shippingAddress,
      quantity,
    }),
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Checkout failed");
  }

  return res.json();
}

export async function getOrder(orderId: string): Promise<Order> {
  const res = await fetch(`${API_URL}/orders/${orderId}`);

  if (!res.ok) {
    throw new Error("Order not found");
  }

  const data = await res.json();
  return {
    ...data,
    subtotal: Number(data.subtotal),
    shipping_cost: Number(data.shipping_cost),
    total: Number(data.total),
  };
}

export async function lookupOrder(
  email: string,
  orderNumber: string
): Promise<Order> {
  const res = await fetch(`${API_URL}/orders/lookup`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      order_number: orderNumber,
    }),
  });

  if (!res.ok) {
    throw new Error("Order not found");
  }

  return res.json();
}

// Admin API - Scored Products

export interface ScoredProduct {
  id: string;
  source_product_id: string;
  source: string;
  source_url: string | null;
  name: string;
  selling_price: number;
  category: string;
  cogs: number;
  gross_margin: number;
  net_margin: number;
  // Shipping/logistics
  weight_grams: number | null;
  shipping_days_min: number | null;
  shipping_days_max: number | null;
  warehouse_country: string | null;
  // Supplier
  supplier_name: string | null;
  inventory_count: number | null;
  // Scoring
  points: number | null;
  rank_score: number | null;
  recommendation: string;
  // Association
  crawl_job_id: string | null;
  created_at: string;
}

export interface ScoredProductListResponse {
  items: ScoredProduct[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApproveProductResponse {
  success: boolean;
  product_id: string;
  slug: string;
  message: string;
}

export async function getScoredProducts(params?: {
  recommendation?: string;
  crawl_job_id?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<ScoredProductListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.recommendation) searchParams.set("recommendation", params.recommendation);
  if (params?.crawl_job_id) searchParams.set("crawl_job_id", params.crawl_job_id);
  if (params?.search) searchParams.set("search", params.search);
  if (params?.limit) searchParams.set("limit", params.limit.toString());
  if (params?.offset) searchParams.set("offset", params.offset.toString());

  const url = `${API_URL}/products/scored${searchParams.toString() ? `?${searchParams}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });

  if (!res.ok) {
    throw new Error("Failed to fetch scored products");
  }

  const data = await res.json();
  return {
    ...data,
    items: data.items.map((item: Record<string, unknown>) => ({
      ...item,
      selling_price: Number(item.selling_price),
      cogs: Number(item.cogs),
      gross_margin: Number(item.gross_margin),
      net_margin: Number(item.net_margin),
      rank_score: item.rank_score ? Number(item.rank_score) : null,
    })),
  };
}

export interface KeywordResult {
  keyword: string;
  cpc: number;
  search_volume: number;
  competition: string;
}

export interface KeywordAnalysis {
  keywords_searched: string[];
  results: KeywordResult[];
  best_keyword: string | { keyword: string; volume: number; cpc: number; relevance: number } | null;
}

export interface AmazonSearchResult {
  asin: string;
  title: string;
  price: number | null;
  original_price: number | null;
  review_count: number;
  rating: number | null;
  is_prime: boolean;
  is_sponsored: boolean;
  position: number;
}

export interface AmazonSearchResults {
  keyword: string;
  products: AmazonSearchResult[];
  total_results: number | null;
  median_price: number | null;
  min_price: number | null;
  max_price: number | null;
  avg_price: number | null;
  avg_review_count: number;
}

export interface ScoredProductFull extends ScoredProduct {
  product_cost: number;
  shipping_cost: number;
  estimated_cpc: number;
  monthly_search_volume: number | null;
  keyword_analysis: KeywordAnalysis | null;
  // Amazon competitor data
  amazon_median_price: number | null;
  amazon_min_price: number | null;
  amazon_avg_review_count: number | null;
  amazon_prime_percentage: number | null;
  amazon_search_results: AmazonSearchResults | null;
  max_cpc: number;
  cpc_buffer: number;
  passed_filters: boolean;
  rejection_reasons: string[];
  point_breakdown: Record<string, number> | null;
  updated_at: string;
}

export async function getScoredProduct(id: string): Promise<ScoredProductFull> {
  const res = await fetch(`${API_URL}/products/${id}/score`, { cache: "no-store" });

  if (!res.ok) {
    throw new Error("Scored product not found");
  }

  const data = await res.json();
  return {
    ...data,
    product_cost: Number(data.product_cost),
    shipping_cost: Number(data.shipping_cost),
    selling_price: Number(data.selling_price),
    estimated_cpc: Number(data.estimated_cpc),
    cogs: Number(data.cogs),
    gross_margin: Number(data.gross_margin),
    net_margin: Number(data.net_margin),
    max_cpc: Number(data.max_cpc),
    cpc_buffer: Number(data.cpc_buffer),
    rank_score: data.rank_score ? Number(data.rank_score) : null,
    rejection_reasons: data.rejection_reasons || [],
    point_breakdown: data.point_breakdown || null,
    // Amazon data
    amazon_median_price: data.amazon_median_price ? Number(data.amazon_median_price) : null,
    amazon_min_price: data.amazon_min_price ? Number(data.amazon_min_price) : null,
    amazon_avg_review_count: data.amazon_avg_review_count ?? null,
    amazon_prime_percentage: data.amazon_prime_percentage ? Number(data.amazon_prime_percentage) : null,
    amazon_search_results: data.amazon_search_results || null,
  };
}

export async function approveProduct(
  id: string,
  options?: { selling_price?: number; compare_at_price?: number }
): Promise<ApproveProductResponse> {
  const res = await fetch(`${API_URL}/products/${id}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: options ? JSON.stringify(options) : "{}",
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to approve product");
  }

  return res.json();
}

export async function rejectProduct(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/products/${id}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to reject product");
  }
}

// Admin - Discovery

export interface SeedDemoResponse {
  status: string;
  message: string;
  created: number;
}

export async function seedDemoProducts(count: number = 20): Promise<SeedDemoResponse> {
  const res = await fetch(`${API_URL}/admin/seed-demo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ count }),
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to seed products");
  }

  return res.json();
}

export async function clearScoredProducts(): Promise<void> {
  const res = await fetch(`${API_URL}/admin/scored-products`, {
    method: "DELETE",
  });

  if (!res.ok) {
    throw new Error("Failed to clear products");
  }
}

// Admin - Discover from CJ

export interface DiscoverRequest {
  keywords: string[];
  limit_per_keyword: number;
}

export interface DiscoverResponse {
  status: string;
  message: string;
  discovered: number;
  skipped: number;
  scored: number;
  passed: number;
}

export async function discoverProducts(request: DiscoverRequest): Promise<DiscoverResponse> {
  const res = await fetch(`${API_URL}/admin/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to discover products");
  }

  return res.json();
}

// Admin - Scoring Settings

export interface ScoringSettings {
  // Fee assumptions
  payment_fee_rate: number;
  chargeback_rate: number;
  default_refund_rate: number;
  cvr: number;
  cpc_multiplier: number;

  // Hard filter thresholds
  max_cpc_threshold: number;
  min_gross_margin: number;
  min_selling_price: number;
  max_selling_price: number;
  max_shipping_days: number;
  min_supplier_rating: number;
  min_supplier_age_months: number;
  min_supplier_feedback: number;
  max_amazon_reviews_for_competition: number;
  min_cpc_buffer: number;
  max_weight_grams: number;
}

export async function getScoringSettings(): Promise<ScoringSettings> {
  const res = await fetch(`${API_URL}/admin/settings`, { cache: "no-store" });

  if (!res.ok) {
    throw new Error("Failed to fetch settings");
  }

  return res.json();
}

export async function updateScoringSettings(
  settings: Partial<ScoringSettings>
): Promise<ScoringSettings> {
  const res = await fetch(`${API_URL}/admin/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to update settings");
  }

  return res.json();
}

// ============================================================================
// Crawl System API
// ============================================================================

export interface CrawlConfig {
  keywords: string[];
  price_min: number;
  price_max: number;
  include_warehouses: string[];
  exclude_warehouses: string[];
  include_categories: string[];
  exclude_categories: string[];
}

export interface CrawlProgress {
  search_urls_submitted: number;
  search_urls_completed: number;
  product_urls_found: number;
  product_urls_skipped_existing: number;
  product_urls_submitted: number;
  product_urls_completed: number;
  products_parsed: number;
  products_skipped_filtered: number;
  products_scored: number;
  products_passed_scoring: number;
  errors: number;
}

export interface CrawlJob {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  config: CrawlConfig;
  progress: CrawlProgress;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ExclusionRule {
  id: string;
  rule_type: 'country' | 'category' | 'supplier' | 'keyword';
  value: string;
  reason: string | null;
  created_at: string;
}

export interface StartCrawlResponse {
  job_id: string;
  status: string;
  message: string;
  search_urls_submitted: number;
}

export async function startCrawl(config: CrawlConfig): Promise<StartCrawlResponse> {
  const res = await fetch(`${API_URL}/crawl/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to start crawl");
  }

  return res.json();
}

export async function getCrawlJob(jobId: string): Promise<CrawlJob> {
  const res = await fetch(`${API_URL}/crawl/${jobId}`, { cache: "no-store" });

  if (!res.ok) {
    throw new Error("Failed to fetch crawl job");
  }

  return res.json();
}

export async function getCrawlJobs(): Promise<CrawlJob[]> {
  const res = await fetch(`${API_URL}/crawl/jobs`, { cache: "no-store" });

  if (!res.ok) {
    throw new Error("Failed to fetch crawl jobs");
  }

  const data = await res.json();
  return data.items || [];
}

export async function cancelCrawl(jobId: string): Promise<void> {
  const res = await fetch(`${API_URL}/crawl/${jobId}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to cancel crawl");
  }
}

export interface CrawlLogEntry {
  ts: string;
  level: string;
  msg: string;
}

export interface CrawlLogsResponse {
  job_id: string;
  logs: CrawlLogEntry[];
}

export async function getCrawlLogs(jobId: string, since: number = 0): Promise<CrawlLogsResponse> {
  const res = await fetch(`${API_URL}/crawl/${jobId}/logs?since=${since}`, { cache: "no-store" });

  if (!res.ok) {
    throw new Error("Failed to fetch crawl logs");
  }

  return res.json();
}

export async function getExclusionRules(): Promise<ExclusionRule[]> {
  const res = await fetch(`${API_URL}/exclusions`, { cache: "no-store" });

  if (!res.ok) {
    throw new Error("Failed to fetch exclusion rules");
  }

  const data = await res.json();
  return data.items || [];
}

export async function addExclusionRule(rule: {
  rule_type: string;
  value: string;
  reason?: string;
}): Promise<ExclusionRule> {
  const res = await fetch(`${API_URL}/exclusions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rule),
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to add exclusion rule");
  }

  return res.json();
}

export async function deleteExclusionRule(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/exclusions/${id}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to delete exclusion rule");
  }
}

// ============================================================================
// LLM Product Analysis API
// ============================================================================

export interface ProductUnderstanding {
  product_type: string;
  style: string[];
  materials: string[];
  use_cases: string[];
  buyer_persona: string;
  quality_tier: string;
  price_expectation: string;
  seed_keywords: {
    exact: string[];
    specific: string[];
    broad: string[];
  };
}

export interface KeywordOpportunity {
  keyword: string;
  volume: number;
  cpc: number;
  relevance: number;
  opportunity_score: number;
  tier: string;
}

export interface KeywordExplorationDetails {
  total_keywords: number;
  total_explored: number;
  depth_reached: number;
  errors: string[];
  top_opportunities: KeywordOpportunity[];
  by_tier: {
    exact: KeywordOpportunity[];
    specific: KeywordOpportunity[];
    broad: KeywordOpportunity[];
  };
}

export interface KeywordAnalysisResult {
  seed_keywords: {
    exact: string[];
    specific: string[];
    broad: string[];
  };
  best_keyword: {
    keyword: string;
    volume: number;
    cpc: number;
    relevance: number;
  } | null;
  exploration: KeywordExplorationDetails;
}

export interface AmazonMatch {
  index: number;
  title: string;
  price: number;
  reviews: number;
  similarity: number;
  reason: string;
  asin?: string;
}

export interface AmazonAnalysis {
  similar_products: AmazonMatch[];
  market_price: {
    weighted_median: number | null;
    min: number | null;
    max: number | null;
  };
  sample_size: number;
}

export interface ViabilityAssessment {
  score: number;
  pros: string[];
  cons: string[];
  recommendation: "launch" | "maybe" | "skip";
  summary: string;
}

export interface ProductAnalysisResult {
  product_id: string;
  name: string;
  cost: number;
  product_understanding: ProductUnderstanding;
  keyword_analysis: KeywordAnalysisResult;
  amazon_analysis: AmazonAnalysis;
  viability: ViabilityAssessment;
}

export async function analyzeProduct(productId: string): Promise<ProductAnalysisResult> {
  const res = await fetch(`${API_URL}/admin/analyze-product/${productId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to analyze product");
  }

  return res.json();
}
