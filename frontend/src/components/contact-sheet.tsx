"use client"

import { Loader2Icon, SendIcon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { StatusBadge } from "@/components/badges"
import { EmailPreviewView } from "@/components/email-preview"
import { defaultLabel, TemplatePicker } from "@/components/template-picker"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { patch, type Company, type Contact, type EmailPreview, type Template } from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import { useApi } from "@/lib/use-api"

const NO_COMPANY = "none"

/** Drawer: edit a contact and see the exact email it would get. */
export function ContactSheet({
  contact,
  companies,
  onClose,
  onSaved,
  onSendNow,
}: {
  contact: Contact | null
  companies: Company[]
  onClose: () => void
  onSaved: (contact: Contact) => void
  onSendNow: (contact: Contact) => void
}) {
  return (
    <Sheet open={contact !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl data-[side=right]:sm:max-w-xl">
        {contact && (
          <ContactDetails key={contact.id} contact={contact} companies={companies}
            onSaved={onSaved} onSendNow={onSendNow} />
        )}
      </SheetContent>
    </Sheet>
  )
}

function ContactDetails({
  contact,
  companies,
  onSaved,
  onSendNow,
}: {
  contact: Contact
  companies: Company[]
  onSaved: (contact: Contact) => void
  onSendNow: (contact: Contact) => void
}) {
  const [form, setForm] = useState({
    first_name: contact.first_name ?? "",
    last_name: contact.last_name ?? "",
    title: contact.title ?? "",
    company_id: contact.company_id ? String(contact.company_id) : NO_COMPANY,
  })
  const [saving, setSaving] = useState(false)
  const preview = useApi<EmailPreview>(`/contacts/${contact.id}/preview`)
  const { reload } = preview
  const templates = useApi<Template[]>("/templates")
  const templateList = templates.data ?? []
  const companyTemplate = templateList.find((t) => t.id === contact.company_template_id)
  // Who still gets an email; for anyone already emailed the choice no longer matters.
  const canStillSend = ["new", "queued", "failed"].includes(contact.status)

  async function setTemplate(templateId: number | null) {
    try {
      onSaved(await patch<Contact>(`/contacts/${contact.id}`, { template_id: templateId }))
      reload()
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await patch<Contact>(`/contacts/${contact.id}`, {
        first_name: form.first_name,
        last_name: form.last_name,
        title: form.title,
        company_id: form.company_id === NO_COMPANY ? null : Number(form.company_id),
      })
      onSaved(updated)
      reload()
      toast.success("Saved")
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const companyItems = [
    { value: NO_COMPANY, label: "No company" },
    ...companies.map((c) => ({ value: String(c.id), label: c.name })),
  ]

  return (
    <>
      <SheetHeader>
        <SheetTitle className="break-all">{contact.email}</SheetTitle>
        <SheetDescription className="flex flex-wrap items-center gap-2">
          <StatusBadge status={contact.status} stuck={contact.stuck} />
          {contact.sent_at && <span>Sent {formatDateTime(contact.sent_at)}</span>}
          {contact.error && <span className="text-destructive">{contact.error}</span>}
        </SheetDescription>
      </SheetHeader>
      <div className="space-y-6 px-4 pb-6">
        <form onSubmit={save} className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label htmlFor="first_name">First name</Label>
            <Input id="first_name" value={form.first_name}
              onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="last_name">Last name</Label>
            <Input id="last_name" value={form.last_name}
              onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="title">Title</Label>
            <Input id="title" value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>Company</Label>
            <Select
              items={companyItems}
              value={form.company_id}
              onValueChange={(v) => setForm({ ...form, company_id: v ?? NO_COMPANY })}
            >
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {companyItems.map((c) => (
                  <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Button type="submit" size="sm" disabled={saving}>
              {saving && <Loader2Icon className="animate-spin" />} Save
            </Button>
          </div>
        </form>

        <div className="space-y-1">
          <Label>Template</Label>
          <TemplatePicker
            templates={templateList}
            value={contact.template_id}
            fallbackLabel={companyTemplate
              ? `Same as ${contact.company_name ?? "company"} · ${companyTemplate.name}`
              : defaultLabel(templateList)}
            onChange={setTemplate}
            disabled={!templates.data || !canStillSend}
            className="w-full"
          />
          <p className="text-xs text-muted-foreground">
            {canStillSend
              ? "Only for this person. Set a template for everyone at a company on the Companies page."
              : "Already emailed, so the template can't change what was sent."}
          </p>
        </div>

        <div>
          <h3 className="mb-3 text-sm font-medium">Email preview</h3>
          {preview.error && <p className="text-sm text-destructive">{preview.error}</p>}
          {preview.loading && !preview.data && <Skeleton className="h-48 w-full" />}
          {preview.data && <EmailPreviewView preview={preview.data} />}
          {preview.data && preview.data.problems.length === 0 && canStillSend && (
            <Button className="mt-4" onClick={() => onSendNow(contact)}>
              <SendIcon /> Send now
            </Button>
          )}
        </div>
      </div>
    </>
  )
}
