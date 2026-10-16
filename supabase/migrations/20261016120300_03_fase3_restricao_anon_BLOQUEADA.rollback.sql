-- ROLLBACK da MIGRAÇÃO 03 — restaura as políticas/permissões capturadas em 16/10/2026.
begin;
grant select, insert, update, delete on public.usuarios to anon;
create policy "anon full access"   on public.usuarios as permissive for all    to anon using (true) with check (true);
create policy usuarios_insert_anon on public.usuarios as permissive for insert to anon with check (true);
create policy usuarios_select_anon on public.usuarios as permissive for select to anon using (true);
create policy usuarios_update_anon on public.usuarios as permissive for update to anon using (true) with check (true);

grant select, insert, update, delete on public.usuarios_operacionais to anon;
create policy usuarios_operacionais_delete_anon on public.usuarios_operacionais as permissive for delete to anon using (true);
create policy usuarios_operacionais_insert_anon on public.usuarios_operacionais as permissive for insert to anon with check (true);
create policy usuarios_operacionais_select_anon on public.usuarios_operacionais as permissive for select to anon using (true);
create policy usuarios_operacionais_update_anon on public.usuarios_operacionais as permissive for update to anon using (true) with check (true);

grant insert, update, delete on public.empresas to anon;
create policy "anon full access"   on public.empresas as permissive for all    to anon using (true) with check (true);
create policy empresas_insert_anon on public.empresas as permissive for insert to anon with check (true);
create policy empresas_update_anon on public.empresas as permissive for update to anon using (true) with check (true);

grant insert, update, delete on public.licencas to anon;
create policy "anon full access"   on public.licencas as permissive for all    to anon using (true) with check (true);
create policy licencas_insert_anon on public.licencas as permissive for insert to anon with check (true);
create policy licencas_update_anon on public.licencas as permissive for update to anon using (true) with check (true);

grant insert, update, delete on public.modulos to anon;
create policy "anon full access"  on public.modulos as permissive for all    to anon using (true) with check (true);
create policy modulos_insert_anon on public.modulos as permissive for insert to anon with check (true);
create policy modulos_update_anon on public.modulos as permissive for update to anon using (true) with check (true);

grant execute on function public.registrar_instalacao_wms(text) to public, anon, authenticated;
commit;
