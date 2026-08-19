-- ===========================================================================
-- Storage: org branding (logos) now; job photos in Phase 2.
-- ===========================================================================
insert into storage.buckets (id, name, public)
values ('branding', 'branding', true)
on conflict (id) do nothing;

-- Phase 2 seam: intake photos are private (signed URLs only).
insert into storage.buckets (id, name, public)
values ('job-photos', 'job-photos', false)
on conflict (id) do nothing;

-- Objects are stored under "<org_id>/<filename>" so the first path segment
-- carries the tenant.
create policy "branding read" on storage.objects
  for select using (bucket_id = 'branding');

create policy "branding write own org" on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'branding'
    and (storage.foldername(name))[1] = public.current_org_id()::text
  );

create policy "branding update own org" on storage.objects
  for update to authenticated
  using (
    bucket_id = 'branding'
    and (storage.foldername(name))[1] = public.current_org_id()::text
  );

create policy "job photos own org" on storage.objects
  for all to authenticated
  using (
    bucket_id = 'job-photos'
    and (storage.foldername(name))[1] = public.current_org_id()::text
  )
  with check (
    bucket_id = 'job-photos'
    and (storage.foldername(name))[1] = public.current_org_id()::text
  );
