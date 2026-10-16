"""Base grande (~volume real: 3.9k endereços, 1k produtos, 1k movimentos) — boot, F5, navegação."""
import sys, tempfile, time
from playwright.sync_api import sync_playwright
from harness import *
html = sys.argv[1]
with sync_playwright() as p:
    fake = FakeSupabase(); logs = []
    ctx = montar_contexto(p.chromium, html, tempfile.mkdtemp(), fake)
    pg = abrir(ctx, logs); aguardar_boot(pg); login_ui(pg)
    pg.evaluate("""() => { DB.clientes.push({id:'CLI-G',nome:'CLIENTE GRANDE TESTE',sites:[]});
      for(let i=0;i<3940;i++) DB.enderecos.push({id:'EG'+i,area:'G-'+(i%40),modulo:i,nivel:i%5,addr:'G-'+(i%40)+'-'+i+'-'+(i%5),status:'livre'});
      for(let i=0;i<1000;i++){ DB.produtos.push({wmsId:'WMS-G'+i,clienteId:'CLI-G',descricao:'PRODUTO GRANDE TESTE '+i,qtd:i+1,um:'UN',status:'LIBERADO',endereco:'G-'+(i%40)+'-'+i+'-'+(i%5),paleteId:'PAL-G'+i,lote:'L'+i,validade:'2027-01-01'});
        DB.movimentos.push({id:'MV'+i,data:new Date().toISOString(),tipo:'ENTRADA',wmsId:'WMS-G'+i,qtd:i+1,ref:'carga teste',resp:'teste'}); }
      save(); }""")
    pg.wait_for_timeout(2500)
    tam = pg.evaluate("() => JSON.stringify(DB).length")
    antes = contagens(pg)
    tempos = []
    ok = True
    for n in range(3):
        pg.evaluate("(n) => { DB.produtos[n].qtd = 1000+n; save(); }", n)
        t = time.time(); pg.reload()
        pg.wait_for_function("() => typeof _wmsHidratado!=='undefined' && _wmsHidratado && typeof usuarioAtual!=='undefined' && !!usuarioAtual", timeout=30000)
        tempos.append(round(time.time() - t, 2))
        c = contagens(pg); q = pg.evaluate("(n) => DB.produtos.find(p=>p.wmsId==='WMS-G'+n).qtd", n)
        ok = ok and c['produtos'] == antes['produtos'] and c['enderecos'] == antes['enderecos'] and c['movimentos'] == antes['movimentos'] and q == 1000 + n
    pg.evaluate("() => go('estoqueList')"); pg.wait_for_timeout(500); pg.evaluate("() => go('enderecos')"); pg.wait_for_timeout(500)
    pg.reload(); pg.wait_for_function("() => typeof _wmsHidratado!=='undefined' && _wmsHidratado && !!usuarioAtual", timeout=30000)
    lg = logado(pg)
    erros = [l for l in logs if l.startswith('[pageerror]')]
    print(f"RESULT|L1-base-grande-F5-repetido|{'PASS' if ok and lg and not erros else 'FAIL'}|tamanho JSON={tam/1e6:.2f} MB; contagens={ {k:antes[k] for k in ('produtos','enderecos','movimentos')} }; tempo até base+sessão por F5={tempos}s; logado após navegação+F5={lg}; erros de página={len(erros)}")
    ctx.close()
