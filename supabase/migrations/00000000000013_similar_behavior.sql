-- Similar behavior (docs/proposals/similar-behavior.md): one embedding per
-- trace over the judge rendering, powering GET /v1/traces/{id}/similar and
-- behavior-anchored subscriptions.

create extension if not exists vector;

-- Pure function of (payload, gates), like trace_analysis: rewritten by every
-- analyze run, deleted when the LLM gate (consent/keys) closes. Dimension is
-- fixed to text-embedding-3-small; a model swap is a new migration + re-embed.
create table public.trace_embeddings (
  trace_id uuid primary key references public.traces (id) on delete cascade,
  embedding vector(1536) not null,
  model text not null,
  renderer_version text not null,
  created_at timestamptz not null default now()
);

-- Cosine kNN for the similar-traces endpoint; exact fallback is fine at
-- demo scale, the index keeps the path honest as the corpus grows.
create index trace_embeddings_hnsw
  on public.trace_embeddings using hnsw (embedding vector_cosine_ops);

-- Vectors are derived from trace content: readable exactly when the trace
-- is (owner or listed) — mirrors the API check for defense in depth.
alter table public.trace_embeddings enable row level security;

create policy "trace_embeddings_select_visible" on public.trace_embeddings
  for select to authenticated
  using (
    exists (
      select 1 from public.traces t
      where t.id = trace_id
        and (t.owner_id = (select auth.uid()) or t.visibility = 'listed')
    )
  );

-- Behavior anchor: subscription matches require cosine similarity to the
-- anchor trace >= threshold, ANDed with the stored filter query. Anchor
-- deletion nulls the reference — the subscription then matches nothing
-- until the owner edits it (validated shape requires threshold with anchor).
alter table public.subscriptions
  add column similar_to_trace_id uuid references public.traces (id) on delete set null,
  add column similarity_threshold real
    check (similarity_threshold > 0 and similarity_threshold < 1);
