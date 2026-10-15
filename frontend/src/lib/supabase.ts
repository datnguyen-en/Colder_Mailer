import { createClient, type SupabaseClient } from "@supabase/supabase-js"

const url = process.env.NEXT_PUBLIC_SUPABASE_URL
const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY

/** Null when Supabase isn't configured: local dev with the API's AUTH_DISABLED bypass. */
export const supabase: SupabaseClient | null =
  url && key ? createClient(url, key) : null

export const authEnabled = supabase !== null
