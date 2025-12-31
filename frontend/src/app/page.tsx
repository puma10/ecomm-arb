import Image from "next/image";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import { getProducts, Product } from "@/lib/api";

function ProductCard({ product }: { product: Product }) {
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
    <Link href={`/p/${product.slug}`}>
      <Card className="group overflow-hidden transition-all hover:shadow-lg">
        {/* Product Image */}
        <div className="relative aspect-square bg-gray-100">
          {product.images[0] ? (
            <Image
              src={product.images[0]}
              alt={product.name}
              fill
              className="object-cover transition-transform group-hover:scale-105"
              sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-gray-400">
              No image
            </div>
          )}
          {hasDiscount && (
            <div className="absolute left-2 top-2 rounded-full bg-red-500 px-2 py-0.5 text-xs font-bold text-white">
              -{discountPercent}%
            </div>
          )}
        </div>

        {/* Product Info */}
        <div className="p-3">
          <h3 className="line-clamp-2 text-sm font-medium text-gray-900 group-hover:text-blue-600">
            {product.name}
          </h3>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-lg font-bold text-gray-900">
              ${product.price.toFixed(2)}
            </span>
            {hasDiscount && (
              <span className="text-sm text-gray-500 line-through">
                ${product.compare_at_price!.toFixed(2)}
              </span>
            )}
          </div>
          <div className="mt-1 text-xs text-gray-500">
            Free shipping ({product.shipping_days_min}-{product.shipping_days_max} days)
          </div>
        </div>
      </Card>
    </Link>
  );
}

export default async function Home() {
  let products: Product[] = [];
  let error = false;

  try {
    const response = await getProducts();
    products = response.items;
  } catch {
    error = true;
  }

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b bg-white">
        <div className="mx-auto max-w-7xl px-4 py-4">
          <h1 className="text-xl font-bold text-gray-900">Ecom Arb Store</h1>
        </div>
      </header>

      {/* Hero Section */}
      <section className="bg-gradient-to-r from-blue-600 to-purple-600 py-12 text-white">
        <div className="mx-auto max-w-7xl px-4 text-center">
          <h2 className="text-3xl font-bold md:text-4xl">
            Discover Great Products
          </h2>
          <p className="mt-2 text-lg opacity-90">
            Quality items at unbeatable prices with free shipping
          </p>
        </div>
      </section>

      {/* Products Grid */}
      <section className="mx-auto max-w-7xl px-4 py-8">
        <h2 className="mb-6 text-2xl font-bold text-gray-900">
          Featured Products
        </h2>

        {error ? (
          <div className="rounded-lg bg-red-50 p-8 text-center text-red-600">
            <p>Failed to load products. Make sure the backend is running.</p>
            <p className="mt-2 text-sm">
              Run: <code className="rounded bg-red-100 px-2 py-1">make run-backend</code>
            </p>
          </div>
        ) : products.length === 0 ? (
          <div className="rounded-lg bg-gray-100 p-8 text-center text-gray-600">
            <p>No products available yet.</p>
            <p className="mt-2 text-sm">
              Run: <code className="rounded bg-gray-200 px-2 py-1">python scripts/seed.py</code>
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {products.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </section>

      {/* Footer */}
      <footer className="border-t bg-white py-8">
        <div className="mx-auto max-w-7xl px-4 text-center text-sm text-gray-500">
          <p>Free shipping on all orders</p>
          <p className="mt-1">30-day money-back guarantee</p>
        </div>
      </footer>
    </main>
  );
}
