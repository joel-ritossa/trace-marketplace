// NEXT_PUBLIC_* values are inlined at build time and must be accessed
// statically; this module is the single place that does so.
export const publicEnv = {
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL!,
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  // 50 stays under the API's 60/min per-user upload rate limit.
  uploadMaxFiles: Number(process.env.NEXT_PUBLIC_UPLOAD_MAX_FILES ?? "") || 50,
};

// Server-side code inside Docker reaches the host's Supabase stack via
// host.docker.internal; the browser uses the public URL.
export function serverSupabaseUrl(): string {
  return process.env.SUPABASE_INTERNAL_URL ?? publicEnv.supabaseUrl;
}
