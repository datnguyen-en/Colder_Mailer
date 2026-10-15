import { supabase } from "@/lib/supabase"

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "")

export type ContactStatus =
  | "new" | "queued" | "sending" | "sent" | "replied" | "bounced" | "failed"

export const CONTACT_STATUSES: ContactStatus[] = [
  "new", "queued", "sending", "sent", "replied", "bounced", "failed",
]

export type PreviewRow = {
  email: string
  first_name: string | null
  last_name: string | null
  title: string | null
  domain: string | null
  company_name: string | null
  flags: string[]
}

export type ImportResult = {
  created: number
  skipped: number
  skipped_rows: { email: string; reason: string }[]
}

export type Contact = {
  id: number
  email: string
  first_name: string | null
  last_name: string | null
  title: string | null
  company_id: number | null
  company_name: string | null
  source: string
  status: ContactStatus
  queued_at: string | null
  sent_at: string | null
  gmail_message_id: string | null
  gmail_thread_id: string | null
  error: string | null
  stuck: boolean
  created_at: string
  updated_at: string
}

export type ContactPage = { items: Contact[]; total: number; page: number; page_size: number }

export type EmailPreview = {
  subject: string
  body: string
  attachment_name: string
  to: string | null
  problems: string[]
}

export type Company = {
  id: number
  name: string
  domain: string | null
  notes: string | null
  aliases: string[]
  contact_count: number
  status_counts: Partial<Record<ContactStatus, number>>
  last_contacted_at: string | null
  created_at: string
}

export type Template = {
  id: number
  name: string
  subject: string
  body: string
  is_default: boolean
  updated_at: string
}

export type Settings = {
  sender_name: string
  resume_uploaded: boolean
  resume_filename_pattern: string
  daily_limit: number
  send_window_start: string
  send_window_end: string
  send_days: string
  timezone: string
  gmail_address: string | null
  gmail_connected: boolean
}

export type Stats = {
  sent_today: number
  sent_this_week: number
  total_companies: number
  total_contacts: number
  replies: number
  reply_rate: number
  status_counts: Partial<Record<ContactStatus, number>>
  sends_per_day: { date: string; sent: number }[]
  recent_activity: {
    id: number
    contact_id: number
    email: string
    company_name: string | null
    event: string
    detail: string | null
    created_at: string
  }[]
  stuck_sending: number
  warnings: string[]
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

/** FastAPI errors are `{detail: string}` or `{detail: [{msg, loc}]}` for validation. */
function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const field = d.loc?.filter((p) => p !== "body").join(".")
        return field ? `${field}: ${d.msg}` : d.msg
      })
      .join("; ")
  }
  return fallback
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json")
  if (supabase) {
    const { data } = await supabase.auth.getSession()
    if (data.session) headers.set("Authorization", `Bearer ${data.session.access_token}`)
  }

  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, `Can't reach the API at ${API_URL}. Is the backend running?`)
  }

  if (res.status === 401 && supabase) {
    await supabase.auth.signOut() // AppShell sees the session end and goes to /login
  }
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, errorMessage(body, `Request failed (${res.status})`))
  return body as T
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) })

export const put = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(body) })

export const patch = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) })

export const del = (path: string) => api<void>(path, { method: "DELETE" })
