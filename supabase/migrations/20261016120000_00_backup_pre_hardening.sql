-- ════════════════════════════════════════════════════════════════════
-- YALog WMS · Build 023 · MIGRAÇÃO 00 — BACKUP VERIFICÁVEL (pré-requisito)
-- Projeto: yalog-os (pyckcyaojztixsujbylq)
-- Estado: PREPARADA — NÃO APLICADA EM PRODUÇÃO.
--
-- Cria o schema privado `backup_20261016` (não exposto pela API REST) com:
--   • foto das políticas RLS e das funções do schema public;
--   • cópia integral das tabelas que as migrações 01–03 afetam.
-- Nada é alterado em public. Executar ANTES das migrações 01/02/03.
-- Não apaga nem modifica backups/snapshots existentes
-- (wms_kv_store_backup_tenant002b, wms_recovery_snapshot_20261016).
-- ════════════════════════════════════════════════════════════════════
begin;

create schema if not exists backup_20261016;
revoke all on schema backup_20261016 from public, anon, authenticated;

create table backup_20261016.pg_policies_public as
  select now() as capturado_em, * from pg_policies where schemaname = 'public';

create table backup_20261016.funcoes_public as
  select now() as capturado_em, p.proname, pg_get_function_identity_arguments(p.oid) as args,
         p.prosecdef as security_definer, p.proconfig, p.proacl::text as acl,
         pg_get_functiondef(p.oid) as definicao
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public' and p.prokind = 'f';

create table backup_20261016.grants_public as
  select now() as capturado_em, * from information_schema.role_table_grants
   where table_schema = 'public' and grantee in ('anon','authenticated');

create table backup_20261016.logs                  as table public.logs;
create table backup_20261016.usuarios              as table public.usuarios;
create table backup_20261016.usuarios_operacionais as table public.usuarios_operacionais;
create table backup_20261016.company_installations as table public.company_installations;
create table backup_20261016.module_sessions       as table public.module_sessions;

-- Verificação (deve retornar contagens iguais origem × backup):
-- select 'logs', (select count(*) from public.logs), (select count(*) from backup_20261016.logs)
-- union all select 'usuarios', (select count(*) from public.usuarios), (select count(*) from backup_20261016.usuarios)
-- union all select 'usuarios_operacionais', (select count(*) from public.usuarios_operacionais), (select count(*) from backup_20261016.usuarios_operacionais)
-- union all select 'company_installations', (select count(*) from public.company_installations), (select count(*) from backup_20261016.company_installations)
-- union all select 'policies', (select count(*) from pg_policies where schemaname='public'), (select count(*) from backup_20261016.pg_policies_public);

commit;
