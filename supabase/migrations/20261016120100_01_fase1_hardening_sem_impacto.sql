-- ════════════════════════════════════════════════════════════════════
-- YALog WMS · Build 023 · MIGRAÇÃO 01 — FASE 1 (menor privilégio sem
-- impacto nos fluxos do WMS)
-- Estado: PREPARADA e TESTADA EM RÉPLICA ISOLADA (PGlite) — NÃO APLICADA
-- EM PRODUÇÃO. Pré-requisito: migração 00 (backup).
-- Rollback: 20261016120100_01_fase1_hardening_sem_impacto.rollback.sql
--
-- 1.1 logs — trilha de auditoria apagável/alterável por qualquer pessoa
--     com a chave pública. Mantém SELECT e INSERT para anon (únicas
--     operações usadas pelo WMS: insert em _gravarAuditoriaPlatform).
--     ⚠ Confirmar antes que a Platform não executa UPDATE/DELETE em logs.
-- 1.2 search_path fixo nas 3 funções apontadas pelo advisor.
-- 1.3 wms_kv_store_auditoria é função de TRIGGER: não precisa de EXECUTE
--     via API (o trigger continua disparando — validado na réplica).
-- ════════════════════════════════════════════════════════════════════
begin;

-- 1.1 logs: remove políticas de escrita destrutiva para anon
drop policy if exists "anon full access" on public.logs;
drop policy if exists logs_delete        on public.logs;
drop policy if exists logs_update        on public.logs;
-- (permanecem: logs_select, logs_select_anon, logs_insert, logs_insert_anon)
revoke update, delete on public.logs from anon;

-- 1.2 search_path imutável
alter function public.set_updated_at()                       set search_path = public, pg_catalog;
alter function public.gen_random_bytes(integer)              set search_path = public, pg_catalog;
alter function public._patio_entidade_para_recurso(text)     set search_path = public, pg_catalog;

-- 1.3 função de trigger fora da API
revoke execute on function public.wms_kv_store_auditoria() from public, anon, authenticated;

commit;
