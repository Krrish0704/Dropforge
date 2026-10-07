import { NextResponse } from 'next/server'
import { asc } from 'drizzle-orm'
import { db, liveSales } from '@/lib/db'

const fallbackSales = [
  { name: 'Forge Runner 01', category: 'Footwear', priceInr: 14999, stock: 8, accent: 'bg-zinc-950' },
  { name: 'Utility Shell Jacket', category: 'Outerwear', priceInr: 19999, stock: 14, accent: 'bg-stone-200' },
  { name: 'Heavyweight Core Tee', category: 'Tops', priceInr: 4999, stock: 31, accent: 'bg-zinc-700' },
  { name: 'Transit Cargo Pant', category: 'Bottoms', priceInr: 10499, stock: 12, accent: 'bg-stone-400' },
  { name: 'Studio Knit Hoodie', category: 'Tops', priceInr: 12999, stock: 19, accent: 'bg-neutral-800' },
  { name: 'Form Shoulder Bag', category: 'Accessories', priceInr: 7499, stock: 7, accent: 'bg-neutral-100' },
  { name: 'Daily Frame Sunglasses', category: 'Accessories', priceInr: 5999, stock: 25, accent: 'bg-black' },
  { name: 'Workshop Cap', category: 'Accessories', priceInr: 3999, stock: 42, accent: 'bg-stone-300', status: 'live' },
  { name: 'Signal Track Jacket', category: 'Outerwear', priceInr: 16999, stock: 18, accent: 'bg-stone-300', status: 'upcoming' },
  { name: 'Archive Logo Tee', category: 'Tops', priceInr: 3999, stock: 0, accent: 'bg-neutral-200', status: 'closed' },
]

export async function GET() {
  const storedSales = await db.select().from(liveSales).orderBy(asc(liveSales.id))
  const storedNames = new Set(storedSales.map((sale) => sale.name.toLowerCase()))
  const seededSales = fallbackSales
    .filter((sale) => !storedNames.has(sale.name.toLowerCase()))
    .map((sale, index) => ({ ...sale, id: -(index + 1), status: sale.status || 'live' }))
  return NextResponse.json([...storedSales, ...seededSales])
}

export async function POST(request: Request) {
  const body = await request.json()
  if (!body.name || !body.category || !Number.isInteger(body.priceInr) || body.priceInr <= 0 || !Number.isInteger(body.stock) || body.stock < 0) {
    return NextResponse.json({ error: 'Name, category, positive rupee price, and stock are required.' }, { status: 400 })
  }
  const [sale] = await db.insert(liveSales).values({ name: body.name.trim(), category: body.category.trim(), priceInr: body.priceInr, stock: body.stock, accent: body.accent || 'bg-zinc-950' }).returning()
  return NextResponse.json(sale, { status: 201 })
}
