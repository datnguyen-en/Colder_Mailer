import { Badge } from "@/components/ui/badge"
import type { ContactStatus } from "@/lib/api"
import { cn } from "@/lib/utils"

// Every badge carries its text label, so color is never the only signal.
const STATUS_STYLES: Record<ContactStatus, string> = {
  new: "bg-muted text-muted-foreground",
  queued: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  sending: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  sent: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300",
  replied: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  bounced: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
}

export function StatusBadge({ status, stuck }: { status: ContactStatus; stuck?: boolean }) {
  return (
    <Badge variant="secondary" className={cn("capitalize", STATUS_STYLES[status])}>
      {stuck ? "stuck sending" : status}
    </Badge>
  )
}

const FLAGS: Record<string, { label: string; className: string; title: string }> = {
  personal_email: {
    label: "Personal email",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
    title: "Gmail, Outlook, .edu etc. No company is attached.",
  },
  generic_inbox: {
    label: "Role inbox",
    className: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300",
    title: "careers@, jobs@, info@… Usually a person is a better target.",
  },
  needs_name: {
    label: "No name",
    className: "bg-muted text-muted-foreground",
    title: "No first name found. The email will say \"Hi there,\" unless you add one.",
  },
  already_contacted: {
    label: "Already contacted",
    className: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
    title: "This person is already queued, sent, or replied. Import will skip them.",
  },
  already_imported: {
    label: "Already imported",
    className: "bg-muted text-muted-foreground",
    title: "Already in your contacts. Import will skip them.",
  },
}

export function FlagBadge({ flag }: { flag: string }) {
  const f = FLAGS[flag] ?? { label: flag, className: "", title: flag }
  return (
    <Badge variant="secondary" className={f.className} title={f.title}>
      {f.label}
    </Badge>
  )
}

/** Rows with these flags start unchecked in the import preview. */
export const SKIP_BY_DEFAULT = new Set(["already_contacted", "already_imported", "generic_inbox"])
