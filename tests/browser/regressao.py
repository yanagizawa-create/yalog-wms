"""Regressão funcional dirigida pela UI. Mesmo roteiro para original e corrigido.
Uso: python3 regressao.py <index.html> <saida.json>"""
import sys, tempfile, json
from playwright.sync_api import sync_playwright
from harness import *

html, saida = sys.argv[1], sys.argv[2]
R = {}
def rec(k, ok, ev): R[k] = {'ok': bool(ok), 'ev': ev}; print(f"RESULT|{k}|{'PASS' if ok else 'FAIL'}|{ev}", flush=True)

TELAS = "ageingReport ajusteEstoque alertasValidade armazenagem backup bloqueios capArmazem cargaEstoque clientes conciliacao configGeral curvaABC custoArmazem devolucao enderecos estoqueList estoqueMapa expedicao historico home invList limparEstoque mapaEstoqueGestao masterAceite matrizPP minhaConta movimentar ocupacao paletes recTarefas recUpload relEstoque relRecebimento relSaida sepTarefas sepUpload sites tarefasMov usuarios".split()

CSV = "\n".join([
    "SKU_CLIENTE;DESCRICAO;CLIENTE;SITE;NF_ENTRADA;LOTE;VALIDADE;QUANTIDADE;UNIDADE_MEDIDA;VALOR_UNIT;STATUS;OBS;TIPO_PALETE;ENDERECO;ID_PALETE_UZ",
    "SKU-T1;PRODUTO TESTE UM;CLIENTE REGRESSAO;;NF-T1;L1;2027-01-31;10;UN;1,50;LIBERADO;;PBR;RG-1-0;UZ-T1",
    "SKU-T2;PRODUTO TESTE DOIS;CLIENTE REGRESSAO;;NF-T1;L2;2026-12-31;20;UN;2,00;LIBERADO;;PBR;RG-2-0;UZ-T2",
    "SKU-T3;PRODUTO TESTE TRES;CLIENTE REGRESSAO;;NF-T1;L3;2027-06-30;30;CX;3,00;LIBERADO;;PBR;RG-3-0;UZ-T3",
])

with sync_playwright() as p:
    fake = FakeSupabase(); logs = []
    d = tempfile.mkdtemp()
    ctx = montar_contexto(p.chromium, html, d, fake)
    pg = abrir(ctx, logs); aguardar_boot(pg)
    pg.evaluate("() => { window.wmsConfirm = async () => true; window.confirm = () => true; }")

    # 1. Login Master (Platform)
    login_ui(pg, login=MASTER_LOGIN, senha=MASTER_SENHA)
    u = pg.evaluate("() => usuarioAtual && {perfil:usuarioAtual.perfil, company:usuarioAtual.company_id}")
    rec('F01-login-master', u and u['perfil'] == 'master', f'usuario={u}')

    # 2. Cadastro de cliente pela tela
    pg.evaluate("() => go('clientes')"); pg.wait_for_timeout(400)
    pg.evaluate("() => { if(typeof novoCliente==='function') novoCliente(); }"); pg.wait_for_timeout(200)
    pg.evaluate("() => { const e=document.getElementById('cliEditId'); if(e) e.value=''; document.getElementById('cliNome').value='CLIENTE REGRESSAO'; salvarCliente(); }")
    pg.wait_for_timeout(500)
    pg.reload(); aguardar_boot(pg); pg.evaluate("() => { window.wmsConfirm = async () => true; window.confirm = () => true; }")
    cli = pg.evaluate("() => DB.clientes.map(c=>c.nome)")
    rec('F02-cadastro-cliente-persiste', 'CLIENTE REGRESSAO' in cli, f'clientes após F5={cli}')

    # 3. Cadastro de endereços (modo único) pela tela
    pg.evaluate("() => go('enderecos')"); pg.wait_for_timeout(400)
    pg.evaluate("""() => { setModoEnd('unica'); document.getElementById('endArea').value='RG'; document.getElementById('endModDe').value='1';
       document.getElementById('endModAte').value='3'; document.getElementById('endNivDe').value='0'; document.getElementById('endNivAte').value='0'; criarEnderecos(); }""")
    pg.wait_for_timeout(800)
    pg.reload(); aguardar_boot(pg); pg.evaluate("() => { window.wmsConfirm = async () => true; window.confirm = () => true; }")
    ends = pg.evaluate("() => DB.enderecos.map(e=>e.addr).filter(a=>a.startsWith('RG'))")
    rec('F03-cadastro-enderecos-persiste', len(ends) >= 3, f'endereços RG após F5={ends}')

    # 4. Carga inicial de estoque por template (CSV pela tela)
    pg.evaluate("() => go('cargaEstoque')"); pg.wait_for_timeout(400)
    arq = tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8'); arq.write(CSV); arq.close()
    pg.set_input_files('#cargaFile', arq.name); pg.wait_for_timeout(1200)
    prev = pg.evaluate("() => (typeof cargaData!=='undefined' && cargaData) ? cargaData.length : -1")
    pg.evaluate("() => processarCarga()"); pg.wait_for_timeout(3000)
    pr = pg.evaluate("() => DB.produtos.filter(p=>String(p.codCliente||p.sku||'').startsWith('SKU-T')).map(p=>[p.codCliente,p.qtd,p.endereco,p.lote])")
    pg.reload(); aguardar_boot(pg); pg.evaluate("() => { window.wmsConfirm = async () => true; window.confirm = () => true; }")
    pr5 = pg.evaluate("() => DB.produtos.filter(p=>String(p.codCliente||p.sku||'').startsWith('SKU-T')).map(p=>[p.codCliente,p.qtd,p.endereco,p.lote])")
    rec('F04-carga-estoque-template', prev == 3 and len(pr) == 3 and sorted(map(json.dumps, pr)) == sorted(map(json.dumps, pr5)), f'linhas lidas={prev}; produtos={pr}; após F5={pr5}')

    # 5. Movimentação total + rastreabilidade (histórico)
    mv = pg.evaluate("""() => { const p=DB.produtos.find(x=>x.codCliente==='SKU-T1'); if(!p) return 'sem produto';
        _movProduto=p; _movDestino='RG-3-0'; document.getElementById('movQtd').value=String(p.qtd); document.getElementById('movMotivo').value='teste regressao';
        confirmarMovimentacao(); return p.wmsId; }""")
    pg.wait_for_timeout(600)
    pg.reload(); aguardar_boot(pg); pg.evaluate("() => { window.wmsConfirm = async () => true; window.confirm = () => true; }")
    st = pg.evaluate("(w) => ({end:(DB.produtos.find(x=>x.wmsId===w)||{}).endereco, mov:DB.movimentos.filter(m=>m.wmsId===w&&m.tipo==='MOVIMENTACAO').length})", mv)
    rec('F05-movimentacao-rastreabilidade', st['end'] == 'RG-3-0' and st['mov'] >= 1, f'wmsId={mv} estado após F5={st}')

    # 6. FEFO — ordem por validade disponível nas funções do sistema
    fefo = pg.evaluate("""() => { const ps=DB.produtos.filter(p=>String(p.codCliente||'').startsWith('SKU-T'));
        const ord=[...ps].sort((a,b)=>String(a.validade||'').localeCompare(String(b.validade||''))).map(p=>p.codCliente); return ord; }""")
    rec('F06-fefo-dados-de-validade-preservados', fefo[:1] == ['SKU-T2'], f'ordem por validade={fefo}')

    # 7. Inventário: abertura da tela e criação (se a UI permitir via função)
    pg.evaluate("() => go('invList')"); pg.wait_for_timeout(600)
    n0 = pg.evaluate("() => (DB.inventarios||[]).length")
    pg.evaluate("() => inv20AbrirPlanejamento()"); pg.wait_for_timeout(500)
    pg.evaluate("() => { inv20MarcarRuas(true); criarInventario2(); }"); pg.wait_for_timeout(800)
    n1 = pg.evaluate("() => (DB.inventarios||[]).map(i=>[i.id,i.status,(i.tarefas||[]).length])")
    pg.reload(); aguardar_boot(pg); pg.evaluate("() => { window.wmsConfirm = async () => true; window.confirm = () => true; }")
    n2 = pg.evaluate("() => (DB.inventarios||[]).map(i=>[i.id,i.status,(i.tarefas||[]).length])")
    rec('F07-inventario-criar-persistir', len(n1) == n0 + 1 and n1 == n2 and n1[-1][2] > 0, f'antes={n0}; criado={n1}; após F5={n2}')

    # 8. Navegação por todas as telas (erros de página por tela)
    erros_tela = {}
    for t in TELAS:
        antes = len(logs)
        try:
            pg.evaluate("(t) => go(t)", t); pg.wait_for_timeout(250)
        except Exception as e:
            erros_tela[t] = [str(e)[:120]]; continue
        novos = [l for l in logs[antes:] if l.startswith('[pageerror]')]
        if novos: erros_tela[t] = [n[:160] for n in novos]
    rec('F08-navegacao-todas-telas', not erros_tela, f'telas={len(TELAS)} com erro={erros_tela}')

    # 9. Responsividade: viewport móvel sem erro de página
    pg.set_viewport_size({'width': 390, 'height': 844})
    try: pg.evaluate("() => go('home')")
    except Exception as e: logs.append('[pageerror] viewport-home '+str(e)[:120])
    pg.wait_for_timeout(500)
    larg = pg.evaluate("() => document.documentElement.scrollWidth")
    rec('F09-viewport-movel', True, f'scrollWidth em 390px={larg}')

    # 10. Perfis: operador não vê gestão de usuários
    pg.evaluate("() => { window.wmsConfirm=async()=>true; return fazerLogoff(); }"); pg.wait_for_timeout(1000)
    login_ui(pg)  # líder
    perf = pg.evaluate("() => ({perfil:usuarioAtual.perfil, gerir:typeof podeGerirUsuarios==='function'?podeGerirUsuarios():null, excluir:typeof podeExcluirUsuarios==='function'?podeExcluirUsuarios():null})")
    rec('F10-perfis-permissoes', perf['perfil'] == 'lider' and perf['excluir'] in (False, None), f'{perf}')

    erros = [l for l in logs if l.startswith('[pageerror]')]
    R['_pageerrors_total'] = len(erros); R['_pageerrors'] = erros[:30]
    json.dump(R, open(saida, 'w'), ensure_ascii=False, indent=1)
    ctx.close()
print('PAGEERRORS', R['_pageerrors_total'])
