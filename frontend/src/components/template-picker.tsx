"use client"

import { StarIcon } from "lucide-react"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { Template } from "@/lib/api"
import { cn } from "@/lib/utils"

const INHERIT = "inherit"

/** Pick a template, or none (`null`) to fall back to `fallbackLabel`,
 *  e.g. "Default · Template for bigtech" or "Same as company · Amazon special". */
export function TemplatePicker({
  templates,
  value,
  fallbackLabel,
  onChange,
  disabled,
  className,
  ariaLabel = "Template",
}: {
  templates: Template[]
  value: number | null
  fallbackLabel: string
  onChange: (templateId: number | null) => void
  disabled?: boolean
  className?: string
  ariaLabel?: string
}) {
  const items = [
    { value: INHERIT, label: fallbackLabel },
    ...templates.map((t) => ({ value: String(t.id), label: t.name })),
  ]

  return (
    <Select
      items={items}
      value={value === null ? INHERIT : String(value)}
      onValueChange={(v) => v !== null && onChange(v === INHERIT ? null : Number(v))}
      disabled={disabled}
    >
      <SelectTrigger className={cn("w-64 max-w-full", value === null && "text-muted-foreground", className)} aria-label={ariaLabel}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={INHERIT}>{fallbackLabel}</SelectItem>
        <SelectSeparator />
        {templates.map((t) => (
          <SelectItem key={t.id} value={String(t.id)}>
            {t.name}
            {t.is_default && <StarIcon className="fill-current text-muted-foreground" aria-label="default" />}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** "Default · Template for bigtech": what an unset choice falls back to. */
export function defaultLabel(templates: Template[]) {
  const t = templates.find((x) => x.is_default)
  return t ? `Default · ${t.name}` : "Default template"
}
