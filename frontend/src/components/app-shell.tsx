"use client"

import type { Session } from "@supabase/supabase-js"
import { LogOutIcon } from "lucide-react"
import Image from "next/image"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { authEnabled, supabase } from "@/lib/supabase"
import { cn } from "@/lib/utils"

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/import", label: "Import" },
  { href: "/contacts", label: "Contacts" },
  { href: "/companies", label: "Companies" },
  { href: "/templates", label: "Template" },
  { href: "/settings", label: "Settings" },
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
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 pt-4 md:px-8 md:pt-6">
        <Link
          href="/"
          className="flex items-center gap-3 rounded-2xl border bg-background py-2 pr-5 pl-2 shadow-soft"
        >
          <Image src="/logo.png" alt="" width={36} height={36} className="size-9 rounded-full" priority />
          <span className="text-lg font-medium tracking-tight">Colder Mailer</span>
        </Link>
        <nav className="flex max-w-full items-center gap-1 overflow-x-auto rounded-2xl border bg-background p-1.5 shadow-soft">
          {NAV.map(({ href, label }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href)
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "shrink-0 rounded-xl px-4 py-2.5 text-[13px] font-medium tracking-[0.14em] uppercase text-foreground/70 transition-colors hover:text-foreground",
                  active && "bg-muted text-foreground ring-1 ring-border",
                )}
              >
                {label}
              </Link>
            )
          })}
          {supabase && session && (
            <Button
              variant="ghost"
              size="icon"
              className="ml-1 shrink-0"
              title={`Sign out ${session.user.email}`}
              aria-label="Sign out"
              onClick={() => supabase!.auth.signOut()}
            >
              <LogOutIcon />
            </Button>
          )}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-4 pb-16 md:px-8">{children}</main>
    </div>
  )
}
