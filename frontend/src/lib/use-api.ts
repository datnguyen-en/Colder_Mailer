"use client"

import { useCallback, useEffect, useState } from "react"

import { api } from "@/lib/api"

type Result<T> = { key: string | null; data: T | null; error: string | null }

/** GET `path` on mount and whenever it changes. `path = null` skips the request.
 *  Previous data stays visible while a new request is in flight. */
export function useApi<T>(path: string | null) {
  const [version, setVersion] = useState(0)
  const [result, setResult] = useState<Result<T>>({ key: null, data: null, error: null })
  const key = path === null ? null : `${version}:${path}`

  useEffect(() => {
    if (path === null || key === null) return
    let cancelled = false
    api<T>(path)
      .then((data) => !cancelled && setResult({ key, data, error: null }))
      .catch((e: Error) => !cancelled && setResult((r) => ({ key, data: r.data, error: e.message })))
    return () => {
      cancelled = true
    }
  }, [path, key])

  const reload = useCallback(() => setVersion((v) => v + 1), [])
  const setData = useCallback(
    (update: (data: T | null) => T | null) => setResult((r) => ({ ...r, data: update(r.data) })),
    [],
  )
  return {
    data: result.data,
    error: result.error,
    loading: key !== null && result.key !== key,
    reload,
    setData,
  }
}
