'use client'

import Link from 'next/link'

import { Badge } from '@/components/Badge'
import { DataProduct } from '@/lib/api-client'
import { useApiResource } from '@/lib/hooks/use-api-resource'

export default function ProductsPage() {
  const { data, error, isLoading } = useApiResource<DataProduct[]>('/api/core/data-products/')

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-900">Data product catalog</h1>
      <p className="mt-1 text-sm text-slate-500">
        What data products exist, where they originated, and whether they&apos;ve passed conformity and
        privacy screening.
      </p>

      {isLoading && <p className="mt-6 text-sm text-slate-500">Loading…</p>}
      {error && <p className="mt-6 text-sm text-red-600">Could not load the catalog ({error.status}).</p>}

      {data && (
        <div className="mt-6 overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Title</th>
                <th className="px-4 py-3">Origin</th>
                <th className="px-4 py-3">Privacy</th>
                <th className="px-4 py-3">Pipeline stage</th>
                <th className="px-4 py-3">Quality</th>
                <th className="px-4 py-3">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((product) => (
                <tr key={product.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link href={`/products/${product.id}`} className="font-medium text-slate-900 hover:underline">
                      {product.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {product.source || '—'}
                    {product.geographic_coverage ? ` · ${product.geographic_coverage}` : ''}
                  </td>
                  <td className="px-4 py-3">
                    <Badge value={product.sensitivity_classification} />
                  </td>
                  <td className="px-4 py-3">
                    <Badge value={product.transformation_status} />
                  </td>
                  <td className="px-4 py-3">
                    <Badge value={product.quality_status} />
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {new Date(product.updated_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
              {data.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-slate-400">
                    No data products yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
