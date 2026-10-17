"use client"

import { Loader2Icon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { RichTextEditor } from "@/components/rich-text-editor"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { put, type Settings } from "@/lib/api"

/** Edit the one signature that goes after "--" at the end of every email. */
export function SignatureDialog({
  open,
  onOpenChange,
  signature,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  signature: string
  onSaved: (settings: Settings) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Signature</DialogTitle>
          <DialogDescription>
            Added after a &ldquo;--&rdquo; line at the end of every email. For example: your name in bold,
            your school and graduation year, then LinkedIn | phone | email as links.
          </DialogDescription>
        </DialogHeader>
        {/* Mounted on open, so each opening starts from the saved signature. */}
        {open && <SignatureForm signature={signature} onSaved={onSaved} onClose={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function SignatureForm({
  signature,
  onSaved,
  onClose,
}: {
  signature: string
  onSaved: (settings: Settings) => void
  onClose: () => void
}) {
  const [draft, setDraft] = useState(signature)
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    try {
      const saved = await put<Settings>("/settings", { signature: draft })
      onSaved(saved)
      toast.success(saved.signature ? "Signature saved" : "Signature removed")
      onClose()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <RichTextEditor ariaLabel="Signature" value={draft} onChange={setDraft} minHeight="min-h-36" />
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={save} disabled={saving}>
          {saving && <Loader2Icon className="animate-spin" />} Save signature
        </Button>
      </DialogFooter>
    </>
  )
}
