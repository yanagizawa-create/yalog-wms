# Plano de segurança do Supabase — YALog WMS · Build 023

Projeto: `yalog-os` (`pyckcyaojztixsujbylq`). Auditoria feita em 16/10/2026 **somente leitura** (consultas a `pg_policies`, `information_schema`, `pg_proc` e advisors). **Nenhuma migração foi aplicada em produção.**

| Arquivo | Estado | Pode aplicar? |
|---|---|---|
| `…_00_backup_pre_hardening.sql` | Preparada · testada em réplica | Sim — primeiro |
| `…_01_fase1_hardening_sem_impacto.sql` (+ `.rollback.sql`) | Preparada · testada em réplica | Sim, após 00 e após confirmar que a Platform não faz UPDATE/DELETE em `logs` |
| `…_02_fase2_rpcs_sessao_wms.sql` (+ `.rollback.sql`) | Preparada · testada em réplica | Sim — só cria funções, não remove nada |
| `…_03_fase3_restricao_anon_BLOQUEADA.sql` (+ `.rollback.sql`) | Preparada · testada em réplica | **Não** — depende de mudanças no WMS e na Platform (ver abaixo) |

Teste em réplica isolada: `tests/sql/testar_migracoes.js` (PostgreSQL 18 via PGlite, com as políticas, grants e funções de produção reproduzidas fielmente). Resultado: **42/42 aprovados** — inclui confirmação dos riscos antes, acesso autorizado e negado depois, isolamento entre empresas e rollback com políticas idênticas ao backup.

## Achados confirmados no estado atual

| # | Risco | Evidência |
|---|---|---|
| A1 | **Crítico** — `anon` lê `senha_hash` de `usuarios` e `usuarios_operacionais` (SHA-256 sem sal de `senha::yalog`), com a chave pública que está no HTML | Políticas `anon full access`/`*_select_anon` com `using (true)`; teste S00 |
| A2 | **Crítico** — `anon` cria/edita empresas, licenças, módulos e usuários Master | Políticas `ALL`/`INSERT`/`UPDATE` com `true` |
| A3 | **Alto** — qualquer instalação anônima se vincula a qualquer empresa ativa via `registrar_instalacao_wms(p_company_id)` e passa a ler/gravar o `wms_kv_store` dela | Função `SECURITY DEFINER` sem prova de identidade; teste S00 |
| A4 | Alto — trilha `logs` apagável/alterável por `anon` | `logs_delete`, `logs_update`, `anon full access` |
| A5 | Médio — 3 funções com `search_path` mutável | Advisor `function_search_path_mutable` |
| A6 | Baixo — função de trigger `wms_kv_store_auditoria` exposta via `/rpc` | Advisor `anon_security_definer_function_executable` |
| A7 | Info — 11 tabelas com RLS e sem políticas (acesso só via `SECURITY DEFINER`) — **intencional**, inclui os snapshots | Advisor `rls_enabled_no_policy` |
| A8 | Config — proteção de senha vazada desativada no Auth | Advisor; o WMS só usa login anônimo do Supabase Auth, impacto baixo — ativar no painel (Auth → Password security) |

## Matriz por alteração

| Alteração | Operação legítima afetada | Permissão necessária | Nova regra | Teste autorizado / negado | Rollback |
|---|---|---|---|---|---|
| 01 · `logs` sem UPDATE/DELETE para anon | WMS grava auditoria (`insert`); Platform lê/grava logs | `anon`: SELECT + INSERT | Remove `anon full access`, `logs_delete`, `logs_update`; revoga UPDATE/DELETE | S02 insert/select ✔ · delete/update ✘ | `.rollback.sql` recria as 3 políticas e os grants |
| 01 · `search_path` fixo | Triggers `updated_at`, geração de tokens | — | `set search_path = public, pg_catalog` | S02 trigger `updated_at` funciona | `reset search_path` |
| 01 · revoga EXECUTE da função de trigger | Trigger de auditoria do `wms_kv_store` | Nenhuma via API | `revoke execute … from public, anon, authenticated` | S02 trigger continua preenchendo `version/created_by` ✔ · chamada direta ✘ | `grant execute` |
| 02 · `wms_criar_sessao` | Login manual do WMS (hoje lê o hash direto) | EXECUTE para anon | Valida empresa/licença/módulo/usuário/hash **no servidor**; devolve token, nunca o hash | S03 ok / senha inválida / inativo / não encontrado / empresa bloqueada | Drop da função |
| 02 · `wms_validar_sessao` / `wms_revogar_sessao` | F5, logout | EXECUTE para anon | Sessão de 12 h renovável; revogação e desativação invalidam | S03 revogada ✘ · usuário desativado ✘ | Drop |
| 02 · `wms_operacionais_*` | Tela Usuários (gestão de operacionais) | EXECUTE para anon + token | Empresa vem da sessão; listar/salvar só Master/Líder; excluir só Master; nunca retorna hash | S03 operador ✘ · edição cross-tenant ✘ · líder exclui ✘ | Drop |
| 02 · `registrar_instalacao_wms_v2` | Vínculo instalação ↔ empresa (modo Supabase) | EXECUTE para authenticated + token | Exige sessão válida da empresa | S03 token falso ✘ · token válido ✔ | Drop |
| 03 · sem acesso direto de anon a `usuarios*`; anon só lê `empresas/licencas/modulos`; v1 do vínculo revogada | Login/gestão do WMS **e** cadastro da Platform | Via RPCs da 02 / rotas autenticadas da Platform | Remove políticas `anon` de escrita e de leitura de hashes | S04 hash ✘ · licença ✘ · login via RPC ✔ | `.rollback.sql` recria tudo |

## Por que a Fase 3 está bloqueada

1. O WMS (Build 023) ainda autentica lendo `usuarios`/`usuarios_operacionais` direto e grava usuários operacionais por `upsert`. Migrar para as RPCs da Fase 2 é uma sprint de frontend própria (login, F5 com token, tela Usuários, sincronização).
2. A YALog Platform (repositório separado, não auditado aqui) cadastra empresas, licenças, módulos e Masters com a chave pública. Ela precisa de rotas autenticadas (ou Edge Function com `service_role` **no servidor**) antes da Fase 3.
3. Outros módulos (Pátio, ContaLog, Radar) usam o mesmo projeto; `company_installations` recebeu vínculo em 12/10/2026 — mapear quem chama `registrar_instalacao_wms` antes de revogá-la.

## Ordem de execução recomendada

1. Aplicar **00** e conferir as contagens (consulta comentada no fim do arquivo).
2. Aplicar **01**; testar no WMS publicado: login, F5, auditoria aparecendo em `logs`; na Platform: tela de Logs.
3. Aplicar **02** (aditiva). Nenhum fluxo muda até o frontend usar as funções.
4. Sprint de frontend WMS + Platform usando a Fase 2; homologar.
5. Aplicar **03** em janela controlada, com `.rollback.sql` à mão.

Snapshots e backups existentes (`wms_kv_store_backup_tenant002b`, `wms_recovery_snapshot_20261016`) não são tocados por nenhuma migração.
