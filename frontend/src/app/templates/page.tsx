"use client"

import { Loader2Icon, PlusIcon, StarIcon } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import { EmailPreviewView } from "@/components/email-preview"
import { ErrorAlert, PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import {
  post,
  put,
  type ContactPage,
  type EmailPreview,
  type Template,
} from "@/lib/api"
import { useApi } from "@/lib/use-api"

const TOKENS = [
  { token: "[Name]", hint: "First name" },
  { token: "[FullName]", hint: "First + last name" },
  { token: "[Company]", hint: "Company name" },
  { token: "[Title]", hint: "Job title" },
]

const STARTER = {
  name: "Main",
  subject: "Software engineering internship at [Company]",
  body: "Hi [Name],\n\nI'm a computer science student and I'd love to be considered for a software engineering internship at [Company]. ...\n\nMy resume is attached. Thanks for your time!\n\nBest,\nEric",
  is_default: false,
}

type Draft = typeof STARTER
type Field = "subject" | "body"

export default function TemplatesPage() {
  const templates = useApi<Template[]>("/templates")
  const contacts = useApi<ContactPage>("/contacts?page_size=200")
  const [editingId, setEditingId] = useState<number | "new" | null>(null)
  const [draft, setDraft] = useState<Draft>(STARTER)
  const [saving, setSaving] = useState(false)
  const [contactId, setContactId] = useState<string | null>(null)
  const [preview, setPreview] = useState<EmailPreview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const subjectRef = useRef<HTMLInputElement>(null)
  const bodyRef = useRef<HTMLTextAreaElement>(null)
  const lastField = useRef<Field>("body")

  // Once templates load, open the default one (or a starter draft for the first template).
  if (templates.data && editingId === null) {
    const first = templates.data.find((t) => t.is_default) ?? templates.data[0]
    if (first) open(first)
    else setEditingId("new")
  }

  const firstContact = contacts.data?.items[0]
  const previewContactId = contactId ?? (firstContact ? String(firstContact.id) : null)

  // Live preview, debounced while typing.
  useEffect(() => {
    if (!previewContactId) return
    const t = setTimeout(() => {
      post<EmailPreview>("/templates/preview", {
        subject: draft.subject,
        body: draft.body,
        contact_id: Number(previewContactId),
      })
        .then((p) => {
          setPreview(p)
          setPreviewError(null)
        })
        .catch((e: Error) => setPreviewError(e.message))
    }, 300)
    return () => clearTimeout(t)
  }, [draft.subject, draft.body, previewContactId])

  function open(t: Template) {
    setEditingId(t.id)
    setDraft({ name: t.name, subject: t.subject, body: t.body, is_default: t.is_default })
  }

  function insertToken(token: string) {
    const field = lastField.current
    const el = field === "subject" ? subjectRef.current : bodyRef.current
    const value = draft[field]
    const start = el?.selectionStart ?? value.length
    const end = el?.selectionEnd ?? value.length
    setDraft({ ...draft, [field]: value.slice(0, start) + token + value.slice(end) })
    requestAnimationFrame(() => {
      el?.focus()
      el?.setSelectionRange(start + token.length, start + token.length)
    })
  }

  async function save(makeDefault = draft.is_default) {
    setSaving(true)
    try {
      const body = { ...draft, is_default: makeDefault }
      const saved = editingId === "new" || editingId === null
        ? await post<Template>("/templates", body)
        : await put<Template>(`/templates/${editingId}`, body)
      templates.reload()
      setEditingId(saved.id)
      setDraft({ ...draft, is_default: saved.is_default })
      toast.success(saved.is_default ? "Saved as the default template" : "Saved")
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const contactItems = (contacts.data?.items ?? []).map((c) => ({
    value: String(c.id),
    label: `${[c.first_name, c.last_name].filter(Boolean).join(" ") || c.email}${c.company_name ? ` · ${c.company_name}` : ""}`,
  }))

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Email template"
        description="The default template is what every email uses. Tokens are filled in per contact."
      >
        {(templates.data?.length ?? 0) > 0 && (
          <Button variant="outline" onClick={() => { setEditingId("new"); setDraft({ ...STARTER, name: "" }) }}>
            <PlusIcon /> New template
          </Button>
        )}
      </PageHeader>
      {templates.error && <ErrorAlert message={templates.error} />}

      {(templates.data?.length ?? 0) > 1 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {templates.data!.map((t) => (
            <Button key={t.id} size="sm" variant={editingId === t.id ? "secondary" : "ghost"} onClick={() => open(t)}>
              {t.is_default && <StarIcon className="fill-current" />} {t.name}
            </Button>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {editingId === "new" ? "New template" : "Edit template"}
              {draft.is_default && <Badge variant="secondary">Default</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="name">Template name</Label>
              <Input id="name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="subject">Subject</Label>
              <Input
                id="subject"
                ref={subjectRef}
                value={draft.subject}
                onFocus={() => (lastField.current = "subject")}
                onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="body">Body</Label>
              <Textarea
                id="body"
                ref={bodyRef}
                value={draft.body}
                onFocus={() => (lastField.current = "body")}
                onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                className="min-h-72 text-sm"
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">Insert:</span>
              {TOKENS.map((t) => (
                <Button key={t.token} size="xs" variant="outline" title={t.hint}
                  onMouseDown={(e) => e.preventDefault()} onClick={() => insertToken(t.token)}>
                  {t.token}
                </Button>
              ))}
            </div>
            <div className="flex flex-wrap gap-2 border-t pt-4">
              <Button onClick={() => save()} disabled={saving || !draft.name.trim() || !draft.subject.trim() || !draft.body.trim()}>
                {saving && <Loader2Icon className="animate-spin" />} Save
              </Button>
              {!draft.is_default && editingId !== "new" && (
                <Button variant="outline" onClick={() => save(true)} disabled={saving}>
                  <StarIcon /> Save & make default
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
            <CardTitle>Live preview</CardTitle>
            {contactItems.length > 0 && (
              <Select items={contactItems} value={previewContactId} onValueChange={(v) => setContactId(v)}>
                <SelectTrigger className="w-64 max-w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {contactItems.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
          </CardHeader>
          <CardContent>
            {contactItems.length === 0 && contacts.data && (
              <p className="text-sm text-muted-foreground">Import a contact to preview the template against real data.</p>
            )}
            {previewError && <p className="text-sm text-destructive">{previewError}</p>}
            {preview && contactItems.length > 0 && <EmailPreviewView preview={preview} />}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
