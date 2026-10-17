"use client"

import { CheckCircle2Icon, Loader2Icon, MailIcon, TriangleAlertIcon } from "lucide-react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, type GmailStatus } from "@/lib/api"
import { useApi } from "@/lib/use-api"

export function GmailCard() {
  const { data: status, error } = useApi<GmailStatus>("/gmail/status")
  const [busy, setBusy] = useState(false)
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()

  // Google redirects back to /settings?gmail=connected|error&message=...
  useEffect(() => {
    const result = params.get("gmail")
    if (!result) return
    if (result === "connected") toast.success("Gmail connected")
    else toast.error(params.get("message") ?? "Couldn't connect Gmail")
    router.replace(pathname)
  }, [params, router, pathname])

  async function connect() {
    setBusy(true)
    try {
      const { url } = await api<{ url: string }>("/gmail/connect")
      window.location.href = url // off to Google's consent screen
    } catch (e) {
      toast.error((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><MailIcon className="size-4" /> Gmail</CardTitle>
        <CardDescription>Emails are sent from your Gmail account. The app can only send, not read.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center justify-between gap-3">
        {error && <span className="text-sm text-destructive">{error}</span>}
        {status?.connected && (
          <span className="flex items-center gap-2 text-sm">
            <CheckCircle2Icon className="size-4 text-emerald-600" /> Connected as {status.address}
          </span>
        )}
        {status?.needs_reconnect && (
          <span className="flex items-center gap-2 text-sm text-destructive">
            <TriangleAlertIcon className="size-4" /> The connection to {status.address} stopped working. Sending is paused.
          </span>
        )}
        {status && !status.connected && !status.needs_reconnect && (
          <span className="text-sm text-muted-foreground">
            {status.oauth_configured ? "Not connected" : "Add your Google client ID and secret to .env first (see README)."}
          </span>
        )}
        {status && (
          <Button
            variant={status.connected ? "outline" : "default"}
            onClick={connect}
            disabled={busy || !status.oauth_configured}
          >
            {busy && <Loader2Icon className="animate-spin" />}
            {status.connected ? "Reconnect" : status.needs_reconnect ? "Reconnect Gmail" : "Connect Gmail"}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
