"use client"

import { PencilIcon } from "lucide-react"
import Link from "next/link"
import { useState } from "react"
import { toast } from "sonner"

import { StatusBadge } from "@/components/badges"
import { ErrorAlert, PageHeader } from "@/components/page-header"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { CONTACT_STATUSES, patch, type Company } from "@/lib/api"
import { formatDate } from "@/lib/format"
import { useApi } from "@/lib/use-api"

function CompanyName({ company, onSaved }: { company: Company; onSaved: (c: Company) => void }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(company.name)

  async function save() {
    setEditing(false)
    const trimmed = name.trim()
    if (!trimmed || trimmed === company.name) {
      setName(company.name)
      return
    }
    try {
      onSaved(await patch<Company>(`/companies/${company.id}`, { name: trimmed }))
      toast.success(`Renamed to ${trimmed}`)
    } catch (e) {
      setName(company.name)
      toast.error((e as Error).message)
    }
  }

  if (editing) {
    return (
      <Input
        autoFocus
        aria-label="Company name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur()
          if (e.key === "Escape") {
            setName(company.name)
            setEditing(false)
          }
        }}
        className="h-8 max-w-56"
      />
    )
  }
  return (
    <button
      className="group inline-flex items-center gap-1.5 text-left font-medium"
      onClick={() => setEditing(true)}
      title="Rename"
    >
      {company.name}
      <PencilIcon className="size-3 text-muted-foreground opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100" />
    </button>
  )
}

export default function CompaniesPage() {
  const { data, error, setData } = useApi<Company[]>("/companies")

  function replace(updated: Company) {
    setData((list) => list && list.map((c) => (c.id === updated.id ? updated : c)))
  }

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Companies"
        description="Click a name to rename it. Emails from these domains will use the new name."
      />
      {error && <ErrorAlert message={error} />}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Company</TableHead>
              <TableHead>Domains</TableHead>
              <TableHead className="text-right">Contacts</TableHead>
              <TableHead>By status</TableHead>
              <TableHead>Last contacted</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!data && !error && (
              <TableRow><TableCell colSpan={5}><Skeleton className="h-24 w-full" /></TableCell></TableRow>
            )}
            {data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                  No companies yet. They&apos;re created when you <Link href="/import" className="underline">import contacts</Link>.
                </TableCell>
              </TableRow>
            )}
            {data?.map((c) => (
              <TableRow key={c.id}>
                <TableCell><CompanyName company={c} onSaved={replace} /></TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {[c.domain, ...c.aliases].filter(Boolean).join(", ") || "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  <Link href={`/contacts?company_id=${c.id}`} className="hover:underline">{c.contact_count}</Link>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {CONTACT_STATUSES.filter((s) => c.status_counts[s]).map((s) => (
                      <Link key={s} href={`/contacts?company_id=${c.id}&status=${s}`}>
                        <StatusBadge status={s} />
                        <span className="sr-only">: </span>
                        <span className="ml-1 text-xs tabular-nums text-muted-foreground">{c.status_counts[s]}</span>
                      </Link>
                    ))}
                  </div>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{formatDate(c.last_contacted_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
