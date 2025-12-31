"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createCheckoutSession,
  getProduct,
  Product,
  ShippingAddress,
} from "@/lib/api";

export default function CheckoutPage() {
  const params = useParams();
  const slug = params.slug as string;

  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [address, setAddress] = useState<ShippingAddress>({
    first_name: "",
    last_name: "",
    address_line1: "",
    address_line2: "",
    city: "",
    state: "",
    postal_code: "",
    country: "US",
  });

  useEffect(() => {
    async function loadProduct() {
      try {
        const p = await getProduct(slug);
        setProduct(p);
      } catch {
        setError("Product not found");
      } finally {
        setLoading(false);
      }
    }
    loadProduct();
  }, [slug]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!product) return;

    setSubmitting(true);
    setError(null);

    try {
      const { checkout_url } = await createCheckoutSession(
        product.slug,
        email,
        address,
        1
      );
      window.location.href = checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-gray-900 mx-auto"></div>
          <p className="mt-2 text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (error && !product) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 p-4">
        <div className="text-center">
          <div className="text-6xl mb-4">😕</div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Product not found</h1>
          <p className="text-gray-600 mb-4">{error}</p>
          <Link href="/">
            <Button variant="outline">Go Home</Button>
          </Link>
        </div>
      </div>
    );
  }

  if (!product) return null;

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="border-b bg-white">
        <div className="mx-auto max-w-4xl px-4 py-4">
          <Link href={`/p/${product.slug}`} className="text-sm text-gray-600 hover:text-gray-900">
            ← Back to product
          </Link>
        </div>
      </div>

      <div className="mx-auto max-w-4xl px-4 py-6 lg:py-8">
        <h1 className="mb-6 text-xl font-bold lg:text-2xl">Checkout</h1>

        {/* Mobile: Order summary first */}
        <div className="lg:hidden mb-6">
          <Card>
            <CardContent className="p-4">
              <div className="flex gap-4">
                <div className="relative h-20 w-20 flex-shrink-0 overflow-hidden rounded-md bg-gray-100">
                  {product.images[0] && (
                    <Image
                      src={product.images[0]}
                      alt={product.name}
                      fill
                      className="object-cover"
                    />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-sm truncate">{product.name}</h3>
                  <p className="text-sm text-gray-500">Qty: 1</p>
                  <p className="font-bold mt-1">${product.price.toFixed(2)}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Shipping Form */}
          <div className="order-2 lg:order-1">
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Contact */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Contact</CardTitle>
                </CardHeader>
                <CardContent className="pt-0">
                  <div>
                    <Label htmlFor="email" className="text-sm">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      placeholder="you@example.com"
                      className="mt-1"
                    />
                  </div>
                </CardContent>
              </Card>

              {/* Shipping Address */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Shipping Address</CardTitle>
                </CardHeader>
                <CardContent className="pt-0 space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label htmlFor="first_name" className="text-sm">First Name</Label>
                      <Input
                        id="first_name"
                        value={address.first_name}
                        onChange={(e) =>
                          setAddress({ ...address, first_name: e.target.value })
                        }
                        required
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <Label htmlFor="last_name" className="text-sm">Last Name</Label>
                      <Input
                        id="last_name"
                        value={address.last_name}
                        onChange={(e) =>
                          setAddress({ ...address, last_name: e.target.value })
                        }
                        required
                        className="mt-1"
                      />
                    </div>
                  </div>

                  <div>
                    <Label htmlFor="address_line1" className="text-sm">Address</Label>
                    <Input
                      id="address_line1"
                      value={address.address_line1}
                      onChange={(e) =>
                        setAddress({ ...address, address_line1: e.target.value })
                      }
                      required
                      placeholder="123 Main St"
                      className="mt-1"
                    />
                  </div>

                  <div>
                    <Label htmlFor="address_line2" className="text-sm">
                      Apt, suite, etc. <span className="text-gray-400">(optional)</span>
                    </Label>
                    <Input
                      id="address_line2"
                      value={address.address_line2}
                      onChange={(e) =>
                        setAddress({ ...address, address_line2: e.target.value })
                      }
                      className="mt-1"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label htmlFor="city" className="text-sm">City</Label>
                      <Input
                        id="city"
                        value={address.city}
                        onChange={(e) =>
                          setAddress({ ...address, city: e.target.value })
                        }
                        required
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <Label htmlFor="state" className="text-sm">State</Label>
                      <Input
                        id="state"
                        value={address.state}
                        onChange={(e) =>
                          setAddress({ ...address, state: e.target.value })
                        }
                        required
                        placeholder="CA"
                        className="mt-1"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label htmlFor="postal_code" className="text-sm">ZIP Code</Label>
                      <Input
                        id="postal_code"
                        value={address.postal_code}
                        onChange={(e) =>
                          setAddress({ ...address, postal_code: e.target.value })
                        }
                        required
                        placeholder="12345"
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <Label htmlFor="country" className="text-sm">Country</Label>
                      <Input
                        id="country"
                        value={address.country}
                        disabled
                        className="mt-1 bg-gray-50"
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              {error && (
                <div className="rounded-md bg-red-50 p-4 text-sm text-red-600">
                  {error}
                </div>
              )}

              {/* Desktop Submit */}
              <div className="hidden lg:block">
                <Button
                  type="submit"
                  size="lg"
                  className="w-full text-lg font-semibold"
                  disabled={submitting}
                >
                  {submitting ? "Processing..." : `Pay $${product.price.toFixed(2)}`}
                </Button>
                <p className="text-center text-xs text-gray-500 mt-2">
                  Secure checkout powered by Stripe
                </p>
              </div>
            </form>
          </div>

          {/* Order Summary - Desktop */}
          <div className="order-1 lg:order-2 hidden lg:block">
            <Card className="sticky top-8">
              <CardHeader>
                <CardTitle>Order Summary</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex gap-4">
                  <div className="relative h-20 w-20 flex-shrink-0 overflow-hidden rounded-md bg-gray-100">
                    {product.images[0] && (
                      <Image
                        src={product.images[0]}
                        alt={product.name}
                        fill
                        className="object-cover"
                      />
                    )}
                  </div>
                  <div className="flex-1">
                    <h3 className="font-medium">{product.name}</h3>
                    <p className="text-sm text-gray-500">Qty: 1</p>
                  </div>
                  <div className="font-medium">${product.price.toFixed(2)}</div>
                </div>

                <hr className="my-4" />

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span>Subtotal</span>
                    <span>${product.price.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Shipping</span>
                    <span className="text-green-600">Free</span>
                  </div>
                </div>

                <hr className="my-4" />

                <div className="flex justify-between text-lg font-bold">
                  <span>Total</span>
                  <span>${product.price.toFixed(2)}</span>
                </div>

                <div className="mt-4 text-center text-xs text-gray-500">
                  📦 Delivery: {product.shipping_days_min}-{product.shipping_days_max} business days
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/* Mobile Sticky Footer */}
      <div className="fixed bottom-0 left-0 right-0 border-t bg-white p-4 shadow-lg lg:hidden">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-gray-600">Total</span>
          <span className="text-xl font-bold">${product.price.toFixed(2)}</span>
        </div>
        <Button
          type="submit"
          size="lg"
          className="w-full text-lg font-semibold h-12"
          disabled={submitting}
          onClick={handleSubmit}
        >
          {submitting ? "Processing..." : "Continue to Payment"}
        </Button>
      </div>

      {/* Spacer for mobile sticky footer */}
      <div className="h-32 lg:hidden" />
    </main>
  );
}
