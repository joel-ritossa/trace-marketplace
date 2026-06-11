// Types mirror services/api/app/schemas/profile.py — keep in sync.

export type Me = {
  id: string;
  email: string | null;
  display_name: string | null;
  created_at: string;
};
