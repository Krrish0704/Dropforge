'use client'

import { FormEvent, useEffect, useState } from 'react'

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

type Sale = { id: number; name: string; category: string; priceInr: number; stock: number; status: string }

export default function AdminPage() {
  const [sales, setSales] = useState<Sale[]>([])
  const [form, setForm] = useState({ name: '', category: 'Footwear', priceInr: '', stock: '' })
  const [message, setMessage] = useState('')

  async function load() {
    const response = await fetch('/api/sales', { cache: 'no-store' })
    setSales(await response.json())
  }

  useEffect(() => { load() }, [])

  async function createSale(event: FormEvent) {
    event.preventDefault()
    setMessage('')
    const response = await fetch('/api/sales', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...form, priceInr: Number(form.priceInr), stock: Number(form.stock) }) })
    if (!response.ok) { const data = await response.json(); setMessage(data.error || 'Could not create sale.'); return }
    setForm({ name: '', category: 'Footwear', priceInr: '', stock: '' })
    setMessage('Live sale published.')
    load()
  }

  return <main className="min-h-screen bg-[#f4f0e8] px-4 py-6 text-[#171717] sm:px-8">
    <div className="mx-auto max-w-6xl">
      <header className="mb-10 flex flex-col justify-between gap-5 border-b-4 border-[#171717] pb-6 sm:flex-row sm:items-end">
        <div><p className="font-mono text-xs font-bold uppercase tracking-[0.25em]">Dropforge / Control room</p><h1 className="mt-2 text-5xl font-black uppercase tracking-[-0.06em]">Live sales admin</h1></div>
        <a href="/" className="border-2 border-[#171717] bg-white px-5 py-3 text-center text-xs font-black uppercase shadow-[4px_4px_0_#171717]">View storefront</a>
      </header>
      <div className="grid gap-8 lg:grid-cols-[360px_1fr]">
        <form onSubmit={createSale} className="h-fit border-4 border-[#171717] bg-white p-5 shadow-[8px_8px_0_#171717]">
          <h2 className="mb-5 text-2xl font-black uppercase">Add live sale</h2>
          <div className="flex flex-col gap-4">
            {(['name', 'category', 'priceInr', 'stock'] as const).map((field) => <label key={field} className="font-mono text-xs font-bold uppercase">{field === 'priceInr' ? 'Price (INR)' : field}<input required value={form[field]} onChange={(e) => setForm({ ...form, [field]: e.target.value })} type={field === 'priceInr' || field === 'stock' ? 'number' : 'text'} className="mt-2 w-full border-2 border-[#171717] bg-[#f4f0e8] px-3 py-3 font-sans text-base outline-none focus:bg-white" /></label>)}
            <button className="mt-2 border-2 border-[#171717] bg-[#171717] px-4 py-4 text-sm font-black uppercase text-white hover:bg-white hover:text-[#171717]">Publish sale</button>
            {message && <p className="font-mono text-xs font-bold uppercase">{message}</p>}
          </div>
        </form>
        <section><div className="mb-4 flex items-baseline justify-between"><h2 className="text-2xl font-black uppercase">Current drops</h2><span className="font-mono text-xs font-bold uppercase">{sales.length} live</span></div><div className="grid gap-4 sm:grid-cols-2">{sales.map((sale) => <article key={sale.id} className="border-4 border-[#171717] bg-white p-5 shadow-[5px_5px_0_#171717]"><div className="flex justify-between gap-4"><p className="font-mono text-xs font-bold uppercase">{sale.category}</p><span className="bg-white px-2 py-1 font-mono text-[10px] font-bold uppercase">{sale.status}</span></div><h3 className="mt-8 text-2xl font-black uppercase">{sale.name}</h3><div className="mt-5 flex justify-between border-t-2 border-[#171717] pt-4 font-mono text-xs font-bold uppercase"><span>{money.format(sale.priceInr)}</span><span>{sale.stock} units</span></div></article>)}</div></section>
      </div>
    </div>
  </main>
}
