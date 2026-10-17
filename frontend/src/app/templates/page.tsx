"use client"

import { Loader2Icon, PenLineIcon, PlusIcon, StarIcon } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import { ConfirmDialog } from "@/components/confirm-dialog"
import { EmailPreviewView } from "@/components/email-preview"
import { ErrorAlert, PageHeader } from "@/components/page-header"
import { RichTextEditor, type RichTextHandle } from "@/components/rich-text-editor"
import { SignatureDialog } from "@/components/signature-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  post,
  put,
  type ContactPage,
  type EmailPreview,
  type Settings,
  type Template,
} from "@/lib/api"
import { useApi } from "@/lib/use-api"
import { cn } from "@/lib/utils"

const TOKENS = [
  { token: "[Name]", hint: "First name" },
  { token: "[FullName]", hint: "First + last name" },
  { token: "[Company]", hint: "Company name" },
  { token: "[Title]", hint: "Job title" },
]

const STARTER = {
  name: "Main",
  subject: "Software engineering internship at [Company]",
  body: "<p>Hi [Name],</p><p>I'm a computer science student and I'd love to be considered for a software engineering internship at [Company].</p><p>My resume is attached. Thanks for your time!</p><p>Best,<br>Eric</p>",
  is_default: false,
}

type Draft = typeof STARTER
type Field = "subject" | "body"

// Cold emails that get replies are short; nudge, don't block.
const WORD_TARGET = 125
const countWords = (text: string) => text.trim().split(/\s+/).filter(Boolean).length

export default function TemplatesPage() {
  const templates = useApi<Template[]>("/templates")
  const contacts = useApi<ContactPage>("/contacts?page_size=200")
  const settings = useApi<Settings>("/settings")
  const [signatureOpen, setSignatureOpen] = useState(false)
  const [words, setWords] = useState(0)
  const [editingId, setEditingId] = useState<number | "new" | null>(null)
  const [draft, setDraft] = useState<Draft>(STARTER)
  // What the draft looked like when opened or last saved, to spot unsaved edits.
  const [cleanDraft, setCleanDraft] = useState<Draft>(STARTER)
  const [pendingSwitch, setPendingSwitch] = useState<number | "new" | null>(null)
  const [saving, setSaving] = useState(false)
  const [contactId, setContactId] = useState<string | null>(null)
  const [preview, setPreview] = useState<EmailPreview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const subjectRef = useRef<HTMLInputElement>(null)
  const bodyRef = useRef<RichTextHandle>(null)
  const lastField = useRef<Field>("body")

  // Once templates load, open the default one (or a starter draft for the first template).
  if (templates.data && editingId === null) {
    const first = templates.data.find((t) => t.is_default) ?? templates.data[0]
    if (first) open(first)
    else setEditingId("new")
  }

  const firstContact = contacts.data?.items[0]
  const previewContactId = contactId ?? (firstContact ? String(firstContact.id) : null)
  const signature = settings.data?.signature ?? ""

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
  }, [draft.subject, draft.body, previewContactId, signature])

  function open(t: Template) {
    const next = { name: t.name, subject: t.subject, body: t.body, is_default: t.is_default }
    setEditingId(t.id)
    setDraft(next)
    setCleanDraft(next)
  }

  function startNew() {
    const next = { ...STARTER, name: "" }
    setEditingId("new")
    setDraft(next)
    setCleanDraft(next)
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(cleanDraft)

  function switchTo(target: number | "new") {
    if (target === "new") startNew()
    else {
      const t = templates.data?.find((x) => x.id === target)
      if (t) open(t)
    }
  }

  /** From the template box: switch, but ask first if that would drop unsaved edits. */
  function choose(value: string | null) {
    if (value === null) return
    const target = value === "new" ? "new" : Number(value)
    if (target === editingId) return
    if (dirty) setPendingSwitch(target)
    else switchTo(target)
  }

  function insertToken(token: string) {
    if (lastField.current === "body") {
      bodyRef.current?.insertText(token)
      return
    }
    const el = subjectRef.current
    const value = draft.subject
    const start = el?.selectionStart ?? value.length
    const end = el?.selectionEnd ?? value.length
    setDraft({ ...draft, subject: value.slice(0, start) + token + value.slice(end) })
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
      const next = { ...draft, is_default: saved.is_default }
      setDraft(next)
      setCleanDraft(next)
      toast.success(saved.is_default ? "Saved as the default template" : "Saved")
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const templateItems = [
    ...(templates.data ?? []).map((t) => ({ value: String(t.id), label: t.name, isDefault: t.is_default })),
    { value: "new", label: "New template", isDefault: false },
  ]

  const contactItems = (contacts.data?.items ?? []).map((c) => ({
    value: String(c.id),
    label: `${[c.first_name, c.last_name].filter(Boolean).join(" ") || c.email}${c.company_name ? ` · ${c.company_name}` : ""}`,
  }))

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        eyebrow="Your email"
        title="Email template"
        description="Keep as many templates as you like and pick one from the box. The default one is what every email uses."
      />
      {templates.error && <ErrorAlert message={templates.error} />}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <p className="eyebrow">Template</p>
            <div className="flex flex-wrap items-center gap-2">
              <Select
                items={templateItems}
                value={editingId === null ? null : String(editingId)}
                onValueChange={choose}
              >
                <SelectTrigger className="w-72 max-w-full" aria-label="Choose a template"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {templateItems.filter((t) => t.value !== "new").map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                      {t.isDefault && <StarIcon className="fill-current text-muted-foreground" aria-label="default" />}
                    </SelectItem>
                  ))}
                  {(templates.data?.length ?? 0) > 0 && <SelectSeparator />}
                  <SelectItem value="new"><PlusIcon /> New template</SelectItem>
                </SelectContent>
              </Select>
              {draft.is_default && <Badge variant="secondary">Default</Badge>}
              {dirty && <span className="text-xs text-muted-foreground">Unsaved changes</span>}
            </div>
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
              <Label>Body</Label>
              <RichTextEditor
                ariaLabel="Email body"
                ref={bodyRef}
                value={draft.body}
                onFocus={() => (lastField.current = "body")}
                onChange={(body) => setDraft((d) => ({ ...d, body }))}
                onTextChange={(text) => setWords(countWords(text))}
                toolbarExtra={
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setSignatureOpen(true)}
                    title="Edit the signature added to every email"
                  >
                    <PenLineIcon /> Signature
                  </Button>
                }
              />
              <p className={cn("text-xs", words > WORD_TARGET ? "text-amber-700" : "text-muted-foreground")}>
                {words} {words === 1 ? "word" : "words"} ·{" "}
                {words > WORD_TARGET ? "long for a cold email, aim for under " : "aim for under "}{WORD_TARGET}
                {signature ? " · signature added at the end" : " · no signature yet"}
              </p>
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

      <ConfirmDialog
        open={pendingSwitch !== null}
        onOpenChange={(o) => !o && setPendingSwitch(null)}
        title="Discard unsaved changes?"
        description="Your edits to this template haven't been saved. Switching templates will throw them away."
        confirmLabel="Discard and switch"
        onConfirm={() => {
          if (pendingSwitch !== null) switchTo(pendingSwitch)
          setPendingSwitch(null)
        }}
      />

      <SignatureDialog
        open={signatureOpen}
        onOpenChange={setSignatureOpen}
        signature={signature}
        onSaved={(saved) => settings.setData(() => saved)}
      />
    </div>
  )
}
