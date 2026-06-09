import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

if (!url || !anonKey) {
  // Surfaced clearly in dev; in prod these are injected at build time.
  console.error(
    "Missing VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY. Auth will not work."
  );
}

export const supabase = createClient(url, anonKey, {
  auth: {
    // Keep the user signed in on this device across reloads/restarts, and
    // silently refresh the access token so one Google sign-in lasts.
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});
