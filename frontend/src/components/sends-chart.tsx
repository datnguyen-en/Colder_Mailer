"use client"

import { useState } from "react"

type Day = { date: string; sent: number }

const label = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })

/** Column chart of sends per day. One series, so no legend: the card title names it. */
export function SendsChart({ days }: { days: Day[] }) {
  const [active, setActive] = useState<number | null>(null)
  const max = Math.max(1, ...days.map((d) => d.sent))
  // A round top tick so the gridline label is a clean number.
  const top = max <= 5 ? max : Math.ceil(max / 5) * 5
  const total = days.reduce((sum, d) => sum + d.sent, 0)

  return (
    <div>
      <div className="relative flex h-44 gap-2">
        {/* Recessive y-axis: just the top value and zero. */}
        <div className="flex w-6 flex-col justify-between text-right text-[11px] tabular-nums text-muted-foreground">
          <span className="-translate-y-1/2">{top}</span>
          <span className="translate-y-1/2">0</span>
        </div>
        <div className="relative flex-1">
          <div className="absolute inset-x-0 top-0 border-t border-dashed border-border" />
          <div className="absolute inset-x-0 bottom-0 border-t border-border" />
          <div className="absolute inset-0 flex items-end" onMouseLeave={() => setActive(null)}>
            {days.map((d, i) => (
              <div
                key={d.date}
                tabIndex={0}
                role="img"
                aria-label={`${label(d.date)}: ${d.sent} sent`}
                className="group relative flex h-full flex-1 items-end justify-center px-px outline-none"
                onMouseEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
              >
                <div
                  className="w-full max-w-6 rounded-t-md bg-bar transition-opacity group-hover:opacity-80 group-focus-visible:ring-2 group-focus-visible:ring-ring"
                  style={{ height: d.sent ? `${(d.sent / top) * 100}%` : 0 }}
                />
                {active === i && (
                  <div
                    className="pointer-events-none absolute bottom-full z-10 mb-1 rounded-xl border bg-popover px-2.5 py-1.5 text-xs whitespace-nowrap text-popover-foreground shadow-soft"
                    style={{
                      left: i < 3 ? 0 : i > days.length - 4 ? "auto" : "50%",
                      right: i > days.length - 4 ? 0 : "auto",
                      transform: i < 3 || i > days.length - 4 ? undefined : "translateX(-50%)",
                    }}
                  >
                    <div className="text-muted-foreground">{label(d.date)}</div>
                    <div className="font-medium tabular-nums">{d.sent} sent</div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-1 ml-8 flex justify-between text-[11px] text-muted-foreground">
        <span>{days[0] && label(days[0].date)}</span>
        <span>{days[14] && label(days[14].date)}</span>
        <span>{days.at(-1) && label(days.at(-1)!.date)}</span>
      </div>
      {total === 0 && (
        <p className="mt-2 text-center text-sm text-muted-foreground">No emails sent in the last 30 days.</p>
      )}
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-muted-foreground">Show as table</summary>
        <table className="mt-2 w-full max-w-xs text-left text-xs">
          <thead>
            <tr className="text-muted-foreground">
              <th className="py-1 font-normal">Date</th>
              <th className="py-1 text-right font-normal">Sent</th>
            </tr>
          </thead>
          <tbody>
            {days.filter((d) => d.sent > 0).map((d) => (
              <tr key={d.date} className="border-t">
                <td className="py-1">{label(d.date)}</td>
                <td className="py-1 text-right tabular-nums">{d.sent}</td>
              </tr>
            ))}
            {total === 0 && (
              <tr className="border-t"><td colSpan={2} className="py-1 text-muted-foreground">No sends</td></tr>
            )}
          </tbody>
        </table>
      </details>
    </div>
  )
}
