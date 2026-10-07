import { NextResponse } from 'next/server'
import { db, liveSales } from '@/lib/db'
import { eq, gt } from 'drizzle-orm'

const queue = new Map<number, number>()
const seededLiveSales = [
  { id: -1, name: 'Forge Runner 01', status: 'live', stock: 8 },
  { id: -2, name: 'Utility Shell Jacket', status: 'live', stock: 14 },
  { id: -3, name: 'Heavyweight Core Tee', status: 'live', stock: 31 },
  { id: -4, name: 'Transit Cargo Pant', status: 'live', stock: 12 },
  { id: -5, name: 'Studio Knit Hoodie', status: 'live', stock: 19 },
  { id: -6, name: 'Form Shoulder Bag', status: 'live', stock: 7 },
  { id: -7, name: 'Daily Frame Sunglasses', status: 'live', stock: 25 },
  { id: -8, name: 'Workshop Cap', status: 'live', stock: 42 },
]

export async function POST(request: Request) {
  const { saleId } = await request.json()
  if (!Number.isInteger(saleId)) return NextResponse.json({ error: 'A valid sale is required.' }, { status: 400 })
  const [storedSale] = await db.select().from(liveSales).where(eq(liveSales.id, saleId))
  const sale = storedSale || seededLiveSales.find((item) => item.id === saleId)
  if (!sale || sale.status !== 'live') return NextResponse.json({ error: 'This live sale is no longer available.' }, { status: 404 })
  const position = (queue.get(saleId) || 4) + 1
  queue.set(saleId, position)
  return NextResponse.json({ position, saleName: sale.name, remainingPieces: sale.stock, status: 'queued' })
}
