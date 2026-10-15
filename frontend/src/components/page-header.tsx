import { TriangleAlertIcon } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"

export function PageHeader({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children?: React.ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  )
}

export function ErrorAlert({ message }: { message: string }) {
  return (
    <Alert variant="destructive" className="mb-4">
      <TriangleAlertIcon />
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}
