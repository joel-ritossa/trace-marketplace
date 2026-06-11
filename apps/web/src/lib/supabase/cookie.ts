// Browser and server reach Supabase via different hosts (localhost vs
// host.docker.internal), so the cookie name must be pinned explicitly —
// the default is derived from the URL and would diverge.
export const AUTH_COOKIE = { name: "tm-auth" };
