-- ════════════════════════════════════════════════════════════════════
-- YALog WMS · Build 023 · MIGRAÇÃO 02 — FASE 2 (ADITIVA)
-- Estado: PREPARADA e TESTADA EM RÉPLICA ISOLADA (PGlite) — NÃO APLICADA
-- EM PRODUÇÃO. Não remove nenhuma permissão: só cria funções novas.
-- Rollback: 20261016120200_02_fase2_rpcs_sessao_wms.rollback.sql
--
-- Objetivo: permitir que o WMS deixe de ler `senha_hash` direto das tabelas
-- (hoje qualquer portador da chave pública lê todos os hashes) e passe a
-- ter uma sessão de servidor também no login manual. Depois que o WMS e a
-- Platform usarem estas funções, a FASE 3 (migração 03) remove o acesso
-- direto de `anon` às tabelas sensíveis.
--
--   wms_criar_sessao(company, login, senha_hash)  → status + token (sem hash)
--   wms_validar_sessao(token)                      → identidade (operacional ou Master)
--   wms_revogar_sessao(token)                      → logout no servidor
--   wms_operacionais_listar(token)                 → usuários SEM senha_hash
--   wms_operacionais_salvar(token, jsonb)          → cria/edita (Master/Líder)
--   wms_operacionais_excluir(token, id)            → exclui (somente Master)
--   registrar_instalacao_wms_v2(token)             → vínculo da instalação
--                                                    exige sessão válida
-- Isolamento: toda função deriva company_id da SESSÃO, nunca do cliente.
-- ════════════════════════════════════════════════════════════════════
begin;

-- Contexto de uma sessão válida (uso interno — sem EXECUTE para a API).
create or replace function public._wms_sessao_contexto(p_token text)
returns table(company_id text, login text, nome text, perfil text, origem text)
language plpgsql stable security definer set search_path = public, pg_catalog as $$
declare s record; u record; o record;
begin
  select ms.* into s from public.module_sessions ms
   where ms.token = p_token and ms.modulo = 'wms' and ms.revoked_at is null and ms.expires_at > now();
  if not found then return; end if;
  -- Empresa / licença / módulo continuam obrigatórios a cada uso da sessão
  if not exists (select 1 from public.empresas e where e.company_id = s.company_id and e.ativo) then return; end if;
  if not exists (select 1 from public.licencas l where l.company_id = s.company_id and l.status = 'ATIVA'
                  and (l.validade is null or l.validade >= current_date)) then return; end if;
  if not exists (select 1 from public.modulos m where m.company_id = s.company_id and lower(m.modulo) = 'wms'
                  and m.status = 'LIBERADO') then return; end if;
  select * into o from public.usuarios_operacionais x
   where x.company_id = s.company_id and lower(trim(x.login)) = lower(trim(s.login)) limit 1;
  if found then
    if o.ativo is false then return; end if;
    return query select s.company_id, o.login, o.nome, coalesce(o.perfil,'conferente'), 'operacional'::text; return;
  end if;
  select * into u from public.usuarios x
   where x.company_id = s.company_id and lower(x.login) = lower(s.login) limit 1;
  if found and u.ativo is not false and u.role in ('MASTER','GESTOR','SUPER_ADMIN') then
    return query select s.company_id, u.login, u.nome, 'master'::text, 'platform'::text;
  end if;
end $$;

create or replace function public.wms_criar_sessao(p_company_id text, p_login text, p_senha_hash text)
returns table(status text, module_session_token text, user_id text, nome text, perfil text, origem text, obrigar_troca_senha boolean)
language plpgsql security definer set search_path = public, pg_catalog as $$
declare v_cid text := upper(trim(coalesce(p_company_id,''))); v_login text := lower(trim(coalesce(p_login,'')));
        v_tok text; o record; u record;
begin
  if not exists (select 1 from public.empresas e where e.company_id = v_cid and e.ativo) then
    return query select 'empresa-inativa'::text, null::text, null::text, null::text, null::text, null::text, null::boolean; return; end if;
  if not exists (select 1 from public.licencas l where l.company_id = v_cid and l.status = 'ATIVA') then
    return query select 'licenca-inativa'::text, null::text, null::text, null::text, null::text, null::text, null::boolean; return; end if;
  if exists (select 1 from public.licencas l where l.company_id = v_cid and l.validade is not null and l.validade < current_date) then
    return query select 'licenca-vencida'::text, null::text, null::text, null::text, null::text, null::text, null::boolean; return; end if;
  if not exists (select 1 from public.modulos m where m.company_id = v_cid and lower(m.modulo) = 'wms' and m.status = 'LIBERADO') then
    return query select 'modulo-bloqueado'::text, null::text, null::text, null::text, null::text, null::text, null::boolean; return; end if;

  select * into o from public.usuarios_operacionais x where x.company_id = v_cid and lower(trim(x.login)) = v_login limit 1;
  if found then
    if o.ativo is false then return query select 'inativo'::text, null::text, null::text, null::text, null::text, null::text, null::boolean; return; end if;
    if o.senha_hash is distinct from p_senha_hash then return query select 'senha-invalida'::text, null::text, null::text, null::text, null::text, null::text, null::boolean; return; end if;
    insert into public.module_sessions(token, company_id, login, modulo)
      values (encode(public.gen_random_bytes(32), 'hex'), v_cid, o.login, 'wms') returning token into v_tok;
    update public.usuarios_operacionais set ultimo_login = now() where id = o.id;
    return query select 'ok'::text, v_tok, o.id::text, o.nome, coalesce(o.perfil,'conferente'), 'operacional'::text, coalesce(o.obrigar_troca_senha,false); return;
  end if;

  select * into u from public.usuarios x where x.company_id = v_cid and lower(x.login) = v_login limit 1;
  if not found then return query select 'nao-encontrado'::text, null::text, null::text, null::text, null::text, null::text, null::boolean; return; end if;
  if u.ativo is false then return query select 'inativo'::text, null::text, null::text, null::text, null::text, null::text, null::boolean; return; end if;
  if u.senha_hash is distinct from p_senha_hash then return query select 'senha-invalida'::text, null::text, null::text, null::text, null::text, null::text, null::boolean; return; end if;
  if u.role not in ('MASTER','GESTOR','SUPER_ADMIN') then return query select 'perfil-nao-autorizado'::text, null::text, null::text, null::text, null::text, null::text, null::boolean; return; end if;
  insert into public.module_sessions(token, company_id, login, modulo)
    values (encode(public.gen_random_bytes(32), 'hex'), v_cid, u.login, 'wms') returning token into v_tok;
  return query select 'ok'::text, v_tok, u.id::text, u.nome, 'master'::text, 'platform'::text, coalesce(u.obrigar_troca_senha,false);
end $$;

create or replace function public.wms_validar_sessao(p_token text)
returns table(company_id text, login text, nome text, perfil text, origem text)
language plpgsql security definer set search_path = public, pg_catalog as $$
begin
  return query select * from public._wms_sessao_contexto(p_token);
  if found then
    update public.module_sessions set last_seen_at = now(), expires_at = now() + interval '12 hours'
     where token = p_token and modulo = 'wms' and revoked_at is null;
  end if;
end $$;

create or replace function public.wms_revogar_sessao(p_token text)
returns boolean language plpgsql security definer set search_path = public, pg_catalog as $$
begin
  update public.module_sessions set revoked_at = now() where token = p_token and modulo = 'wms' and revoked_at is null;
  return true;
end $$;

create or replace function public.wms_operacionais_listar(p_token text)
returns table(id uuid, company_id text, login text, nome text, perfil text, ativo boolean, obrigar_troca_senha boolean,
              ultimo_login timestamptz, ultima_troca_senha timestamptz, criado_em timestamptz, atualizado_em timestamptz)
language plpgsql security definer set search_path = public, pg_catalog as $$
declare c record;
begin
  select * into c from public._wms_sessao_contexto(p_token) limit 1;
  if not found or c.perfil not in ('master','lider') then raise exception 'NAO_AUTORIZADO' using errcode = '42501'; end if;
  return query select u.id, u.company_id, u.login, u.nome, u.perfil, u.ativo, u.obrigar_troca_senha,
                      u.ultimo_login, u.ultima_troca_senha, u.criado_em, u.atualizado_em
                 from public.usuarios_operacionais u where u.company_id = c.company_id order by u.nome;
end $$;

create or replace function public.wms_operacionais_salvar(p_token text, p_usuario jsonb)
returns uuid language plpgsql security definer set search_path = public, pg_catalog as $$
declare c record; v_id uuid; v_login text := lower(trim(coalesce(p_usuario->>'login','')));
begin
  select * into c from public._wms_sessao_contexto(p_token) limit 1;
  if not found or c.perfil not in ('master','lider') then raise exception 'NAO_AUTORIZADO' using errcode = '42501'; end if;
  if v_login = '' or v_login ~ '\s' then raise exception 'LOGIN_INVALIDO' using errcode = '22023'; end if;
  if coalesce(p_usuario->>'perfil','') not in ('lider','analista','administrativo','conferente','operador') then
    raise exception 'PERFIL_INVALIDO' using errcode = '22023'; end if;
  v_id := nullif(p_usuario->>'id','')::uuid;
  if v_id is not null and exists (select 1 from public.usuarios_operacionais u where u.id = v_id) then
    -- edição: só dentro da própria empresa (company_id vem da sessão)
    update public.usuarios_operacionais u set
      login = v_login, nome = coalesce(p_usuario->>'nome', u.nome), perfil = p_usuario->>'perfil',
      ativo = coalesce((p_usuario->>'ativo')::boolean, u.ativo),
      obrigar_troca_senha = coalesce((p_usuario->>'obrigar_troca_senha')::boolean, u.obrigar_troca_senha),
      senha_hash = coalesce(nullif(p_usuario->>'senha_hash',''), u.senha_hash),
      ultima_troca_senha = case when nullif(p_usuario->>'senha_hash','') is not null then now() else u.ultima_troca_senha end,
      atualizado_em = now(), versao = coalesce(u.versao,1) + 1
     where u.id = v_id and u.company_id = c.company_id;
    if not found then raise exception 'NAO_AUTORIZADO' using errcode = '42501'; end if;
    return v_id;
  end if;
  if exists (select 1 from public.usuarios_operacionais u where u.company_id = c.company_id and lower(trim(u.login)) = v_login) then
    raise exception 'LOGIN_DUPLICADO' using errcode = '23505'; end if;
  if coalesce(p_usuario->>'senha_hash','') = '' then raise exception 'SENHA_OBRIGATORIA' using errcode = '22023'; end if;
  insert into public.usuarios_operacionais(id, company_id, login, nome, perfil, senha_hash, ativo, obrigar_troca_senha, origem, modulo)
  values (coalesce(v_id, gen_random_uuid()), c.company_id, v_login, p_usuario->>'nome', p_usuario->>'perfil', p_usuario->>'senha_hash',
          coalesce((p_usuario->>'ativo')::boolean, true), coalesce((p_usuario->>'obrigar_troca_senha')::boolean, false), 'WMS', 'WMS')
  returning id into v_id;
  return v_id;
end $$;

create or replace function public.wms_operacionais_excluir(p_token text, p_id uuid)
returns boolean language plpgsql security definer set search_path = public, pg_catalog as $$
declare c record;
begin
  select * into c from public._wms_sessao_contexto(p_token) limit 1;
  if not found or c.perfil <> 'master' then raise exception 'NAO_AUTORIZADO' using errcode = '42501'; end if;
  delete from public.usuarios_operacionais u where u.id = p_id and u.company_id = c.company_id;
  return found;
end $$;

create or replace function public.registrar_instalacao_wms_v2(p_module_session_token text)
returns uuid language plpgsql security definer set search_path = public, pg_catalog as $$
declare c record; v_inst uuid := auth.uid();
begin
  if v_inst is null then raise exception 'INSTALACAO_NAO_AUTENTICADA' using errcode = '42501'; end if;
  select * into c from public._wms_sessao_contexto(p_module_session_token) limit 1;
  if not found then raise exception 'SESSAO_INVALIDA' using errcode = '42501'; end if;
  insert into public.company_installations(installation_id, company_id) values (v_inst, c.company_id)
  on conflict (installation_id) do update set company_id = excluded.company_id, updated_at = now();
  return v_inst;
end $$;

-- Permissões: só as funções públicas da API; a auxiliar fica interna.
revoke all on function public._wms_sessao_contexto(text) from public, anon, authenticated;
revoke all on function public.wms_criar_sessao(text,text,text) from public;
revoke all on function public.wms_validar_sessao(text) from public;
revoke all on function public.wms_revogar_sessao(text) from public;
revoke all on function public.wms_operacionais_listar(text) from public;
revoke all on function public.wms_operacionais_salvar(text,jsonb) from public;
revoke all on function public.wms_operacionais_excluir(text,uuid) from public;
revoke all on function public.registrar_instalacao_wms_v2(text) from public;
grant execute on function public.wms_criar_sessao(text,text,text)      to anon, authenticated;
grant execute on function public.wms_validar_sessao(text)              to anon, authenticated;
grant execute on function public.wms_revogar_sessao(text)              to anon, authenticated;
grant execute on function public.wms_operacionais_listar(text)         to anon, authenticated;
grant execute on function public.wms_operacionais_salvar(text,jsonb)   to anon, authenticated;
grant execute on function public.wms_operacionais_excluir(text,uuid)   to anon, authenticated;
grant execute on function public.registrar_instalacao_wms_v2(text)     to authenticated;

commit;
