# YALog WMS — Build 023 · Recuperação, correção e liberação

- **Origem:** `main` @ `b9f88a0` (16/10/2026 13:38) — `index.html` v2.1.2 Build 022
- **Branch:** `fix/wms-persistencia-sessao-seguranca`
- **Arquivos:** `index.html` (corrigido, v2.1.3 Build 023) · `supabase/migrations/*` (preparadas, não aplicadas) · `tests/**` · `docs/BUILD-023-RELATORIO.md`
- **Estado final:** **APTO COM RESSALVAS** para publicar o `index.html` (ver §7). A exposição de dados no Supabase (§4) é **crítica, pré-existente e continua aberta** — não é alterada por esta publicação.

---

## 1. Defeitos encontrados e causas-raiz confirmadas

Todos reproduzidos no `index.html` original em Chromium antes de qualquer correção (`tests/browser/repro.py`, `multiaba.py`).

| # | Sintoma | Causa-raiz (ponto exato) | Reprodução no original |
|---|---|---|---|
| D1 | Base inteira some após F5/atualização | `save()` e o `beforeunload` (`_persistirDBCanonico(DB)`) gravavam o `DB` **antes de o `load()` terminar**. Com o espelho do localStorage indisponível (base grande/quota), o `DB` ainda vazio sobrescrevia `db-canonico` no IndexedDB. Qualquer F5 durante o carregamento, ou o `save()` do login, disparava | R4: 50 produtos + 1 cliente → **0 / 0**. R4b (só F5 duplo): **0 / 0** |
| D2 | Edições “voltam sozinhas”; exclusões reaparecem; IDs repetidos | `save()` mesclava o cofre `wms_data_vault_v1` e o `wms_db_guard_snapshot_v2` com `_mesclarDBSemPerda(DB, snapshot)`, em que **o snapshot vence campo a campo**. Com IndexedDB, esses snapshots não eram mais atualizados (ficaram congelados nas builds 014–017), então cada gravação revertia quantidades/status, reabria exclusões e regredia `seqWMS/seqRec…` (gerando IDs duplicados, que depois colapsam registros). O `load()` fazia o mesmo | R1: qtd editada 4 → **10** já no próprio `save()`; R1b: 7 → **10** após F5 |
| D3 | Dados de outra empresa aparecem | A base local era uma só por navegador e `_recuperarMelhorBasePersistida` / `_migrarParaEmpresa` mesclavam chaves `wms:<outra>:…`, cofres e snapshots de qualquer empresa | R3: empresa 01 vê cliente da 02; R3b: idem pelo cache legado |
| D4 | Sessão revogada continua valendo | `_tentarRestaurarSessaoWms` tratava “servidor disse inválido” igual a “rede falhou” e restaurava a sessão local mesmo com token revogado/expirado. Sessão local também nunca revalidava empresa/licença/usuário após F5 | R5: logado após F5 com token revogado = **true** |
| D5 | Duas abas: alterações perdidas | A aba desatualizada gravava a base inteira por cima | M2: edição da outra aba perdida e exclusão reaparece |
| D6 | Dashboard quebrado com estoque | `renderHome` usava `vertColor` sem declarar → `ReferenceError` interrompia a tela (painel de capacidade, ícones, gráficos não renderizavam) | F08: erro em `home`; 6 erros de página no roteiro |
| D7 | Risco de quebra externa | `lucide@latest` sem versão fixa (publicado diariamente) | — |

**F5 em condições normais já restaurava a sessão no original** (R6/R7 passaram nos dois). O retorno ao login relatado é explicado por D1 (base some e a sessão local reconstruída não acha o usuário/dados) e por exceções na restauração, agora tratadas sem derrubar a sessão.

## 2. Correções implementadas (`index.html`)

Todas restritas à camada de persistência/sessão, exceto D6 (1 linha) e D7 (URL). Sem mudança de layout, fluxo, permissão por perfil ou regra de negócio.

1. **Portão de hidratação** — nada é gravado (IndexedDB, espelho ou `beforeunload`) antes de a base da empresa ativa ser carregada. `save()` pré-carregamento vira pendente e é aplicado depois, de forma aditiva.
2. **`load()` serializado** (`_wmsLoadChain`) e aguardando gravações em andamento; boot e restauração de sessão não recarregam à toa (`_wmsGarantirBaseDaEmpresa`).
3. **Versão explícita** — `DB._persistMeta {schema, rev, companyId, build}`; entre IndexedDB e espelho vale o `rev` maior.
4. **Leitura confirmada** — `_idbLerRegistro` distingue “não existe” de “falhou” (3 tentativas). Falha de leitura **suspende** a gravação canônica na sessão e avisa o usuário; nunca presume base vazia.
5. **Snapshots legados** só são usados quando não há base desta empresa, e só **acrescentam** registros (nunca sobrescrevem campos); sequências nunca regridem.
6. **Isolamento por empresa** — dono da base por `_persistMeta.companyId` (ou inferido dos usuários). A base principal continua da empresa dona; outra empresa no mesmo navegador usa `db-canonico@<COMPANY>` e `wms:<COMPANY>:wms_3cs_v2026`. Logout limpa a empresa ativa.
7. **Pontos de restauração** — `db-canonico:inicio-sessao` (uma vez por abertura) e `db-canonico:anterior` (antes de reduções > 50 % e ≥ 20 registros, na mesma transação). Função `wmsRestaurarPontoDeRestauracao('anterior'|'inicio-sessao')` (console, só Master) guarda o estado atual em `:antes-restauracao`.
8. **Concorrência entre abas** — gravação com verificação de versão na mesma transação (`db-canonico:meta`) e mesclagem de 3 vias por registro (base × esta aba × outra aba).
9. **Sessão** — `_consultarSessaoModuloYalog` retorna `valida / invalida / indisponivel`: inválida encerra a sessão com mensagem; indisponível mantém (F5 offline não é logout). Após restaurar sessão local, revalidação em segundo plano encerra só com resposta autoritativa (empresa/licença/módulo bloqueados, usuário inativo/removido). Erro inesperado na restauração não apaga a sessão.
10. `vertColor` declarado (mesma regra/paleta de `chaoColor`); `lucide@1.58.0` fixado; versão `2.1.3 Build 023`.

Revisão do diff: `git diff b9f88a0 -- index.html` (+474/−137 linhas, quase tudo no bloco “BUILD 023”). 4 blocos `<script>` e 694 handlers inline com sintaxe validada, contagem idêntica ao original.

## 3. Relatório de testes

Ambiente: Chromium 141 headless (Playwright), IndexedDB/localStorage reais do navegador, perfis isolados por teste, dados de TESTE. **O Supabase foi simulado por rota** (o ambiente de execução não alcança `*.supabase.co`); o banco foi testado à parte em réplica (§4).

| Teste | Resultado | Evidência (resumo da saída) |
|---|---|---|
| Sintaxe (scripts + handlers) | APROVADO | 4 scripts, 694 handlers, 0 erros |
| R1 cofre antigo não reverte edição | APROVADO (original: FALHA) | qtd 4 → 4 após save e F5 |
| R1b snapshot antigo não reverte edição | APROVADO (original: FALHA) | 7 → 7 após F5 |
| R3 isolamento entre empresas | APROVADO (original: FALHA) | empresa 01 não vê cliente da 02, inclusive após F5 |
| R3b cache legado de outra empresa | APROVADO (original: FALHA) | nenhum cliente da 02 |
| R4 save antes do carregamento | APROVADO (original: FALHA 50→0) | 50/1 preservados |
| R4b F5 durante o carregamento | APROVADO (original: FALHA 50→0) | 50/1 preservados |
| R5 sessão revogada não restaura | APROVADO (original: FALHA) | logado = false |
| R6 F5 e Ctrl+R offline mantêm sessão | APROVADO | logado = true / true |
| R7 SSO com falha transitória | APROVADO | offline e online logado |
| R8 logout explícito | APROVADO | após logout+F5 = deslogado |
| P1 atualização de build preserva base antiga | APROVADO | base da 022 aberta pela 023: contagens e qtd iguais, `companyId` gravado |
| P2 salvar → F5 → reabrir navegador → novo login | APROVADO | 99 / 99 / 99 |
| P3 falha de leitura do IndexedDB | APROVADO | falha detectada, gravação suspensa, base intacta |
| P4 ida e volta entre empresas | APROVADO | chaves `db-canonico` e `db-canonico@YLG-TESTE-02` separadas |
| P5 exclusão legítima não ressuscita | APROVADO | endereço excluído não volta |
| P6 ponto de restauração e rollback | APROVADO | não-Master negado; 0 → 40 endereços restaurados |
| P7 versão mais recente prevalece | APROVADO | espelho rev maior vence |
| P8 falha de rede não apaga | APROVADO | contagens iguais offline e após sync |
| P9 usuário desativado encerra sessão após F5 | APROVADO | mensagem correta, dados preservados |
| M1/M2 duas abas | APROVADO (original: M2 FALHA) | registros, edições e exclusões das duas abas preservados |
| L1 base volumosa, F5 ×3 | APROVADO | 3.940 end./1.000 prod./1.000 mov.; base+sessão em 0,56–0,69 s |
| F01 login Master | APROVADO | perfil master |
| F02 cadastro de cliente (UI) | APROVADO | persiste após F5 |
| F03 cadastro de endereços (UI) | APROVADO | 3 endereços após F5 |
| F04 carga de estoque por template CSV (UI) | APROVADO | 3 linhas → 3 produtos idênticos após F5 |
| F05 movimentação + rastreabilidade | APROVADO | endereço novo + movimento após F5 |
| F06 validade preservada (base do FEFO) | APROVADO | ordenação por validade correta — *a regra de sugestão FEFO na separação não foi exercitada* |
| F07 inventário (criar e persistir) | APROVADO | INV-0001 com 6 tarefas após F5 |
| F08 navegação por 39 telas | APROVADO (original: erro em `home`) | 0 erros |
| F09 viewport 390 px | APROVADO | sem rolagem horizontal |
| F10 perfis | APROVADO | Líder gere, não exclui |
| Erros de página no roteiro completo | 0 (original: 6) | |
| SQL S00–S05 (réplica PGlite, 42 casos) | APROVADO | ver `supabase/migrations/README.md` |
| Supabase real a partir do navegador | **NÃO EXECUTADO** | sem acesso de rede do ambiente a `*.supabase.co` |
| Safari / Firefox / dispositivos reais | **NÃO EXECUTADO** | só Chromium disponível |
| Base real do usuário (navegador de produção) | **NÃO EXECUTADO** | os dados ficam no navegador da operação; validar após publicar (§6) |
| Importação XLSX, expedição, separação, devolução (execução) | **NÃO EXECUTADO** | telas abrem sem erro; fluxos não executados ponta a ponta |

## 4. Supabase — achados e migrações

Detalhes, matriz por política e ordem de execução: `supabase/migrations/README.md`.

- **Crítico (aberto):** a chave pública permite ler todos os `senha_hash` (`usuarios`, `usuarios_operacionais`), alterar empresas/licenças/módulos/Masters e vincular qualquer instalação a qualquer empresa (`registrar_instalacao_wms`).
- **Preparadas e testadas em réplica, NÃO executadas:** 00 (backup), 01 (fase 1 sem impacto no WMS), 02 (RPCs de sessão/usuários, aditiva). **Preparada e bloqueada:** 03 (remove acesso direto de `anon`) — depende de sprint de frontend no WMS e na Platform.
- **Snapshot `wms_recovery_snapshot_20261016`:** não restaurado. Comparação somente leitura: **nenhum ID em comum** com o registro atual (clientes `1785761655354` × `1790909404282/1790944655916/1790944686842`; 0 de 3.939 endereços coincidem), apesar de contagens parecidas. Preservado intacto, assim como `wms_kv_store_backup_tenant002b`.
- O WMS opera com persistência **local autoritativa** (`storageProvider` forçado para `local` desde a Build 016). O `wms_kv_store` não é a fonte dos dados operacionais; a correção mantém isso.

## 5. Procedimento de publicação

1. Revisar o diff na branch `fix/wms-persistencia-sessao-seguranca`.
2. Fazer merge na `main` (ou substituir `index.html` na `main` pelo da branch). Os demais arquivos (`docs/`, `supabase/`, `tests/`) não interferem no site.
3. Aguardar o GitHub Pages publicar e abrir o WMS com **Ctrl+Shift+R** (evita cache da versão anterior).
4. Conferir no rodapé/título: **v2.1.3 Build 023**.

## 6. Validação pós-publicação (no navegador da operação)

1. **Antes de publicar**, no WMS atual: exportar pela tela **Backup** e anotar contagens de clientes, produtos e endereços.
2. Abrir a 023 e o Console (F12). Deve aparecer `[WMS PERSISTENCE 023] base carregada · empresa: YLG-AFD2BC · origem: … · rev: … · registros: …`.
3. Conferir as mesmas contagens. Criar um cliente de teste, F5, confirmar; excluir o cliente de teste.
4. F5 e Ctrl+R logado: deve permanecer logado. Sair → F5: deve pedir login.
5. Se a contagem divergir: **não operar**; no console (Master) `await wmsRestaurarPontoDeRestauracao('inicio-sessao')` e avisar.

## 7. Rollback

- **Código:** `git revert` do merge (ou recolocar o `index.html` do commit `b9f88a0`). A 022 continua lendo `db-canonico`; o campo `_persistMeta` é ignorado por ela. Bases isoladas `db-canonico@<empresa>` ficam preservadas, mas a 022 volta a não enxergá-las (comportamento antigo).
- **Dados:** `wmsRestaurarPontoDeRestauracao('anterior' | 'inicio-sessao')` (Master, console). O estado substituído fica em `<chave>:antes-restauracao`.
- **Banco:** cada migração tem `.rollback.sql`; nenhuma foi aplicada.

## 8. Estado final

**APTO COM RESSALVAS** — para publicação do `index.html`:

- critérios críticos comprovados em Chromium: perda de dados (D1–D3, D5) e sessão (D4) reproduzidas no original e corrigidas, regressão funcional sem falhas, base de build anterior migrada sem perda;
- ressalvas a aceitar: Supabase simulado nos testes de navegador; só Chromium; validação com a base real feita após publicar (§6); fluxos de expedição/separação/XLSX não executados ponta a ponta;
- **fora do arquivo publicado e ainda aberto:** exposição crítica do Supabase (§4). Esta publicação não piora nem resolve; exige aplicar as migrações 00–02 e a sprint de frontend antes da 03.
