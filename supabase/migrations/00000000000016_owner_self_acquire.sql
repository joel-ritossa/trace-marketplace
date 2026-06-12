-- Owners may acquire their own listed traces (2_data-model.md): the
-- acquisition lands the trace in their library. Drop the non-owner check
-- from the insert mirror; the listed requirement stays.

drop policy "acquisitions_insert_own" on public.acquisitions;

create policy "acquisitions_insert_own" on public.acquisitions
  for insert to authenticated
  with check (
    (select auth.uid()) = consumer_id
    and exists (
      select 1 from public.traces t
      where t.id = trace_id
        and t.visibility = 'listed'
    )
  );
