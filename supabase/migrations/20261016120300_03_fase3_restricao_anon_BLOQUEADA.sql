-- ════════════════════════════════════════════════════════════════════
-- YALog WMS · Build 023 · MIGRAÇÃO 03 — FASE 3 (RESTRITIVA)
-- Estado: PREPARADA e TESTADA EM RÉPLICA ISOLADA — ⛔ BLOQUEADA PARA
-- PRODUÇÃO até que, comprovadamente:
--   (a) o WMS use as RPCs da migração 02 no login, na gestão de usuários
--       operacionais e no vínculo de instalação (sprint de frontend
--       própria — NÃO incluída na Build 023);
--   (b) a YALog Platform deixe de gravar empresas/usuarios/licencas/modulos
--       com a chave pública (anon) — rotas administrativas autenticadas
--       ou Edge Function com service_role no SERVIDOR;
--   (c) os demais módulos que leem essas tabelas sejam mapeados.
-- Aplicar antes disso QUEBRA o login do WMS e o cadastro da Platform.
-- Rollback: 20261016120300_03_fase3_restricao_anon_BLOQUEADA.rollback.sql
--
-- Risco corrigido: hoje, com a chave pública embutida no HTML, qualquer
-- pessoa lê todos os senha_hash (SHA-256 sem sal), cria/edita usuários
-- Master, altera licenças/módulos e vincula uma instalação anônima a
-- qualquer empresa (registrar_instalacao_wms) para ler o wms_kv_store dela.
-- ════════════════════════════════════════════════════════════════════
begin;

-- usuarios / usuarios_operacionais: nenhum acesso direto por anon
drop policy if exists "anon full access"                  on public.usuarios;
drop policy if exists usuarios_insert_anon                on public.usuarios;
drop policy if exists usuarios_select_anon                on public.usuarios;
drop policy if exists usuarios_update_anon                on public.usuarios;
revoke select, insert, update, delete on public.usuarios from anon;

drop policy if exists usuarios_operacionais_delete_anon   on public.usuarios_operacionais;
drop policy if exists usuarios_operacionais_insert_anon   on public.usuarios_operacionais;
drop policy if exists usuarios_operacionais_select_anon   on public.usuarios_operacionais;
drop policy if exists usuarios_operacionais_update_anon   on public.usuarios_operacionais;
revoke select, insert, update, delete on public.usuarios_operacionais from anon;

-- empresas / licencas / modulos: anon mantém apenas leitura
drop policy if exists "anon full access"     on public.empresas;
drop policy if exists empresas_insert_anon   on public.empresas;
drop policy if exists empresas_update_anon   on public.empresas;
revoke insert, update, delete on public.empresas from anon;

drop policy if exists "anon full access"     on public.licencas;
drop policy if exists licencas_insert_anon   on public.licencas;
drop policy if exists licencas_update_anon   on public.licencas;
revoke insert, update, delete on public.licencas from anon;

drop policy if exists "anon full access"     on public.modulos;
drop policy if exists modulos_insert_anon    on public.modulos;
drop policy if exists modulos_update_anon    on public.modulos;
revoke insert, update, delete on public.modulos from anon;

-- Vínculo de instalação só com prova de sessão (v2, migração 02)
revoke execute on function public.registrar_instalacao_wms(text) from public, anon, authenticated;

commit;
