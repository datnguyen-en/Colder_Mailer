"use client"

import { FileUpIcon, Loader2Icon } from "lucide-react"
import Link from "next/link"
import { useRef, useState } from "react"
import { toast } from "sonner"

import { FlagBadge, SKIP_BY_DEFAULT } from "@/components/badges"
import { ErrorAlert, PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { post, type ImportResult, type PreviewRow } from "@/lib/api"

type Row = PreviewRow & { include: boolean }
type Source = "paste" | "csv"

export default function ImportPage() {
  const [text, setText] = useState("")
  const [source, setSource] = useState<Source>("paste")
  const [fileName, setFileName] = useState<string | null>(null)
  const [rows, setRows] = useState<Row[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  async function parse(input: string, format: "text" | "csv") {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const preview = await post<PreviewRow[]>("/parse", { text: input, format })
      setRows(preview.map((r) => ({ ...r, include: !r.flags.some((f) => SKIP_BY_DEFAULT.has(f)) })))
      if (preview.length === 0) toast.info("No email addresses found.")
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function onFile(file: File) {
    setFileName(file.name)
    setSource("csv")
    await parse(await file.text(), "csv")
  }

  function update(index: number, changes: Partial<Row>) {
    setRows((current) => current && current.map((r, i) => (i === index ? { ...r, ...changes } : r)))
  }

  /** A company fix applies to every row from that domain that had the same guess. */
  function renameCompany(index: number, name: string) {
    setRows((current) => {
      if (!current) return current
      const { domain, company_name: before } = current[index]
      return current.map((r, i) =>
        i === index || (r.domain === domain && r.company_name === before && !r.flags.includes("personal_email"))
          ? { ...r, company_name: name }
          : r,
      )
    })
  }

  async function importSelected() {
    if (!rows) return
    setBusy(true)
    setError(null)
    try {
      const selected = rows.filter((r) => r.include).map((r) => ({
        email: r.email,
        title: r.title,
        domain: r.domain,
        flags: r.flags,
        first_name: r.first_name?.trim() || null,
        last_name: r.last_name?.trim() || null,
        company_name: r.company_name?.trim() || null,
      }))
      const res = await post<ImportResult>("/contacts/import", { rows: selected, source })
      setResult(res)
      setRows(null)
      setText("")
      setFileName(null)
      toast.success(`Imported ${res.created} contact${res.created === 1 ? "" : "s"}`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const included = rows?.filter((r) => r.include).length ?? 0
  const allIncluded = !!rows?.length && included === rows.length

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        eyebrow="Add people"
        title="Import contacts"
        description="Paste anything with email addresses in it, or upload a CSV export (e.g. from Apollo). Nothing is saved until you import."
      />
      {error && <ErrorAlert message={error} />}

      {result && (
        <Card className="mb-6">
          <CardContent className="text-sm">
            <p>
              <strong>{result.created}</strong> imported, <strong>{result.skipped}</strong> skipped.{" "}
              <Link href="/contacts" className="underline">View contacts</Link>
            </p>
            {result.skipped_rows.length > 0 && (
              <ul className="mt-2 text-muted-foreground">
                {result.skipped_rows.map((s) => <li key={s.email}>{s.email}: {s.reason}</li>)}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      {!rows && (
        <div className="space-y-3">
          <Textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              setSource("paste")
            }}
            placeholder={"Jane Doe <jane.doe@stripe.com>, jsmith@ramp.com\nmailto:recruiting@notion.so …"}
            className="min-h-64 font-mono text-sm"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => parse(text, "text")} disabled={busy || !text.trim()}>
              {busy && <Loader2Icon className="animate-spin" />} Parse
            </Button>
            <span className="text-sm text-muted-foreground">or</span>
            <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={busy}>
              <FileUpIcon /> Upload CSV
            </Button>
            <input
              ref={fileInput}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) onFile(file)
                e.target.value = ""
              }}
            />
          </div>
        </div>
      )}

      {rows && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-muted-foreground">
              Found {rows.length} email{rows.length === 1 ? "" : "s"}
              {fileName && ` in ${fileName}`}. Fix names and companies below, then import.
              Role inboxes and people you already have start unchecked.
            </p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setRows(null)} disabled={busy}>Back</Button>
              <Button onClick={importSelected} disabled={busy || included === 0}>
                {busy && <Loader2Icon className="animate-spin" />} Import {included} selected
              </Button>
            </div>
          </div>
          <div className="overflow-hidden rounded-3xl border bg-card shadow-soft">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      aria-label="Select all"
                      checked={allIncluded}
                      indeterminate={included > 0 && !allIncluded}
                      onCheckedChange={(checked) =>
                        setRows(rows.map((r) => ({ ...r, include: checked })))
                      }
                    />
                  </TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>First name</TableHead>
                  <TableHead>Last name</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Flags</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row, i) => (
                  <TableRow key={row.email} className={row.include ? "" : "opacity-60"}>
                    <TableCell>
                      <Checkbox
                        aria-label={`Include ${row.email}`}
                        checked={row.include}
                        onCheckedChange={(checked) => update(i, { include: checked })}
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs">{row.email}</TableCell>
                    <TableCell>
                      <Input
                        aria-label="First name"
                        value={row.first_name ?? ""}
                        onChange={(e) => update(i, { first_name: e.target.value })}
                        placeholder="there"
                        className="h-8 min-w-28"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        aria-label="Last name"
                        value={row.last_name ?? ""}
                        onChange={(e) => update(i, { last_name: e.target.value })}
                        className="h-8 min-w-28"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        aria-label="Company"
                        value={row.company_name ?? ""}
                        placeholder={row.flags.includes("personal_email") ? "None" : ""}
                        onChange={(e) => renameCompany(i, e.target.value)}
                        className="h-8 min-w-36"
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {row.flags
                          .filter((f) => !(f === "needs_name" && row.first_name?.trim()))
                          .map((f) => <FlagBadge key={f} flag={f} />)}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
    </div>
  )
}
