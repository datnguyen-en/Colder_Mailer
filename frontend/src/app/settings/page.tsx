"use client"

import { CheckCircle2Icon, FileUpIcon, Loader2Icon } from "lucide-react"
import { Suspense, useRef, useState } from "react"
import { toast } from "sonner"

import { GmailCard } from "@/components/gmail-card"
import { ErrorAlert, PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { api, put, type Settings } from "@/lib/api"
import { useApi } from "@/lib/use-api"

// The signature is edited in its own dialog on the Template page.
type Form = Omit<Settings, "resume_uploaded" | "gmail_address" | "gmail_connected" | "signature">

const TIMEZONES = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : []

/** Same rule as the backend: strip everything but letters and digits. */
function exampleFilename(pattern: string, company = "Jane Street") {
  const slug = company.normalize("NFKD").replace(/[^A-Za-z0-9]/g, "")
  let name = pattern.replace(/\{company\}/gi, slug)
  if (!name.toLowerCase().endsWith(".pdf")) name += ".pdf"
  return name
}

export default function SettingsPage() {
  const { data, error, setData } = useApi<Settings>("/settings")
  const [form, setForm] = useState<Form | null>(null)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  // Fill the form once, when settings first load.
  if (data && !form) {
    setForm({
      sender_name: data.sender_name,
      resume_filename_pattern: data.resume_filename_pattern,
      daily_limit: data.daily_limit,
      send_window_start: data.send_window_start,
      send_window_end: data.send_window_end,
      send_days: data.send_days,
      timezone: data.timezone,
    })
  }

  async function save(e: React.FormEvent) {
    e.preventDefault()
    if (!form) return
    setSaving(true)
    try {
      const saved = await put<Settings>("/settings", form)
      setData(() => saved)
      toast.success("Settings saved")
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function upload(file: File) {
    if (file.size > 5 * 1024 * 1024) {
      toast.error("Resume must be 5 MB or smaller")
      return
    }
    setUploading(true)
    try {
      const body = new FormData()
      body.append("file", file)
      const saved = await api<Settings>("/resume", { method: "POST", body })
      setData(() => saved)
      toast.success("Resume uploaded")
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setUploading(false)
    }
  }

  const set = <K extends keyof Form>(key: K, value: Form[K]) => form && setForm({ ...form, [key]: value })

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow="Setup"
        title="Settings"
        description="Gmail connection, resume, and how fast emails go out."
      />
      {error && <ErrorAlert message={error} />}
      {!data && !error && <Skeleton className="h-96 w-full" />}
      {data && form && (
        <div className="space-y-6">
          <Suspense fallback={<Skeleton className="h-28 w-full" />}>
            <GmailCard />
          </Suspense>

          <Card>
            <CardHeader>
              <CardTitle>Resume</CardTitle>
              <CardDescription>
                PDF, up to 5 MB. Attached to every email as{" "}
                <span className="font-mono">{exampleFilename(form.resume_filename_pattern)}</span>.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center justify-between gap-3">
              {data.resume_uploaded ? (
                <span className="flex items-center gap-2 text-sm">
                  <CheckCircle2Icon className="size-4 text-emerald-600" /> Resume uploaded
                </span>
              ) : (
                <span className="text-sm text-muted-foreground">No resume yet</span>
              )}
              <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={uploading}>
                {uploading ? <Loader2Icon className="animate-spin" /> : <FileUpIcon />}
                {data.resume_uploaded ? "Replace" : "Upload"}
              </Button>
              <input
                ref={fileInput}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) upload(file)
                  e.target.value = ""
                }}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Sending</CardTitle>
              <CardDescription>
                Queued emails go out about one every 15 minutes, only inside this window.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="sender_name">Sender name</Label>
                  <Input id="sender_name" value={form.sender_name} placeholder="Eric Nguyen"
                    onChange={(e) => set("sender_name", e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="pattern">Resume filename</Label>
                  <Input id="pattern" value={form.resume_filename_pattern} className="font-mono"
                    onChange={(e) => set("resume_filename_pattern", e.target.value)} />
                  <p className="text-xs text-muted-foreground">{"{company}"} becomes the company name.</p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="daily_limit">Daily limit</Label>
                  <Input id="daily_limit" type="number" min={1} max={100} value={form.daily_limit}
                    onChange={(e) => set("daily_limit", Number(e.target.value))} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="send_days">Send days</Label>
                  <Input id="send_days" value={form.send_days} placeholder="Mon-Fri"
                    onChange={(e) => set("send_days", e.target.value)} />
                  <p className="text-xs text-muted-foreground">e.g. Mon-Fri or Mon,Wed,Fri</p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="start">Window start</Label>
                  <Input id="start" type="time" value={form.send_window_start}
                    onChange={(e) => set("send_window_start", e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="end">Window end</Label>
                  <Input id="end" type="time" value={form.send_window_end}
                    onChange={(e) => set("send_window_end", e.target.value)} />
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="timezone">Timezone</Label>
                  <Input id="timezone" list="timezones" value={form.timezone}
                    onChange={(e) => set("timezone", e.target.value)} />
                  <datalist id="timezones">
                    {TIMEZONES.map((tz) => <option key={tz} value={tz} />)}
                  </datalist>
                </div>
                <div className="sm:col-span-2">
                  <Button type="submit" disabled={saving}>
                    {saving && <Loader2Icon className="animate-spin" />} Save settings
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
