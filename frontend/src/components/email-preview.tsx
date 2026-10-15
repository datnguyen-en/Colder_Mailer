import { PaperclipIcon, TriangleAlertIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { EmailPreview } from "@/lib/api"

/** The exact email that would go out, plus anything that would stop it sending. */
export function EmailPreviewView({ preview }: { preview: EmailPreview }) {
  return (
    <div className="space-y-4">
      {preview.problems.length > 0 && (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>This email can&apos;t be sent yet</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4">
              {preview.problems.map((p) => <li key={p}>{p}</li>)}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {preview.to && (
          <>
            <dt className="text-muted-foreground">To</dt>
            <dd className="break-all">{preview.to}</dd>
          </>
        )}
        <dt className="text-muted-foreground">Subject</dt>
        <dd className="font-medium">{preview.subject}</dd>
      </dl>
      <div className="rounded-lg border bg-muted/30 p-4 text-sm whitespace-pre-wrap">{preview.body}</div>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <PaperclipIcon className="size-4" />
        <span className="font-mono">{preview.attachment_name}</span>
      </div>
    </div>
  )
}
