"use client"

import { MoreHorizontalIcon, SearchIcon, SendIcon, Trash2Icon } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { Suspense, useEffect, useState } from "react"
import { toast } from "sonner"

import { StatusBadge } from "@/components/badges"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { ContactSheet } from "@/components/contact-sheet"
import { ErrorAlert, PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  CONTACT_STATUSES,
  del,
  post,
  type Company,
  type Contact,
  type ContactPage,
  type QueueResult,
  type SendNowResult,
} from "@/lib/api"
import { formatDate, fullName } from "@/lib/format"
import { useApi } from "@/lib/use-api"

const PAGE_SIZE = 50
const ALL = "all"

export default function ContactsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <Contacts />
    </Suspense>
  )
}

function Contacts() {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const status = params.get("status") ?? ALL
  const companyId = params.get("company_id")
  const q = params.get("q") ?? ""
  const page = Number(params.get("page") ?? 1)

  const [search, setSearch] = useState(q)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [open, setOpen] = useState<Contact | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<number[] | null>(null)
  const [confirmRequeue, setConfirmRequeue] = useState<Contact | null>(null)
  const [confirmSend, setConfirmSend] = useState<Contact | null>(null)
  const [sendingId, setSendingId] = useState<number | null>(null)

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
  if (status !== ALL) query.set("status", status)
  if (companyId) query.set("company_id", companyId)
  if (q) query.set("q", q)
  const { data, error, reload, setData } = useApi<ContactPage>(`/contacts?${query}`)
  const { data: companies } = useApi<Company[]>("/companies")
  const companyName = companies?.find((c) => String(c.id) === companyId)?.name

  function setParam(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "" || v === ALL) next.delete(k)
      else next.set(k, v)
    }
    if (!("page" in changes)) next.delete("page")
    router.replace(`${pathname}?${next}`)
    setSelected(new Set())
  }

  // Search as you type, debounced.
  useEffect(() => {
    if (search === q) return
    const t = setTimeout(() => setParam({ q: search }), 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  function replaceContact(updated: Contact) {
    setData((d) => d && { ...d, items: d.items.map((c) => (c.id === updated.id ? updated : c)) })
    if (open?.id === updated.id) setOpen(updated)
  }

  async function action(contact: Contact, path: string, done: string) {
    try {
      replaceContact(await post<Contact>(`/contacts/${contact.id}/${path}`))
      toast.success(done)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  async function sendNow(contact: Contact) {
    setSendingId(contact.id)
    try {
      const res = await post<SendNowResult>("/send/now", { contact_id: contact.id })
      replaceContact(res.contact)
      if (res.outcome === "sent") toast.success(`Sent to ${contact.email}`)
      else if (res.outcome === "failed") toast.error(`Not sent: ${res.detail}`)
      else toast.warning(`Gmail didn't confirm the send to ${contact.email}. Check your Sent folder.`)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSendingId(null)
    }
  }

  async function queueSelected() {
    try {
      const res = await post<QueueResult>("/send/queue", { contact_ids: [...selected] })
      toast.success(`Queued ${res.queued} email${res.queued === 1 ? "" : "s"}. About one goes out every 15 minutes during your send window.`)
      if (res.skipped.length) {
        toast.info(`Skipped ${res.skipped.length}: ${res.skipped.map((s) => `${s.email} (${s.reason})`).join(", ")}`)
      }
      setSelected(new Set())
      reload()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  async function deleteContacts(ids: number[]) {
    const results = await Promise.allSettled(ids.map((id) => del(`/contacts/${id}`)))
    const failed = results.filter((r) => r.status === "rejected")
    if (failed.length) toast.error((failed[0] as PromiseRejectedResult).reason.message)
    const deleted = ids.length - failed.length
    if (deleted) toast.success(`Deleted ${deleted} contact${deleted === 1 ? "" : "s"}`)
    setSelected(new Set())
    reload()
  }

  const items = data?.items ?? []
  const allSelected = items.length > 0 && items.every((c) => selected.has(c.id))
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  const statusItems = [{ value: ALL, label: "All statuses" }, ...CONTACT_STATUSES.map((s) => ({ value: s, label: s }))]

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader eyebrow="People" title="Contacts" description={data ? `${data.total} total` : undefined}>
        <Button render={<Link href="/import" />} nativeButton={false} variant="outline">Import</Button>
      </PageHeader>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-72">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, email, company, title"
            className="pl-8"
          />
        </div>
        <Select items={statusItems} value={status} onValueChange={(v) => setParam({ status: v })}>
          <SelectTrigger className="w-40 capitalize"><SelectValue /></SelectTrigger>
          <SelectContent>
            {statusItems.map((s) => (
              <SelectItem key={s.value} value={s.value} className="capitalize">{s.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {companyId && (
          <Button variant="secondary" size="sm" onClick={() => setParam({ company_id: null })}>
            {companyName ?? "Company"} ✕
          </Button>
        )}
        {selected.size > 0 && (
          <div className="flex items-center gap-2 sm:ml-auto">
            <span className="text-sm text-muted-foreground">{selected.size} selected</span>
            <Button size="sm" onClick={queueSelected}>
              <SendIcon /> Queue
            </Button>
            <Button size="sm" variant="destructive" onClick={() => setConfirmDelete([...selected])}>
              <Trash2Icon /> Delete
            </Button>
          </div>
        )}
      </div>

      {error && <ErrorAlert message={error} />}

      <div className="overflow-hidden rounded-3xl border bg-card shadow-soft">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <Checkbox
                  aria-label="Select all on this page"
                  checked={allSelected}
                  indeterminate={selected.size > 0 && !allSelected}
                  onCheckedChange={(checked) =>
                    setSelected(checked ? new Set(items.map((c) => c.id)) : new Set())
                  }
                />
              </TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Sent</TableHead>
              <TableHead className="w-10"><span className="sr-only">Actions</span></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!data && !error && (
              <TableRow><TableCell colSpan={7}><Skeleton className="h-24 w-full" /></TableCell></TableRow>
            )}
            {data && items.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  No contacts match. <Link href="/import" className="underline">Import some</Link>.
                </TableCell>
              </TableRow>
            )}
            {items.map((c) => (
              <TableRow key={c.id} data-state={selected.has(c.id) ? "selected" : undefined}>
                <TableCell>
                  <Checkbox
                    aria-label={`Select ${c.email}`}
                    checked={selected.has(c.id)}
                    onCheckedChange={(checked) => {
                      const next = new Set(selected)
                      if (checked) next.add(c.id)
                      else next.delete(c.id)
                      setSelected(next)
                    }}
                  />
                </TableCell>
                <TableCell>
                  <button className="text-left font-mono text-xs hover:underline" onClick={() => setOpen(c)}>
                    {c.email}
                  </button>
                </TableCell>
                <TableCell>
                  {fullName(c.first_name, c.last_name) || <span className="text-muted-foreground">—</span>}
                  {c.title && <div className="text-xs text-muted-foreground">{c.title}</div>}
                </TableCell>
                <TableCell>{c.company_name ?? <span className="text-muted-foreground">—</span>}</TableCell>
                <TableCell><StatusBadge status={c.status} stuck={c.stuck} /></TableCell>
                <TableCell className="text-sm text-muted-foreground">{formatDate(c.sent_at)}</TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label="Actions" />}>
                      <MoreHorizontalIcon />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => setOpen(c)}>Preview & edit</DropdownMenuItem>
                      {["new", "queued", "failed"].includes(c.status) && (
                        <DropdownMenuItem disabled={sendingId !== null} onClick={() => setConfirmSend(c)}>
                          Send now
                        </DropdownMenuItem>
                      )}
                      {c.status !== "replied" && (
                        <DropdownMenuItem onClick={() => action(c, "mark-replied", "Marked as replied")}>
                          Mark replied
                        </DropdownMenuItem>
                      )}
                      {c.status === "failed" && (
                        <DropdownMenuItem onClick={() => action(c, "requeue", "Requeued")}>Requeue</DropdownMenuItem>
                      )}
                      {c.stuck && (
                        <DropdownMenuItem onClick={() => setConfirmRequeue(c)}>Requeue…</DropdownMenuItem>
                      )}
                      {c.status === "queued" && (
                        <DropdownMenuItem onClick={() => action(c, "unqueue", "Removed from queue")}>
                          Remove from queue
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuSeparator />
                      <DropdownMenuItem variant="destructive" onClick={() => setConfirmDelete([c.id])}>
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {pages > 1 && (
        <div className="mt-4 flex items-center justify-end gap-2 text-sm">
          <Button variant="outline" size="sm" disabled={page <= 1}
            onClick={() => setParam({ page: String(page - 1) })}>Previous</Button>
          <span className="text-muted-foreground">Page {page} of {pages}</span>
          <Button variant="outline" size="sm" disabled={page >= pages}
            onClick={() => setParam({ page: String(page + 1) })}>Next</Button>
        </div>
      )}

      <ContactSheet
        contact={open}
        companies={companies ?? []}
        onClose={() => setOpen(null)}
        onSaved={replaceContact}
        onSendNow={setConfirmSend}
      />
      <ConfirmDialog
        open={confirmSend !== null}
        onOpenChange={(o) => !o && setConfirmSend(null)}
        title={`Send to ${confirmSend?.email} now?`}
        description="It goes out from your Gmail right away and can't be unsent. Each address only ever gets one email."
        confirmLabel="Send now"
        destructive={false}
        onConfirm={() => confirmSend && sendNow(confirmSend)}
      />
      <ConfirmDialog
        open={confirmRequeue !== null}
        onOpenChange={(o) => !o && setConfirmRequeue(null)}
        title="Was this email actually sent?"
        description={`The send to ${confirmRequeue?.email} got stuck, so it may have gone out. Open Gmail's Sent folder first. Only requeue if it's not there, or they'll get it twice.`}
        confirmLabel="It's not in Sent, requeue"
        onConfirm={() => confirmRequeue && action(confirmRequeue, "requeue?confirm_not_sent=true", "Requeued")}
      />
      <ConfirmDialog
        open={confirmDelete !== null}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
        title={`Delete ${confirmDelete?.length === 1 ? "this contact" : `${confirmDelete?.length} contacts`}?`}
        description="This can't be undone. Contacts you've already emailed are kept, so they can never be emailed twice."
        confirmLabel="Delete"
        onConfirm={() => confirmDelete && deleteContacts(confirmDelete)}
      />
    </div>
  )
}
