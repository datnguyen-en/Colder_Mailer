"use client"

import { TriangleAlertIcon } from "lucide-react"
import Link from "next/link"

import { ErrorAlert, PageHeader } from "@/components/page-header"
import { SendsChart } from "@/components/sends-chart"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { Stats } from "@/lib/api"
import { percent, timeAgo } from "@/lib/format"
import { useApi } from "@/lib/use-api"

const WARNINGS: Record<string, { title: string; body: string; href: string; action: string }> = {
  gmail_disconnected: {
    title: "Gmail isn't connected",
    body: "Nothing can be sent until you connect Gmail.",
    href: "/settings",
    action: "Open settings",
  },
  gmail_reconnect: {
    title: "Gmail needs reconnecting",
    body: "The connection stopped working, so sending is paused. Queued emails will go out once you reconnect.",
    href: "/settings",
    action: "Reconnect",
  },
  no_resume: {
    title: "No resume uploaded",
    body: "Every email attaches your resume, so sending is blocked without one.",
    href: "/settings",
    action: "Upload resume",
  },
  no_default_template: {
    title: "No email template yet",
    body: "Write the template that gets filled in for each contact.",
    href: "/templates",
    action: "Write template",
  },
  stuck_sending: {
    title: "Some sends are stuck",
    body: "Gmail didn't clearly confirm some sends. Check Gmail's Sent folder before requeueing, so nobody gets two emails.",
    href: "/contacts?status=sending",
    action: "Review",
  },
}

const EVENT_TEXT: Record<string, string> = {
  queued: "queued",
  sent: "sent",
  failed: "failed",
  replied: "replied",
  bounced: "bounced",
  requeued: "requeued",
  unqueued: "removed from queue",
}

function StatTile({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Card size="sm">
      <CardHeader>
        <p className="eyebrow">{label}</p>
      </CardHeader>
      <CardContent>
        <div className="text-4xl font-medium tracking-tight tabular-nums">{value}</div>
        {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const { data: stats, error } = useApi<Stats>("/stats")

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        description="This week's sends and replies, and anything that needs your attention."
      />
      {error && <ErrorAlert message={error} />}
      {!stats && !error && <Skeleton className="h-64 w-full" />}
      {stats && (
        <div className="space-y-6">
          {stats.warnings.length > 0 && (
            <div className="grid gap-3 md:grid-cols-2">
              {stats.warnings.map((w) => WARNINGS[w] && (
                <Alert key={w}>
                  <TriangleAlertIcon />
                  <AlertTitle>{WARNINGS[w].title}</AlertTitle>
                  <AlertDescription>
                    {WARNINGS[w].body}{" "}
                    <Link href={WARNINGS[w].href} className="font-medium underline">
                      {WARNINGS[w].action}
                    </Link>
                  </AlertDescription>
                </Alert>
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Sent this week" value={stats.sent_this_week} hint={`${stats.sent_today} today`} />
            <StatTile label="Companies" value={stats.total_companies} hint={`${stats.total_contacts} contacts`} />
            <StatTile label="Replies" value={stats.replies} />
            <StatTile
              label="Reply rate"
              value={percent(stats.reply_rate)}
              hint="of contacts emailed"
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <Card>
              <CardHeader>
                <CardTitle>Emails sent per day</CardTitle>
              </CardHeader>
              <CardContent>
                <SendsChart days={stats.sends_per_day} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Recent activity</CardTitle>
              </CardHeader>
              <CardContent>
                {stats.recent_activity.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Nothing yet. <Link href="/import" className="underline">Import some contacts</Link> to get started.
                  </p>
                ) : (
                  <ul className="space-y-3 text-sm">
                    {stats.recent_activity.map((a) => (
                      <li key={a.id} className="flex items-baseline justify-between gap-3">
                        <span className="min-w-0">
                          <span className="block truncate font-medium">{a.email}</span>
                          <span className="text-muted-foreground">
                            {EVENT_TEXT[a.event] ?? a.event}
                            {a.company_name && ` · ${a.company_name}`}
                          </span>
                        </span>
                        <span className="shrink-0 text-xs text-muted-foreground">{timeAgo(a.created_at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
