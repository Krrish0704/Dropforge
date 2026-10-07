import { drizzle } from 'drizzle-orm/node-postgres'
import { pgTable, bigserial, integer, text, timestamp } from 'drizzle-orm/pg-core'
import { Pool } from 'pg'

export const liveSales = pgTable('live_sales', {
  id: bigserial('id', { mode: 'number' }).primaryKey(),
  name: text('name').notNull(),
  category: text('category').notNull(),
  priceInr: integer('price_inr').notNull(),
  stock: integer('stock').notNull().default(0),
  status: text('status').notNull().default('live'),
  accent: text('accent').notNull().default('bg-zinc-950'),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
})

export const pool = new Pool({ connectionString: process.env.DATABASE_URL })
export const db = drizzle(pool, { schema: { liveSales } })
