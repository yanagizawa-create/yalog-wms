-- ROLLBACK da MIGRAÇÃO 01 — restaura exatamente o estado capturado em 16/10/2026
-- (definições conferidas em backup_20261016.pg_policies_public).
begin;

create policy "anon full access" on public.logs as permissive for all to anon using (true) with check (true);
create policy logs_delete on public.logs as permissive for delete to anon using (true);
create policy logs_update on public.logs as permissive for update to anon using (true) with check (true);
grant update, delete on public.logs to anon;

alter function public.set_updated_at()                   reset search_path;
alter function public.gen_random_bytes(integer)          reset search_path;
alter function public._patio_entidade_para_recurso(text) reset search_path;

grant execute on function public.wms_kv_store_auditoria() to public, anon, authenticated;

commit;
