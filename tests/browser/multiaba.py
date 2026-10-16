"""Duas abas abertas na mesma base: a gravação de uma aba desatualizada não
pode apagar nem reverter o que a outra aba gravou. Uso: python3 multiaba.py <index.html>"""
import sys, tempfile
from playwright.sync_api import sync_playwright
from harness import *
html = sys.argv[1]
with sync_playwright() as p:
    fake = FakeSupabase(); logs = []
    ctx = montar_contexto(p.chromium, html, tempfile.mkdtemp(), fake)
    a = abrir(ctx, logs); aguardar_boot(a); login_ui(a)
    a.evaluate("""() => { DB.clientes.push({id:'CLI-BASE',nome:'BASE',sites:[]});
      DB.produtos.push({wmsId:'WMS-P1',clienteId:'CLI-BASE',descricao:'P1',qtd:10,um:'UN',status:'LIBERADO',endereco:'A-1',paleteId:'X1'});
      DB.produtos.push({wmsId:'WMS-P2',clienteId:'CLI-BASE',descricao:'P2',qtd:20,um:'UN',status:'LIBERADO',endereco:'A-2',paleteId:'X2'});
      DB.enderecos.push({id:'E-DEL',addr:'Z-9',area:'Z',status:'livre'}); save(); }""")
    a.wait_for_timeout(600)
    b = ctx.new_page(); b.goto(ORIGIN); aguardar_boot(b); b.wait_for_timeout(1500)
    # Aba A: cria cliente, altera P1 e exclui um endereço
    a.evaluate("""() => { DB.clientes.push({id:'CLI-ABA-A',nome:'ABA A',sites:[]}); DB.produtos.find(p=>p.wmsId==='WMS-P1').qtd=3;
      DB.enderecos=DB.enderecos.filter(e=>e.id!=='E-DEL'); save(); }"""); a.wait_for_timeout(800)
    # Aba B (desatualizada): cria cliente e altera P2
    b.evaluate("() => { DB.clientes.push({id:'CLI-ABA-B',nome:'ABA B',sites:[]}); DB.produtos.find(p=>p.wmsId==='WMS-P2').qtd=7; save(); }")
    b.wait_for_timeout(2000)
    mem_b = b.evaluate("() => ({cli:DB.clientes.map(c=>c.id).sort(), p1:DB.produtos.find(p=>p.wmsId==='WMS-P1').qtd})")
    b.close()
    a.reload(); aguardar_boot(a); a.wait_for_timeout(1000)
    st = a.evaluate("""() => ({cli:DB.clientes.map(c=>c.id).sort(), p1:DB.produtos.find(p=>p.wmsId==='WMS-P1').qtd,
       p2:DB.produtos.find(p=>p.wmsId==='WMS-P2').qtd, endDel:DB.enderecos.some(e=>e.id==='E-DEL')})""")
    ok1 = st['cli'] == ['CLI-ABA-A', 'CLI-ABA-B', 'CLI-BASE']
    ok2 = st['p1'] == 3 and st['p2'] == 7 and st['endDel'] is False
    print(f"RESULT|M1-duas-abas-novos-registros-preservados|{'PASS' if ok1 else 'FAIL'}|clientes após F5={st['cli']}")
    print(f"RESULT|M2-duas-abas-edicoes-e-exclusoes-preservadas|{'PASS' if ok2 else 'FAIL'}|P1 (editado na aba A)={st['p1']} P2 (editado na aba B)={st['p2']} endereço excluído na aba A voltou={st['endDel']}; memória da aba B após incorporar={mem_b}")
    ctx.close()
