"""Source-format importers: one module per supported trace format.

An importer owns everything format-specific: recognizing a payload (used by
the upload endpoint) and — from Slice 2 — parsing it into normalized
trace/span rows. Importers are pure (bytes/JSON in, rows out); they never
touch HTTP or the database.
"""
