import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { publicEnv, serverSupabaseUrl } from "@/lib/env";
import { AUTH_COOKIE } from "@/lib/supabase/cookie";

export async function createClient() {
  const cookieStore = await cookies();
  return createServerClient(serverSupabaseUrl(), publicEnv.supabaseAnonKey, {
    cookieOptions: AUTH_COOKIE,
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options),
          );
        } catch {
          // Called from a Server Component; middleware handles session refresh.
        }
      },
    },
  });
}
