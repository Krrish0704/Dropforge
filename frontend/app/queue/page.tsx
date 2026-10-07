import Link from 'next/link'

type QueuePageProps = {
  searchParams: Promise<{ name?: string; position?: string; remaining?: string }>
}

export default async function QueuePage({ searchParams }: QueuePageProps) {
  const params = await searchParams
  const saleName = params.name || 'Live sale'
  const position = Number(params.position) || 5
  const remaining = Number(params.remaining) || 0

  return (
    <main className="min-h-screen bg-[#f4f3ef] text-black">
      <header className="border-b-2 border-black bg-white">
        <div className="mx-auto flex max-w-[1100px] items-center justify-between px-4 py-5 sm:px-8">
          <Link href="/" className="text-3xl font-black uppercase tracking-[-0.09em]">Dropforge<span className="text-neutral-500">/</span></Link>
          <Link href="/" className="border-2 border-black px-3 py-2 text-xs font-black uppercase">Back to sales</Link>
        </div>
      </header>
      <section className="mx-auto max-w-[1100px] px-4 py-12 sm:px-8 sm:py-20">
        <p className="mb-4 text-xs font-black uppercase tracking-[0.2em] text-neutral-500">Queue confirmation / entry accepted</p>
        <h1 className="max-w-3xl text-[clamp(3.5rem,10vw,8rem)] font-black uppercase leading-[0.8] tracking-[-0.1em]">You&apos;re<br /><span className="text-white [text-shadow:2px_2px_0_#000,-2px_-2px_0_#000]">in line.</span></h1>
        <div className="mt-12 grid gap-0 border-2 border-black bg-white sm:grid-cols-2">
          <div className="border-b-2 border-black p-6 sm:border-b-0 sm:border-r-2 sm:p-10">
            <p className="text-[10px] font-black uppercase tracking-[0.18em] text-neutral-500">Live sale</p>
            <h2 className="mt-3 text-3xl font-black uppercase leading-none">{saleName}</h2>
            <p className="mt-8 text-sm font-bold leading-relaxed">Your entry is recorded. We&apos;ll process the queue in order and update availability as pieces are assigned.</p>
          </div>
          <div className="grid grid-cols-2 bg-[#d9d9d4]">
            <div className="border-b-2 border-black p-6 sm:p-10"><p className="text-[10px] font-black uppercase tracking-[0.18em] text-neutral-600">Current rank</p><p className="mt-3 text-6xl font-black tracking-[-0.1em]">#{position}</p></div>
            <div className="border-b-2 border-l-2 border-black p-6 sm:p-10"><p className="text-[10px] font-black uppercase tracking-[0.18em] text-neutral-600">Pieces left</p><p className="mt-3 text-6xl font-black tracking-[-0.1em]">{remaining}</p></div>
            <div className="col-span-2 p-6 sm:p-10"><p className="text-[10px] font-black uppercase tracking-[0.18em] text-neutral-600">Status</p><p className="mt-3 text-xl font-black uppercase">Waiting to be processed</p></div>
          </div>
        </div>
        <Link href="/" className="mt-8 inline-flex border-2 border-black bg-black px-5 py-4 text-xs font-black uppercase tracking-[0.14em] text-white">Browse more live sales</Link>
      </section>
    </main>
  )
}
