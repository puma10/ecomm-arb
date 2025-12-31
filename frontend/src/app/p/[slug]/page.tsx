import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { getProduct } from "@/lib/api";

interface ProductPageProps {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({
  params,
}: ProductPageProps): Promise<Metadata> {
  const { slug } = await params;
  try {
    const product = await getProduct(slug);
    return {
      title: product.name,
      description: product.description.slice(0, 160),
    };
  } catch {
    return {
      title: "Product Not Found",
    };
  }
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
    <main className="min-h-screen bg-white">
      {/* Mobile-first layout */}
      <div className="mx-auto max-w-6xl">
        <div className="grid gap-0 lg:grid-cols-2 lg:gap-8 lg:p-8">
          {/* Product Images */}
          <div className="relative">
            {/* Main Image - Full width on mobile */}
            <div className="relative aspect-square w-full bg-gray-100 lg:rounded-lg lg:overflow-hidden">
              {product.images[0] ? (
                <Image
                  src={product.images[0]}
                  alt={product.name}
                  fill
                  className="object-contain"
                  priority
                  sizes="(max-width: 1024px) 100vw, 50vw"
                />
              ) : (
                <div className="flex h-full items-center justify-center text-gray-400">
                  No image available
                </div>
              )}
              {hasDiscount && (
                <div className="absolute left-3 top-3 rounded-full bg-red-500 px-3 py-1 text-sm font-bold text-white shadow-lg">
                  Save {discountPercent}%
                </div>
              )}
            </div>

            {/* Thumbnail gallery - horizontal scroll on mobile */}
            {product.images.length > 1 && (
              <div className="flex gap-2 overflow-x-auto p-3 lg:p-0 lg:mt-4">
                {product.images.slice(0, 5).map((image, index) => (
                  <div
                    key={index}
                    className="relative h-16 w-16 flex-shrink-0 overflow-hidden rounded-md bg-gray-100 ring-2 ring-transparent hover:ring-gray-300 transition-all cursor-pointer"
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
          <div className="space-y-4 p-4 lg:p-0">
            {/* Title */}
            <h1 className="text-2xl font-bold text-gray-900 lg:text-3xl">
              {product.name}
            </h1>

            {/* Pricing */}
            <div className="flex items-baseline gap-3">
              <span className="text-3xl font-bold text-gray-900 lg:text-4xl">
                ${product.price.toFixed(2)}
              </span>
              {hasDiscount && (
                <>
                  <span className="text-lg text-gray-500 line-through lg:text-xl">
                    ${product.compare_at_price!.toFixed(2)}
                  </span>
                  <span className="rounded-md bg-red-100 px-2 py-1 text-sm font-semibold text-red-700">
                    {discountPercent}% OFF
                  </span>
                </>
              )}
            </div>

            {/* Trust Badges - 2 columns on mobile, 3 on desktop */}
            <Card className="p-4">
              <div className="grid grid-cols-2 gap-4 text-center text-sm lg:grid-cols-3">
                <div className="flex flex-col items-center">
                  <div className="mb-1 text-2xl">🚚</div>
                  <div className="font-medium">Free Shipping</div>
                  <div className="text-xs text-gray-500">
                    {product.shipping_days_min}-{product.shipping_days_max} days
                  </div>
                </div>
                <div className="flex flex-col items-center">
                  <div className="mb-1 text-2xl">↩️</div>
                  <div className="font-medium">Easy Returns</div>
                  <div className="text-xs text-gray-500">30-day guarantee</div>
                </div>
                <div className="flex flex-col items-center col-span-2 lg:col-span-1">
                  <div className="mb-1 text-2xl">🔒</div>
                  <div className="font-medium">Secure Payment</div>
                  <div className="text-xs text-gray-500">SSL encrypted</div>
                </div>
              </div>
            </Card>

            {/* Description */}
            <div className="prose prose-gray prose-sm max-w-none lg:prose-base">
              <h3 className="text-lg font-semibold text-gray-900">Description</h3>
              <div className="whitespace-pre-line text-gray-600">
                {product.description}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sticky CTA - Mobile only */}
      <div className="fixed bottom-0 left-0 right-0 border-t bg-white p-4 shadow-lg lg:hidden">
        <Link href={`/checkout/${product.slug}`}>
          <Button size="lg" className="w-full text-lg font-semibold h-14">
            Buy Now - ${product.price.toFixed(2)}
          </Button>
        </Link>
      </div>

      {/* Desktop CTA */}
      <div className="hidden lg:block lg:fixed lg:bottom-8 lg:right-8">
        <Link href={`/checkout/${product.slug}`}>
          <Button size="lg" className="text-lg font-semibold shadow-lg px-8">
            Buy Now - ${product.price.toFixed(2)}
          </Button>
        </Link>
      </div>

      {/* Spacer for sticky CTA on mobile */}
      <div className="h-24 lg:hidden" />
    </main>
  );
}
