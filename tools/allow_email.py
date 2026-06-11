"""Add an email or domain to the signup allowlist:

    make allow EMAIL=user@example.com   # one address
    make allow EMAIL=@example.com       # a whole domain

Targets whichever stack the env points at (.env / .env.local / real env vars);
export SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY for a hosted project.
"""

import sys

from _stack import StackError, allow_email, load_env


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print("usage: python3 tools/allow_email.py <email | @domain>", file=sys.stderr)
        return 2
    entry = sys.argv[1]
    try:
        allow_email(load_env(), entry)
    except StackError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    print(f"allowlisted {entry.lower()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
