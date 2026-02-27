import { useState } from 'react'
import { ChevronDown, ChevronRight, Play } from 'lucide-react'
import { api } from '../api/client'
import { DataTable } from './DataTable'
import type { DataPayload } from '../types'

interface SectionResult {
  data: DataPayload | null
  error: string | null
  loading: boolean
}

function useOlapSection() {
  const [result, setResult] = useState<SectionResult>({ data: null, error: null, loading: false })
  const run = async (op: string, body: Record<string, unknown>) => {
    setResult({ data: null, error: null, loading: true })
    try {
      const res = await api.olapOperation(op, body) as { data?: DataPayload; error?: string }
      setResult({ data: res.data ?? null, error: res.error ?? null, loading: false })
    } catch (e: unknown) {
      setResult({ data: null, error: e instanceof Error ? e.message : 'Error', loading: false })
    }
  }
  return { result, run }
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <span className="text-sm font-semibold text-gray-700">{title}</span>
        {open ? <ChevronDown className="h-4 w-4 text-gray-400" /> : <ChevronRight className="h-4 w-4 text-gray-400" />}
      </button>
      {open && <div className="p-4 space-y-3 bg-white">{children}</div>}
    </div>
  )
}

function RunButton({ onClick, loading }: { onClick: () => void; loading: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
    >
      <Play className="h-3 w-3" />
      {loading ? 'Running…' : 'Run'}
    </button>
  )
}

function ResultView({ result }: { result: SectionResult }) {
  if (result.loading) return <p className="text-xs text-gray-400">Executing…</p>
  if (result.error) return <p className="text-xs text-red-500">{result.error}</p>
  if (!result.data) return null
  return (
    <div className="mt-2 max-h-64 overflow-auto rounded border border-gray-100">
      <DataTable data={result.data} maxRows={20} />
    </div>
  )
}

function Select({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: string[]
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-gray-500 w-20 flex-shrink-0">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="flex-1 text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-700"
      >
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}

function Input({ label, value, onChange, type = 'text' }: {
  label: string; value: string; onChange: (v: string) => void; type?: string
}) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-gray-500 w-20 flex-shrink-0">{label}</label>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="flex-1 text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-700"
      />
    </div>
  )
}

const DIMENSIONS = ['region', 'country', 'category', 'subcategory', 'customer_segment', 'year', 'quarter', 'month']
const MEASURES = ['revenue', 'profit', 'cost', 'quantity', 'orders', 'profit_margin']
const REGIONS = ['North America', 'Europe', 'Asia Pacific', 'Latin America']
const CATEGORIES = ['Electronics', 'Furniture', 'Office Supplies', 'Clothing']
const YEARS = ['2022', '2023', '2024']

export function OLAPControls() {
  // Drill-down / Roll-up
  const nav = useOlapSection()
  const [navOp, setNavOp] = useState<'drill-down' | 'roll-up'>('drill-down')
  const [navDim, setNavDim] = useState('region')

  // Slice
  const slice = useOlapSection()
  const [sliceDim, setSliceDim] = useState('region')
  const [sliceVal, setSliceVal] = useState('Europe')
  const [sliceMeas, setSliceMeas] = useState('revenue')

  // Dice
  const dice = useOlapSection()
  const [diceRegion, setDiceRegion] = useState('')
  const [diceCat, setDiceCat] = useState('')
  const [diceYear, setDiceYear] = useState('')

  // Pivot
  const pivot = useOlapSection()
  const [pivotRows, setPivotRows] = useState('region')
  const [pivotCols, setPivotCols] = useState('year')
  const [pivotMeas, setPivotMeas] = useState('revenue')

  // YoY Growth
  const yoy = useOlapSection()
  const [yoyMeas, setYoyMeas] = useState('revenue')
  const [yoyDim, setYoyDim] = useState('')

  // Top N
  const topn = useOlapSection()
  const [topnN, setTopnN] = useState('5')
  const [topnDim, setTopnDim] = useState('region')
  const [topnMeas, setTopnMeas] = useState('revenue')
  const [topnYear, setTopnYear] = useState('')

  // Profit Margins
  const margins = useOlapSection()
  const [marginDim, setMarginDim] = useState('category')
  const [marginYear, setMarginYear] = useState('')

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      <p className="text-xs text-gray-400 mb-1">Execute OLAP operations directly against the data cube.</p>

      {/* Dimension Navigation */}
      <Section title="Dimension Navigation (Drill-Down / Roll-Up)">
        <div className="flex gap-3 items-center">
          <label className="text-xs text-gray-500">Operation</label>
          {(['drill-down', 'roll-up'] as const).map(op => (
            <label key={op} className="flex items-center gap-1 text-xs cursor-pointer">
              <input type="radio" checked={navOp === op} onChange={() => setNavOp(op)} />
              {op}
            </label>
          ))}
        </div>
        <Select label="Dimension" value={navDim} onChange={setNavDim} options={DIMENSIONS} />
        <RunButton
          onClick={() => nav.run(navOp, { dimension: navDim })}
          loading={nav.result.loading}
        />
        <ResultView result={nav.result} />
      </Section>

      {/* Slice */}
      <Section title="Slice (Single Filter)">
        <Select label="Dimension" value={sliceDim} onChange={setSliceDim} options={DIMENSIONS} />
        <Input label="Value" value={sliceVal} onChange={setSliceVal} />
        <Select label="Measure" value={sliceMeas} onChange={setSliceMeas} options={MEASURES} />
        <RunButton
          onClick={() => slice.run('slice', { dimension: sliceDim, value: sliceVal, measure: sliceMeas })}
          loading={slice.result.loading}
        />
        <ResultView result={slice.result} />
      </Section>

      {/* Dice */}
      <Section title="Dice (Multi-Dimension Filter)">
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 w-20">Region</label>
          <select
            value={diceRegion}
            onChange={e => setDiceRegion(e.target.value)}
            className="flex-1 text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-700"
          >
            <option value="">Any</option>
            {REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 w-20">Category</label>
          <select
            value={diceCat}
            onChange={e => setDiceCat(e.target.value)}
            className="flex-1 text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-700"
          >
            <option value="">Any</option>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 w-20">Year</label>
          <select
            value={diceYear}
            onChange={e => setDiceYear(e.target.value)}
            className="flex-1 text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-700"
          >
            <option value="">Any</option>
            {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <RunButton
          onClick={() => {
            const filters: Record<string, unknown> = {}
            if (diceRegion) filters.region = diceRegion
            if (diceCat) filters.category = diceCat
            if (diceYear) filters.year = parseInt(diceYear)
            dice.run('dice', { filters })
          }}
          loading={dice.result.loading}
        />
        <ResultView result={dice.result} />
      </Section>

      {/* Pivot */}
      <Section title="Pivot Table">
        <Select label="Row dim" value={pivotRows} onChange={setPivotRows} options={DIMENSIONS} />
        <Select label="Col dim" value={pivotCols} onChange={setPivotCols} options={DIMENSIONS} />
        <Select label="Measure" value={pivotMeas} onChange={setPivotMeas} options={MEASURES} />
        <RunButton
          onClick={() => pivot.run('pivot', { rows: pivotRows, columns: pivotCols, measure: pivotMeas })}
          loading={pivot.result.loading}
        />
        <ResultView result={pivot.result} />
      </Section>

      {/* YoY Growth */}
      <Section title="YoY Growth">
        <Select label="Measure" value={yoyMeas} onChange={setYoyMeas} options={MEASURES} />
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 w-20">Group by</label>
          <select
            value={yoyDim}
            onChange={e => setYoyDim(e.target.value)}
            className="flex-1 text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-700"
          >
            <option value="">Overall</option>
            {DIMENSIONS.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <RunButton
          onClick={() => {
            const body: Record<string, unknown> = { measure: yoyMeas }
            if (yoyDim) body.dimension = yoyDim
            yoy.run('yoy-growth', body)
          }}
          loading={yoy.result.loading}
        />
        <ResultView result={yoy.result} />
      </Section>

      {/* Top N */}
      <Section title="Top N Rankings">
        <Input label="N" value={topnN} onChange={setTopnN} type="number" />
        <Select label="Dimension" value={topnDim} onChange={setTopnDim} options={DIMENSIONS} />
        <Select label="Measure" value={topnMeas} onChange={setTopnMeas} options={MEASURES} />
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 w-20">Year</label>
          <select
            value={topnYear}
            onChange={e => setTopnYear(e.target.value)}
            className="flex-1 text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-700"
          >
            <option value="">All years</option>
            {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <RunButton
          onClick={() => {
            const body: Record<string, unknown> = {
              n: parseInt(topnN) || 5,
              dimension: topnDim,
              measure: topnMeas,
            }
            if (topnYear) body.year = parseInt(topnYear)
            topn.run('top-n', body)
          }}
          loading={topn.result.loading}
        />
        <ResultView result={topn.result} />
      </Section>

      {/* Profit Margins */}
      <Section title="Profit Margins">
        <Select label="Dimension" value={marginDim} onChange={setMarginDim} options={DIMENSIONS} />
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 w-20">Year</label>
          <select
            value={marginYear}
            onChange={e => setMarginYear(e.target.value)}
            className="flex-1 text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-700"
          >
            <option value="">All years</option>
            {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <RunButton
          onClick={() => {
            const body: Record<string, unknown> = { dimension: marginDim }
            if (marginYear) body.year = parseInt(marginYear)
            margins.run('profit-margins', body)
          }}
          loading={margins.result.loading}
        />
        <ResultView result={margins.result} />
      </Section>
    </div>
  )
}
