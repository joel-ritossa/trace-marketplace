-- Owner task scope (1_analysis.md Taxonomies): the categories an account
-- works in, hard-scoping the judge's category vocabulary. Empty = unscoped.
-- Values validated app-side against the closed task_category enum; the
-- existing profiles RLS (self select/update) already covers access.
alter table profiles
  add column task_categories text[] not null default '{}';
