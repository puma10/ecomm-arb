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
