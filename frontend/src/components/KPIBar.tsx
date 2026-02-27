import { useEffect, useState } from 'react'
import { DollarSign, TrendingUp, Percent, ShoppingCart, Package, Globe } from 'lucide-react'
import { api } from '../api/client'
import type { DashboardKPIs } from '../types'

function fmt(value: number, type: 'currency' | 'percent' | 'integer'): string {
  if (type === 'currency') {
    if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
    if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`
    return `$${value.toFixed(0)}`
  }
  if (type === 'percent') return `${value.toFixed(1)}%`
  return value.toLocaleString()
}

const CARDS = [
  {
    key: 'total_revenue' as keyof DashboardKPIs,
    label: 'Total Revenue',
    type: 'currency' as const,
    icon: DollarSign,
    gradient: 'from-blue-500 to-blue-600',
    bg: 'bg-blue-50',
    text: 'text-blue-600',
  },
  {
    key: 'total_profit' as keyof DashboardKPIs,
    label: 'Total Profit',
    type: 'currency' as const,
    icon: TrendingUp,
    gradient: 'from-green-500 to-green-600',
    bg: 'bg-green-50',
    text: 'text-green-600',
  },
  {
    key: 'avg_margin_pct' as keyof DashboardKPIs,
    label: 'Avg Margin',
    type: 'percent' as const,
    icon: Percent,
    gradient: 'from-purple-500 to-purple-600',
    bg: 'bg-purple-50',
    text: 'text-purple-600',
  },
  {
    key: 'total_orders' as keyof DashboardKPIs,
    label: 'Total Orders',
    type: 'integer' as const,
    icon: ShoppingCart,
    gradient: 'from-orange-500 to-orange-600',
    bg: 'bg-orange-50',
    text: 'text-orange-600',
  },
  {
    key: 'total_units' as keyof DashboardKPIs,
    label: 'Units Sold',
    type: 'integer' as const,
    icon: Package,
    gradient: 'from-pink-500 to-pink-600',
    bg: 'bg-pink-50',
    text: 'text-pink-600',
  },
  {
    key: 'countries' as keyof DashboardKPIs,
    label: 'Countries',
    type: 'integer' as const,
    icon: Globe,
    gradient: 'from-teal-500 to-teal-600',
    bg: 'bg-teal-50',
    text: 'text-teal-600',
  },
]

export function KPIBar() {
  const [kpis, setKpis] = useState<DashboardKPIs | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.dashboardKpis()
      .then(setKpis)
      .catch(() => setKpis(null))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="flex-shrink-0 bg-white border-b border-gray-100 px-4 py-3">
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
        {CARDS.map(({ key, label, type, icon: Icon, gradient, bg, text }) => (
          <div key={key} className={`rounded-xl p-3 ${bg} flex items-center gap-2.5`}>
            <div className={`flex-shrink-0 h-8 w-8 rounded-lg bg-gradient-to-br ${gradient} flex items-center justify-center shadow-sm`}>
              <Icon className="h-4 w-4 text-white" />
            </div>
            <div className="min-w-0">
              <p className="text-xs text-gray-500 leading-none truncate">{label}</p>
              <p className={`text-sm font-bold ${text} leading-tight mt-0.5`}>
                {loading || !kpis ? '—' : fmt(kpis[key], type)}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
