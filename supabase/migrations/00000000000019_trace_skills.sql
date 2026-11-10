-- Skills (2_data-model.md): the distinct skill names a trace used — agent
-- `Skill` tool calls and user slash commands, from spans' `skill.name` —
-- derived at ingestion like tool_names, filterable by array overlap.
alter table public.traces
  add column skill_names text[] not null default '{}';

create index traces_skill_names_idx on public.traces using gin (skill_names);

-- The few spans whose attributes the detail reads (turn spans, skill uses,
-- subagent spawns): partial indexes keep those reads from detoasting every
-- span's attributes (tool spans carry megabytes of tool I/O). Measured on a
-- 21k-span session: 584 ms without, 73 ms with. Each predicate must match
-- the query's exactly (queries/spans.py SKELETON, queries/analysis.py).
create index spans_turn_idx on public.spans (trace_id) where attributes ? 'turn.index';
create index spans_skill_idx on public.spans (trace_id) where attributes ? 'skill.name';
create index spans_subagent_idx on public.spans (trace_id)
  where attributes ?| array['subagent.id', 'subagent.description', 'subagent.type'];
