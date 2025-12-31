import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { getProduct } from "@/lib/api";

interface ProductPageProps {
  params: Promise<{ slug: string }>;
}

export default async function ProductPage({ params }: ProductPageProps) {
  const { slug } = await params;

  let product;
  try {
    product = await getProduct(slug);
  } catch {
    notFound();
  }

  const hasDiscount =
    product.compare_at_price && product.compare_at_price > product.price;
  const discountPercent = hasDiscount
    ? Math.round(
        ((product.compare_at_price! - product.price) /
          product.compare_at_price!) *
          100
      )
    : 0;

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-6xl px-4 py-8">
        <div className="grid gap-8 lg:grid-cols-2">
          {/* Product Images */}
          <div className="space-y-4">
            <div className="relative aspect-square overflow-hidden rounded-lg bg-white">
              {product.images[0] ? (
                <Image
                  src={product.images[0]}
                  alt={product.name}
                  fill
                  className="object-contain"
                  priority
                />
              ) : (
                <div className="flex h-full items-center justify-center text-gray-400">
                  No image available
                </div>
              )}
              {hasDiscount && (
                <div className="absolute left-4 top-4 rounded-full bg-red-500 px-3 py-1 text-sm font-bold text-white">
                  {discountPercent}% OFF
                </div>
              )}
            </div>

            {/* Thumbnail gallery */}
            {product.images.length > 1 && (
              <div className="flex gap-2 overflow-x-auto">
                {product.images.slice(0, 5).map((image, index) => (
                  <div
                    key={index}
                    className="relative h-20 w-20 flex-shrink-0 overflow-hidden rounded-md bg-white"
                  >
                    <Image
                      src={image}
                      alt={`${product.name} - Image ${index + 1}`}
                      fill
                      className="object-cover"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Product Details */}
          <div className="space-y-6">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                {product.name}
              </h1>
            </div>

            {/* Pricing */}
            <div className="flex items-baseline gap-3">
              <span className="text-4xl font-bold text-gray-900">
                ${product.price.toFixed(2)}
              </span>
              {hasDiscount && (
                <span className="text-xl text-gray-500 line-through">
                  ${product.compare_at_price!.toFixed(2)}
                </span>
              )}
            </div>

            {/* Description */}
            <div className="prose prose-gray max-w-none">
              <p className="text-gray-600">{product.description}</p>
            </div>

            {/* Trust Badges */}
            <Card className="p-4">
              <div className="grid grid-cols-3 gap-4 text-center text-sm">
                <div>
                  <div className="mb-1 text-2xl">🚚</div>
                  <div className="font-medium">Free Shipping</div>
                  <div className="text-xs text-gray-500">
                    {product.shipping_days_min}-{product.shipping_days_max} days
                  </div>
                </div>
                <div>
                  <div className="mb-1 text-2xl">↩️</div>
                  <div className="font-medium">Easy Returns</div>
                  <div className="text-xs text-gray-500">30-day guarantee</div>
                </div>
                <div>
                  <div className="mb-1 text-2xl">🔒</div>
                  <div className="font-medium">Secure Payment</div>
                  <div className="text-xs text-gray-500">SSL encrypted</div>
                </div>
              </div>
            </Card>

            {/* CTA Button */}
            <Link href={`/checkout/${product.slug}`}>
              <Button size="lg" className="w-full text-lg font-semibold">
                Buy Now - ${product.price.toFixed(2)}
              </Button>
            </Link>

            {/* Payment Methods */}
            <div className="text-center text-sm text-gray-500">
              We accept Visa, Mastercard, American Express, and more
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
