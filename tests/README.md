# Testes — YALog WMS

Todos os testes usam **dados identificados como TESTE** (empresas `YLG-TESTE-01/02`) e ambientes isolados. Nenhum teste acessa dados de produção.

## Navegador (`tests/browser/`)

Chromium headless (Playwright). O `index.html` é servido numa origem isolada (`https://wms.test/`); as bibliotecas de CDN são servidas de cópias locais e o **Supabase é simulado por rota** (respostas de empresa/licença/módulo/usuários de teste, modo offline e lento).

Preparar (uma vez):

```bash
pip install playwright && python3 -m playwright install chromium
mkdir -p tests/browser/vendor && cd tests/browser/vendor
npm pack @supabase/supabase-js@2 chart.js@4.4.1 lucide@1.58.0 xlsx@0.18.5 qrcodejs jsbarcode@3.11.6
for f in *.tgz; do d=${f%.tgz}; mkdir -p $d && tar xzf $f -C $d; done
# ajuste os nomes das pastas em harness.py (CDN) se as versões baixadas forem outras
```

Executar (de `tests/browser/`):

| Script | O que cobre |
|---|---|
| `python3 validar_sintaxe.py ../../index.html` | Sintaxe de todos os `<script>` e handlers inline |
| `python3 repro.py ../../index.html` | Reprodução dos defeitos: cofre/snapshot antigo revertendo edição, isolamento entre empresas, save/F5 durante o carregamento, sessão revogada, F5 offline, falha transitória no SSO, logout |
| `python3 persist.py ../../index.html <index_original.html>` | Atualização de build, reabrir navegador, falha de leitura do IndexedDB, ida e volta entre empresas, exclusão legítima, ponto de restauração/rollback, versão mais recente, rede indisponível, usuário desativado |
| `python3 regressao.py ../../index.html saida.json` | Fluxos pela UI: login Master, cliente, endereços, carga de estoque por template, movimentação/rastreabilidade, validade (FEFO), inventário, navegação por 39 telas, viewport móvel, perfis |
| `python3 grande.py ../../index.html` | Base com volume real (3,9 mil endereços, 1 mil produtos, 1 mil movimentos) com F5 repetido |
| `python3 multiaba.py ../../index.html` | Duas abas na mesma base: registros, edições e exclusões preservados |

Cada linha `RESULT|id|PASS/FAIL|evidência` é o resultado de um teste.

## Banco (`tests/sql/`)

`node testar_migracoes.js` (com `@electric-sql/pglite` instalado) cria uma réplica isolada com as políticas/funções de produção (`replica_producao.sql`) e testa as migrações de `supabase/migrations/` e seus rollbacks.
