import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getOrder } from "@/lib/api";

interface OrderPageProps {
  params: Promise<{ id: string }>;
}

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  pending: { label: "Pending", color: "bg-yellow-100 text-yellow-800" },
  paid: { label: "Paid", color: "bg-green-100 text-green-800" },
  processing: { label: "Processing", color: "bg-blue-100 text-blue-800" },
  shipped: { label: "Shipped", color: "bg-purple-100 text-purple-800" },
  delivered: { label: "Delivered", color: "bg-green-100 text-green-800" },
  refunded: { label: "Refunded", color: "bg-gray-100 text-gray-800" },
  cancelled: { label: "Cancelled", color: "bg-red-100 text-red-800" },
};

export default async function OrderPage({ params }: OrderPageProps) {
  const { id } = await params;

  let order;
  try {
    order = await getOrder(id);
  } catch {
    notFound();
  }

  const status = STATUS_LABELS[order.status] || {
    label: order.status,
    color: "bg-gray-100 text-gray-800",
  };

  const isPaid = ["paid", "processing", "shipped", "delivered"].includes(
    order.status
  );

  return (
    <main className="min-h-screen bg-gray-50 py-8">
      <div className="mx-auto max-w-2xl px-4">
        {isPaid && (
          <div className="mb-8 text-center">
            <div className="mb-4 text-6xl">✓</div>
            <h1 className="text-3xl font-bold text-green-600">
              Thank you for your order!
            </h1>
            <p className="mt-2 text-gray-600">
              We&apos;ve sent a confirmation email to your inbox.
            </p>
          </div>
        )}

        <Card className="mb-6">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Order #{order.order_number}</CardTitle>
              <span
                className={`rounded-full px-3 py-1 text-sm font-medium ${status.color}`}
              >
                {status.label}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            {/* Product */}
            <div className="flex gap-4">
              <div className="relative h-20 w-20 flex-shrink-0 overflow-hidden rounded-md bg-gray-100">
                {order.product.images[0] && (
                  <Image
                    src={order.product.images[0]}
                    alt={order.product.name}
                    fill
                    className="object-cover"
                  />
                )}
              </div>
              <div className="flex-1">
                <h3 className="font-medium">{order.product.name}</h3>
                <p className="text-sm text-gray-500">Qty: {order.quantity}</p>
              </div>
              <div className="font-medium">${order.subtotal.toFixed(2)}</div>
            </div>

            <hr className="my-4" />

            {/* Totals */}
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span>Subtotal</span>
                <span>${order.subtotal.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span>Shipping</span>
                <span>
                  {order.shipping_cost > 0
                    ? `$${order.shipping_cost.toFixed(2)}`
                    : "Free"}
                </span>
              </div>
            </div>

            <hr className="my-4" />

            <div className="flex justify-between text-lg font-bold">
              <span>Total</span>
              <span>${order.total.toFixed(2)}</span>
            </div>
          </CardContent>
        </Card>

        {/* Shipping Address */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Shipping Address</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-gray-600">
              <p>
                {order.shipping_address.first_name}{" "}
                {order.shipping_address.last_name}
              </p>
              <p>{order.shipping_address.address_line1}</p>
              {order.shipping_address.address_line2 && (
                <p>{order.shipping_address.address_line2}</p>
              )}
              <p>
                {order.shipping_address.city}, {order.shipping_address.state}{" "}
                {order.shipping_address.postal_code}
              </p>
              <p>{order.shipping_address.country}</p>
            </div>
          </CardContent>
        </Card>

        {/* Tracking */}
        {order.tracking_number && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Tracking Information</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-gray-600">
                Tracking Number: <strong>{order.tracking_number}</strong>
              </p>
              {order.tracking_url && (
                <a
                  href={order.tracking_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-block text-blue-600 hover:underline"
                >
                  Track your package →
                </a>
              )}
            </CardContent>
          </Card>
        )}

        {/* Actions */}
        <div className="text-center">
          <p className="mb-4 text-sm text-gray-500">
            Questions about your order? Contact us at support@example.com
          </p>
          <Link href="/">
            <Button variant="outline">Continue Shopping</Button>
          </Link>
        </div>
      </div>
    </main>
  );
}
