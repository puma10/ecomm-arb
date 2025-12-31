"use client";

import Image from "next/image";
import { useParams, useRouter } from "next/navigation";
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
  const router = useRouter();
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
      // Redirect to Stripe checkout
      window.location.href = checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-lg">Loading...</div>
      </div>
    );
  }

  if (error && !product) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-lg text-red-500">{error}</div>
      </div>
    );
  }

  if (!product) return null;

  return (
    <main className="min-h-screen bg-gray-50 py-8">
      <div className="mx-auto max-w-4xl px-4">
        <h1 className="mb-8 text-2xl font-bold">Checkout</h1>

        <div className="grid gap-8 lg:grid-cols-2">
          {/* Shipping Form */}
          <div>
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Contact */}
              <Card>
                <CardHeader>
                  <CardTitle>Contact Information</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div>
                      <Label htmlFor="email">Email</Label>
                      <Input
                        id="email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        placeholder="you@example.com"
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Shipping Address */}
              <Card>
                <CardHeader>
                  <CardTitle>Shipping Address</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="first_name">First Name</Label>
                        <Input
                          id="first_name"
                          value={address.first_name}
                          onChange={(e) =>
                            setAddress({ ...address, first_name: e.target.value })
                          }
                          required
                        />
                      </div>
                      <div>
                        <Label htmlFor="last_name">Last Name</Label>
                        <Input
                          id="last_name"
                          value={address.last_name}
                          onChange={(e) =>
                            setAddress({ ...address, last_name: e.target.value })
                          }
                          required
                        />
                      </div>
                    </div>

                    <div>
                      <Label htmlFor="address_line1">Address</Label>
                      <Input
                        id="address_line1"
                        value={address.address_line1}
                        onChange={(e) =>
                          setAddress({ ...address, address_line1: e.target.value })
                        }
                        required
                        placeholder="123 Main St"
                      />
                    </div>

                    <div>
                      <Label htmlFor="address_line2">
                        Apartment, suite, etc. (optional)
                      </Label>
                      <Input
                        id="address_line2"
                        value={address.address_line2}
                        onChange={(e) =>
                          setAddress({ ...address, address_line2: e.target.value })
                        }
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="city">City</Label>
                        <Input
                          id="city"
                          value={address.city}
                          onChange={(e) =>
                            setAddress({ ...address, city: e.target.value })
                          }
                          required
                        />
                      </div>
                      <div>
                        <Label htmlFor="state">State</Label>
                        <Input
                          id="state"
                          value={address.state}
                          onChange={(e) =>
                            setAddress({ ...address, state: e.target.value })
                          }
                          required
                          placeholder="CA"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="postal_code">ZIP Code</Label>
                        <Input
                          id="postal_code"
                          value={address.postal_code}
                          onChange={(e) =>
                            setAddress({ ...address, postal_code: e.target.value })
                          }
                          required
                          placeholder="12345"
                        />
                      </div>
                      <div>
                        <Label htmlFor="country">Country</Label>
                        <Input
                          id="country"
                          value={address.country}
                          onChange={(e) =>
                            setAddress({ ...address, country: e.target.value })
                          }
                          required
                          disabled
                        />
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {error && (
                <div className="rounded-md bg-red-50 p-4 text-red-600">
                  {error}
                </div>
              )}

              <Button
                type="submit"
                size="lg"
                className="w-full text-lg font-semibold"
                disabled={submitting}
              >
                {submitting ? "Processing..." : `Pay $${product.price.toFixed(2)}`}
              </Button>

              <p className="text-center text-sm text-gray-500">
                You&apos;ll be redirected to Stripe for secure payment
              </p>
            </form>
          </div>

          {/* Order Summary */}
          <div>
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
                  Estimated delivery: {product.shipping_days_min}-
                  {product.shipping_days_max} business days
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </main>
  );
}
