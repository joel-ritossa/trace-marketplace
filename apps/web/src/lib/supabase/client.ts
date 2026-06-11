import { createBrowserClient } from "@supabase/ssr";
import { publicEnv } from "@/lib/env";
import { AUTH_COOKIE } from "@/lib/supabase/cookie";

export function createClient() {
  return createBrowserClient(publicEnv.supabaseUrl, publicEnv.supabaseAnonKey, {
    cookieOptions: AUTH_COOKIE,
  });
}
