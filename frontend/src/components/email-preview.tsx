"use client"

import { DownloadIcon, PaperclipIcon, TriangleAlertIcon } from "lucide-react"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { downloadResume, type EmailPreview } from "@/lib/api"

/** The exact email that would go out, plus anything that would stop it sending. */
export function EmailPreviewView({ preview }: { preview: EmailPreview }) {
  const noResume = preview.problems.includes("No resume uploaded")

  async function download() {
    try {
      await downloadResume(preview.attachment_name)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't download the resume")
    }
  }

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
      {/* The API cleans this HTML (allowlisted tags, safe links only) before returning it. */}
      <div
        className="email-body rounded-[20px] border bg-muted p-5 text-sm"
        dangerouslySetInnerHTML={{ __html: preview.body }}
      />
      {noResume ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <PaperclipIcon className="size-4" />
          <span className="font-mono">{preview.attachment_name}</span>
        </div>
      ) : (
        <button
          type="button"
          onClick={download}
          title="Download the exact PDF that gets attached"
          className="group flex items-center gap-2 rounded-xl border bg-background px-3 py-2 text-sm shadow-xs transition-colors hover:bg-muted"
        >
          <PaperclipIcon className="size-4 text-muted-foreground" />
          <span className="font-mono underline-offset-4 group-hover:underline">{preview.attachment_name}</span>
          <DownloadIcon className="size-4 text-muted-foreground" />
        </button>
      )}
    </div>
  )
}
