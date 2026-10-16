-- ROLLBACK da MIGRAÇÃO 02 — remove somente as funções criadas por ela.
-- Sessões já emitidas em module_sessions (modulo='wms') são revogadas,
-- não apagadas (trilha preservada).
begin;
update public.module_sessions set revoked_at = now()
 where modulo = 'wms' and revoked_at is null
   and created_at >= timestamptz '2026-10-16 00:00:00-03';
drop function if exists public.registrar_instalacao_wms_v2(text);
drop function if exists public.wms_operacionais_excluir(text,uuid);
drop function if exists public.wms_operacionais_salvar(text,jsonb);
drop function if exists public.wms_operacionais_listar(text);
drop function if exists public.wms_revogar_sessao(text);
drop function if exists public.wms_validar_sessao(text);
drop function if exists public.wms_criar_sessao(text,text,text);
drop function if exists public._wms_sessao_contexto(text);
commit;
