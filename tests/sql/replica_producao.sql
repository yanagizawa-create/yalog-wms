-- Réplica ISOLADA (somente para teste) das tabelas, políticas, grants e
-- funções de produção relevantes ao WMS, capturadas por consulta somente
-- leitura em 16/10/2026 (pg_policies, information_schema, pg_get_functiondef).
-- Dados: exclusivamente fictícios de TESTE.
create role anon nologin; create role authenticated nologin;
create schema auth;
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to anon, authenticated; grant execute on function auth.uid() to anon, authenticated;
grant usage on schema public to anon, authenticated;

create table public.empresas(company_id text primary key, razao_social text, nome_fantasia text, cnpj text, responsavel text, email text, telefone text, ativo boolean default true, created_at timestamptz default now(), updated_at timestamptz default now());
create table public.licencas(company_id text primary key references public.empresas(company_id) on delete cascade, plano text default 'FREE', status text default 'ATIVA' check (status in ('ATIVA','SUSPENSA','EXPIRADA')), validade date, qtd_usuarios int default 1, qtd_modulos int default 0, created_at timestamptz default now(), updated_at timestamptz default now());
create table public.modulos(id bigserial primary key, company_id text references public.empresas(company_id) on delete cascade, modulo text, status text default 'BLOQUEADO' check (status in ('LIBERADO','BLOQUEADO')), liberado_em timestamptz, created_at timestamptz default now(), updated_at timestamptz default now(), unique(company_id, modulo));
create table public.usuarios(id bigserial primary key, company_id text references public.empresas(company_id) on delete cascade, login text, nome text, senha_hash text, role text default 'USUARIO' check (role in ('SUPER_ADMIN','GESTOR','MASTER','USUARIO')), ativo boolean default true, created_at timestamptz default now(), updated_at timestamptz default now(), obrigar_troca_senha boolean default false, email text, unique(company_id, login));
create table public.usuarios_operacionais(id uuid primary key default gen_random_uuid(), company_id text, login text, nome text, perfil text, senha_hash text, ativo boolean default true, obrigar_troca_senha boolean default false, ultimo_login timestamptz, ultima_troca_senha timestamptz, criado_em timestamptz default now(), atualizado_em timestamptz default now(), origem text default 'WMS', modulo text default 'WMS', nivel int default 1, versao int default 1);
create table public.logs(id bigserial primary key, tipo text, detalhe text, company_id text references public.empresas(company_id) on delete set null, created_at timestamptz default now());
create table public.company_installations(installation_id uuid primary key, company_id text references public.empresas(company_id) on delete cascade, created_at timestamptz default now(), updated_at timestamptz default now());
create table public.module_sessions(token text primary key, company_id text, login text, modulo text, created_at timestamptz default now(), expires_at timestamptz default now() + interval '12 hours', last_seen_at timestamptz default now(), revoked_at timestamptz);
create table public.platform_modules(id uuid primary key default gen_random_uuid(), module_id text unique, status text default 'DRAFT');
create table public.wms_kv_store(id uuid primary key default gen_random_uuid(), key text check (key is not null and length(key) > 0), value jsonb check (value is not null), updated_at timestamptz default now(), installation_id uuid, created_at timestamptz default now(), created_by uuid, updated_by uuid, version int default 1, company_id text, module_id text, unique(company_id, module_id, key));

-- grants (iguais a produção)
grant select, insert, update, delete on public.empresas, public.licencas, public.modulos, public.usuarios, public.usuarios_operacionais, public.logs to anon, authenticated;
grant all on public.company_installations, public.module_sessions, public.wms_kv_store, public.platform_modules to anon, authenticated;
grant usage on all sequences in schema public to anon, authenticated;
alter table public.empresas enable row level security; alter table public.licencas enable row level security; alter table public.modulos enable row level security;
alter table public.usuarios enable row level security; alter table public.usuarios_operacionais enable row level security; alter table public.logs enable row level security;
alter table public.company_installations enable row level security; alter table public.module_sessions enable row level security; alter table public.wms_kv_store enable row level security; alter table public.platform_modules enable row level security;

-- políticas (iguais a produção)
create policy "anon full access" on public.empresas for all to anon using (true) with check (true);
create policy empresas_insert_anon on public.empresas for insert to anon with check (true);
create policy empresas_select_anon on public.empresas for select to anon using (true);
create policy empresas_update_anon on public.empresas for update to anon using (true) with check (true);
create policy "anon full access" on public.licencas for all to anon using (true) with check (true);
create policy licencas_insert_anon on public.licencas for insert to anon with check (true);
create policy licencas_select_anon on public.licencas for select to anon using (true);
create policy licencas_update_anon on public.licencas for update to anon using (true) with check (true);
create policy "anon full access" on public.modulos for all to anon using (true) with check (true);
create policy modulos_insert_anon on public.modulos for insert to anon with check (true);
create policy modulos_select_anon on public.modulos for select to anon using (true);
create policy modulos_update_anon on public.modulos for update to anon using (true) with check (true);
create policy "anon full access" on public.usuarios for all to anon using (true) with check (true);
create policy usuarios_insert_anon on public.usuarios for insert to anon with check (true);
create policy usuarios_select_anon on public.usuarios for select to anon using (true);
create policy usuarios_update_anon on public.usuarios for update to anon using (true) with check (true);
create policy usuarios_operacionais_delete_anon on public.usuarios_operacionais for delete to anon using (true);
create policy usuarios_operacionais_insert_anon on public.usuarios_operacionais for insert to anon with check (true);
create policy usuarios_operacionais_select_anon on public.usuarios_operacionais for select to anon using (true);
create policy usuarios_operacionais_update_anon on public.usuarios_operacionais for update to anon using (true) with check (true);
create policy "anon full access" on public.logs for all to anon using (true) with check (true);
create policy logs_delete on public.logs for delete to anon using (true);
create policy logs_insert on public.logs for insert to anon with check (true);
create policy logs_insert_anon on public.logs for insert to anon with check (true);
create policy logs_select on public.logs for select to anon using (true);
create policy logs_select_anon on public.logs for select to anon using (true);
create policy logs_update on public.logs for update to anon using (true) with check (true);
create policy company_installations_select_own on public.company_installations for select to authenticated using (installation_id = auth.uid());
create policy platform_modules_all on public.platform_modules for all to public using (true) with check (true);
create policy wms_kv_select on public.wms_kv_store for select to authenticated using (((company_id = 'PLATFORM') and (installation_id = auth.uid())) or exists (select 1 from public.company_installations ci where ci.installation_id = auth.uid() and ci.company_id = wms_kv_store.company_id));
create policy wms_kv_insert on public.wms_kv_store for insert to authenticated with check (((company_id = 'PLATFORM') and (installation_id = auth.uid())) or exists (select 1 from public.company_installations ci where ci.installation_id = auth.uid() and ci.company_id = wms_kv_store.company_id));
create policy wms_kv_update on public.wms_kv_store for update to authenticated using (((company_id = 'PLATFORM') and (installation_id = auth.uid())) or exists (select 1 from public.company_installations ci where ci.installation_id = auth.uid() and ci.company_id = wms_kv_store.company_id)) with check (((company_id = 'PLATFORM') and (installation_id = auth.uid())) or exists (select 1 from public.company_installations ci where ci.installation_id = auth.uid() and ci.company_id = wms_kv_store.company_id));

-- funções (definições de produção)
create function public.set_updated_at() returns trigger language plpgsql as $$ begin new.updated_at = now(); return new; end; $$;
create function public.gen_random_bytes(p_count integer) returns bytea language plpgsql as $$
declare v_result bytea := ''::bytea; begin if p_count is null or p_count < 0 then raise exception 'p_count deve ser >= 0'; end if;
while octet_length(v_result) < p_count loop v_result := v_result || decode(replace(gen_random_uuid()::text, '-', ''), 'hex'); end loop;
return substring(v_result from 1 for p_count); end; $$;
create function public._patio_entidade_para_recurso(p_entity text) returns text language plpgsql immutable as $$ begin return case p_entity when 'entradas' then 'entradas' else null end; end; $$;
create function public.wms_kv_store_auditoria() returns trigger language plpgsql security definer set search_path to 'public' as $$
begin if tg_op = 'INSERT' then new.created_at := now(); new.created_by := auth.uid(); new.updated_at := now(); new.updated_by := auth.uid(); new.version := 1;
elsif tg_op = 'UPDATE' then new.created_at := old.created_at; new.created_by := old.created_by; new.updated_at := now(); new.updated_by := auth.uid(); new.version := coalesce(old.version, 1) + 1; end if; return new; end; $$;
create trigger trg_wms_kv_store_auditoria before insert or update on public.wms_kv_store for each row execute function public.wms_kv_store_auditoria();
create trigger trg_usuarios_updated_at before update on public.usuarios for each row execute function public.set_updated_at();
create function public.registrar_instalacao_wms(p_company_id text) returns uuid language plpgsql security definer set search_path to 'public' as $$
declare v_installation_id uuid; begin v_installation_id := auth.uid(); if v_installation_id is null then raise exception 'Instalação não autenticada.'; end if;
if not exists (select 1 from public.empresas where company_id = p_company_id and ativo = true) then raise exception 'Empresa inexistente ou inativa.'; end if;
if not exists (select 1 from public.licencas where company_id = p_company_id and status = 'ATIVA' and (validade is null or validade >= current_date)) then raise exception 'Licença inexistente, suspensa ou expirada.'; end if;
if not exists (select 1 from public.modulos where company_id = p_company_id and lower(modulo) = 'wms' and status = 'LIBERADO') then raise exception 'Módulo WMS não está liberado para esta empresa.'; end if;
insert into public.company_installations (installation_id, company_id) values (v_installation_id, p_company_id) on conflict (installation_id) do update set company_id = excluded.company_id, updated_at = now();
return v_installation_id; end; $$;
grant execute on all functions in schema public to public, anon, authenticated;

-- dados de TESTE
insert into public.empresas(company_id, nome_fantasia, ativo) values ('YLG-TESTE-01','EMPRESA TESTE 01',true),('YLG-TESTE-02','EMPRESA TESTE 02',true),('YLG-TESTE-BLOQ','EMPRESA BLOQUEADA',false);
insert into public.licencas(company_id, status) values ('YLG-TESTE-01','ATIVA'),('YLG-TESTE-02','ATIVA'),('YLG-TESTE-BLOQ','ATIVA');
insert into public.modulos(company_id, modulo, status) values ('YLG-TESTE-01','wms','LIBERADO'),('YLG-TESTE-02','wms','LIBERADO'),('YLG-TESTE-BLOQ','wms','LIBERADO');
insert into public.platform_modules(module_id, status) values ('wms','ACTIVE');
insert into public.usuarios(company_id, login, nome, senha_hash, role) values ('YLG-TESTE-01','master.teste','Master Teste','HASH-MASTER','MASTER'),('YLG-TESTE-02','master.dois','Master Dois','HASH-M2','MASTER');
insert into public.usuarios_operacionais(company_id, login, nome, perfil, senha_hash, ativo) values
 ('YLG-TESTE-01','lider.teste','Lider Teste','lider','HASH-LIDER',true),
 ('YLG-TESTE-01','operador.teste','Operador Teste','operador','HASH-OP',true),
 ('YLG-TESTE-01','inativo.teste','Inativo Teste','conferente','HASH-IN',false),
 ('YLG-TESTE-02','lider.dois','Lider Dois','lider','HASH-L2',true);
insert into public.logs(tipo, detalhe, company_id) values ('TESTE','log existente','YLG-TESTE-01');
