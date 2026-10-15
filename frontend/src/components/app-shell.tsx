"use client"

import type { Session } from "@supabase/supabase-js"
import {
  Building2Icon,
  FileTextIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  MailIcon,
  SettingsIcon,
  UploadIcon,
  UsersIcon,
} from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { authEnabled, supabase } from "@/lib/supabase"
import { cn } from "@/lib/utils"

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboardIcon },
  { href: "/import", label: "Import", icon: UploadIcon },
  { href: "/contacts", label: "Contacts", icon: UsersIcon },
  { href: "/companies", label: "Companies", icon: Building2Icon },
  { href: "/templates", label: "Template", icon: FileTextIcon },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
]

/** Nav + login gate. With Supabase unconfigured (local dev) everything is open. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [session, setSession] = useState<Session | null>(null)
  const [checked, setChecked] = useState(!authEnabled)

  useEffect(() => {
    if (!supabase) return
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setChecked(true)
    })
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s))
    return () => data.subscription.unsubscribe()
  }, [])

  const onLogin = pathname === "/login"
  const blocked = authEnabled && checked && !session && !onLogin

  useEffect(() => {
    if (blocked) router.replace("/login")
    if (authEnabled && session && onLogin) router.replace("/")
  }, [blocked, session, onLogin, router])

  if (onLogin) return <>{children}</>
  if (!checked || blocked) return null

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b bg-muted/30 md:sticky md:top-0 md:h-screen md:w-56 md:shrink-0 md:border-r md:border-b-0">
        <div className="flex items-center gap-2 px-4 py-3 md:py-5">
          <MailIcon className="size-5" />
          <span className="font-semibold">Cold Email Tracker</span>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-0">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href)
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  active && "bg-muted font-medium text-foreground",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            )
          })}
        </nav>
        <div className="hidden px-4 py-4 text-xs text-muted-foreground md:absolute md:bottom-0 md:block md:w-56">
          {supabase && session ? (
            <div className="space-y-2">
              <div className="truncate">{session.user.email}</div>
              <Button variant="outline" size="sm" onClick={() => supabase!.auth.signOut()}>
                <LogOutIcon /> Sign out
              </Button>
            </div>
          ) : (
            <span>Dev mode: login disabled</span>
          )}
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 md:px-8">{children}</main>
    </div>
  )
}
