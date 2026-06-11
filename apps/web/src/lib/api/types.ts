// Mirrors services/api/app/schemas — keep in sync when the API changes.

export type Me = {
  id: string;
  email: string | null;
  display_name: string | null;
  created_at: string;
};

export type ApiErrorBody = {
  error: { code: string; message: string; details: Record<string, unknown> };
};
