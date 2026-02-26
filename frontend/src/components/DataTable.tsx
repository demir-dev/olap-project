import { useState } from 'react'

interface DataTableProps {
  columns: string[]
  rows: (string | number | null)[][]
  rowCount: number
  maxHeight?: string
}

function formatCell(value: string | number | null, colName: string): string {
  if (value === null || value === undefined) return '—'

  const col = colName.toLowerCase()
  const num = typeof value === 'number' ? value : parseFloat(String(value))

  if (!isNaN(num)) {
    // Revenue / profit / cost → currency
    if (col.includes('revenue') || col.includes('profit') || col.includes('cost') || col.includes('value') || col.includes('price')) {
      if (Math.abs(num) >= 1_000_000) return `$${(num / 1_000_000).toFixed(1)}M`
      if (Math.abs(num) >= 1_000) return `$${(num / 1_000).toFixed(1)}K`
      return `$${num.toFixed(2)}`
    }
    // Percentage columns
    if (col.includes('pct') || col.includes('percent') || col.includes('margin') || col.includes('growth') || col.includes('share')) {
      return `${num.toFixed(1)}%`
    }
    // Z-score
    if (col.includes('z_score')) {
      return num.toFixed(2)
    }
    // Large counts
    if (num >= 1_000) return num.toLocaleString()
    return String(value)
  }

  return String(value)
}

function getColumnAlignment(colName: string, rows: (string | number | null)[][]): 'left' | 'right' {
  const col = colName.toLowerCase()
  if (
    col.includes('revenue') || col.includes('profit') || col.includes('cost') ||
    col.includes('pct') || col.includes('percent') || col.includes('margin') ||
    col.includes('growth') || col.includes('rank') || col.includes('count') ||
    col.includes('quantity') || col.includes('orders') || col.includes('value') ||
    col.includes('price') || col.includes('share') || col.includes('score')
  ) {
    return 'right'
  }
  return 'left'
}

export function DataTable({ columns, rows, rowCount, maxHeight = '400px' }: DataTableProps) {
  const [sortCol, setSortCol] = useState<number | null>(null)
  const [sortAsc, setSortAsc] = useState(true)

  if (!columns.length) return null

  const handleSort = (idx: number) => {
    if (sortCol === idx) {
      setSortAsc(!sortAsc)
    } else {
      setSortCol(idx)
      setSortAsc(false) // default: descending for numeric
    }
  }

  let displayRows = [...rows]
  if (sortCol !== null) {
    displayRows.sort((a, b) => {
      const av = a[sortCol]
      const bv = b[sortCol]
      if (av === null) return 1
      if (bv === null) return -1
      const an = parseFloat(String(av))
      const bn = parseFloat(String(bv))
      if (!isNaN(an) && !isNaN(bn)) {
        return sortAsc ? an - bn : bn - an
      }
      return sortAsc
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av))
    })
  }

  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden shadow-sm">
      <div className="overflow-x-auto overflow-y-auto scrollbar-thin" style={{ maxHeight }}>
        <table className="w-full text-sm border-collapse min-w-max">
          <thead className="bg-gray-50 border-b border-gray-200 sticky top-0 z-10">
            <tr>
              {columns.map((col, idx) => {
                const align = getColumnAlignment(col, rows)
                return (
                  <th
                    key={idx}
                    onClick={() => handleSort(idx)}
                    className={`
                      px-4 py-3 font-semibold text-gray-600 uppercase text-xs tracking-wide
                      cursor-pointer hover:bg-gray-100 select-none whitespace-nowrap
                      ${align === 'right' ? 'text-right' : 'text-left'}
                    `}
                  >
                    <span className="flex items-center gap-1 justify-between">
                      <span className={align === 'right' ? 'ml-auto' : ''}>
                        {col.replace(/_/g, ' ')}
                      </span>
                      {sortCol === idx ? (
                        <span className="text-blue-500">{sortAsc ? '↑' : '↓'}</span>
                      ) : (
                        <span className="opacity-0 group-hover:opacity-30">↕</span>
                      )}
                    </span>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {displayRows.map((row, rIdx) => (
              <tr key={rIdx} className="hover:bg-blue-50/40 transition-colors">
                {row.map((cell, cIdx) => {
                  const align = getColumnAlignment(columns[cIdx], rows)
                  const formatted = formatCell(cell, columns[cIdx])
                  const isAnomaly = columns[cIdx]?.toLowerCase() === 'status' && String(cell) === 'ANOMALY'
                  const isNegative = typeof cell === 'number' && cell < 0 && (
                    columns[cIdx]?.toLowerCase().includes('growth') ||
                    columns[cIdx]?.toLowerCase().includes('pct')
                  )
                  return (
                    <td
                      key={cIdx}
                      className={`
                        px-4 py-2.5 whitespace-nowrap
                        ${align === 'right' ? 'text-right font-mono text-gray-700' : 'text-left text-gray-800'}
                        ${isAnomaly ? 'text-red-600 font-semibold' : ''}
                        ${isNegative ? 'text-red-500' : ''}
                        ${!isAnomaly && !isNegative && align === 'right' ? 'text-gray-700' : ''}
                      `}
                    >
                      {formatted}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rowCount > 0 && (
        <div className="px-4 py-2 text-xs text-gray-400 border-t border-gray-100 bg-gray-50">
          {rowCount} row{rowCount !== 1 ? 's' : ''}
          {rows.length < rowCount && ` (showing ${rows.length})`}
        </div>
      )}
    </div>
  )
}
