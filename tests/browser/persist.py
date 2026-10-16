"""Testes de persistência, migração, isolamento, falha e rollback.
Uso: python3 persist.py <index_corrigido.html> <index_original.html> [cenario...]"""
import sys, tempfile, json
from playwright.sync_api import sync_playwright
from harness import *

novo_html, orig_html = sys.argv[1], sys.argv[2]
so = set(sys.argv[3:])
res_list = []
def res(cid, ok, ev):
    res_list.append((cid, ok)); print(f"RESULT|{cid}|{'PASS' if ok else 'FAIL'}|{ev}", flush=True)
def run(n): return not so or n in so

SEED = """(pref) => { DB.clientes.push({id:'CLI-'+pref, nome:'CLIENTE TESTE '+pref, sites:[]});
  for(let i=0;i<5;i++){ DB.enderecos.push({id:'END-'+pref+i, area:'A-01', modulo:i, nivel:0, addr:'A-01-'+pref+'-'+i, status:'livre'});
    DB.produtos.push({wmsId:'WMS-'+pref+i, clienteId:'CLI-'+pref, descricao:'PROD TESTE '+i, qtd:10+i, um:'UN', status:'LIBERADO', endereco:'A-01-'+pref+'-'+i, paleteId:'PAL-'+pref+i}); }
  save(); }"""

def ctx_para(p, html, d, fake, init=None):
    c = montar_contexto(p.chromium, html, d, fake, init); pg = abrir(c); aguardar_boot(pg); return c, pg

with sync_playwright() as p:
    if run('P1'):  # Atualização de build: base antiga (sem versão) preservada
        d = tempfile.mkdtemp(); fake = FakeSupabase()
        c, pg = ctx_para(p, orig_html, d, fake); login_ui(pg); pg.evaluate(SEED, 'A'); pg.wait_for_timeout(800)
        antes = contagens(pg); c.close()
        c, pg = ctx_para(p, novo_html, d, fake); pg.wait_for_timeout(2000)
        depois = contagens(pg); lg = logado(pg)
        meta = pg.evaluate("() => DB._persistMeta"); q = pg.evaluate("() => DB.produtos.find(x=>x.wmsId==='WMS-A3').qtd")
        pg.reload(); aguardar_boot(pg); pg.wait_for_timeout(1500); depois2 = contagens(pg)
        ok = lg and all(depois[k] == antes[k] for k in ('clientes','produtos','enderecos')) and q == 13 and depois2 == depois and meta and meta.get('companyId') == CID
        res('P1-upgrade-build-preserva-base', ok, f"antes={ {k:antes[k] for k in ('clientes','produtos','enderecos')} } depois={ {k:depois[k] for k in ('clientes','produtos','enderecos')} } logado={lg} qtd={q} meta={meta}")
        c.close()

    if run('P2'):  # Criar, F5, fechar navegador, novo login
        d = tempfile.mkdtemp(); fake = FakeSupabase()
        c, pg = ctx_para(p, novo_html, d, fake); login_ui(pg); pg.evaluate(SEED, 'B'); pg.wait_for_timeout(600)
        pg.evaluate("() => { DB.produtos.find(x=>x.wmsId==='WMS-B0').qtd=99; save(); }"); pg.wait_for_timeout(400)
        pg.reload(); aguardar_boot(pg); a = pg.evaluate("() => DB.produtos.find(x=>x.wmsId==='WMS-B0')?.qtd")
        c.close()
        c, pg = ctx_para(p, novo_html, d, fake); b = pg.evaluate("() => DB.produtos.find(x=>x.wmsId==='WMS-B0')?.qtd"); lg = logado(pg)
        pg.evaluate("() => { window.wmsConfirm=async()=>true; return fazerLogoff(); }"); pg.wait_for_timeout(1000)
        login_ui(pg); cc = pg.evaluate("() => DB.produtos.find(x=>x.wmsId==='WMS-B0')?.qtd")
        res('P2-salvar-recarregar-reabrir-relogar', a == 99 and b == 99 and cc == 99 and lg, f'F5={a} reabrir navegador={b} (logado={lg}) novo login={cc}')
        c.close()

    if run('P3'):  # Falha de leitura do IndexedDB não sobrescreve a base
        d = tempfile.mkdtemp(); fake = FakeSupabase()
        c, pg = ctx_para(p, novo_html, d, fake); login_ui(pg); pg.evaluate(SEED, 'C'); pg.wait_for_timeout(800); antes = contagens(pg)
        pg.evaluate("() => { localStorage.removeItem('wms_3cs_v2026'); }")
        c.close()
        falha = """(() => { const o=IDBObjectStore.prototype.get; IDBObjectStore.prototype.get=function(k){ if(k==='db-canonico'){ const r=o.call(this,'__inexistente__'); Object.defineProperty(r,'error',{get:()=>new DOMException('simulado','UnknownError')}); r.addEventListener('success',e=>{e.stopImmediatePropagation(); r.dispatchEvent(new Event('error'));},{capture:true}); return r;} return o.call(this,k); }; })()"""
        c, pg = ctx_para(p, novo_html, d, fake, falha); pg.wait_for_timeout(2500)
        falhou = pg.evaluate("() => _wmsIdbLeituraFalhou")
        pg.evaluate("() => { DB.clientes.push({id:'CLI-DURANTE-FALHA',nome:'X',sites:[]}); save(); }"); pg.wait_for_timeout(800)
        c.close()
        c, pg = ctx_para(p, novo_html, d, fake); pg.wait_for_timeout(1500); depois = contagens(pg)
        res('P3-falha-leitura-idb-nao-sobrescreve', falhou and depois['produtos'] == antes['produtos'] and depois['enderecos'] == antes['enderecos'],
            f"leitura falhou detectada={falhou}; antes produtos={antes['produtos']} end={antes['enderecos']}; depois produtos={depois['produtos']} end={depois['enderecos']}")
        c.close()

    if run('P4'):  # Ida e volta entre empresas no mesmo navegador
        d = tempfile.mkdtemp(); fake = FakeSupabase()
        c, pg = ctx_para(p, novo_html, d, fake)
        sair = "() => { window.wmsConfirm=async()=>true; return fazerLogoff(); }"
        login_ui(pg, cid=CID); pg.evaluate(SEED, 'EMP1'); pg.wait_for_timeout(600); pg.evaluate(sair); pg.wait_for_timeout(1000)
        login_ui(pg, cid=CID_OUTRA); v2 = pg.evaluate("() => DB.clientes.map(c=>c.id)"); pg.evaluate(SEED, 'EMP2'); pg.wait_for_timeout(600)
        pg.reload(); aguardar_boot(pg); v2f5 = pg.evaluate("() => DB.clientes.map(c=>c.id)")
        pg.evaluate(sair); pg.wait_for_timeout(1000)
        login_ui(pg, cid=CID); v1 = pg.evaluate("() => DB.clientes.map(c=>c.id)"); n1 = pg.evaluate("() => DB.produtos.length")
        pg.reload(); aguardar_boot(pg); v1f5 = pg.evaluate("() => DB.clientes.map(c=>c.id)")
        keys = pg.evaluate("""() => new Promise(r=>{const q=indexedDB.open('YALOG_WMS_LOCAL_DB');q.onsuccess=()=>{const t=q.result.transaction('estado').objectStore('estado').getAllKeys();t.onsuccess=()=>r(t.result);};})""")
        ok = v2 == [] and v2f5 == ['CLI-EMP2'] and v1 == ['CLI-EMP1'] and v1f5 == ['CLI-EMP1'] and n1 == 5
        res('P4-ida-e-volta-entre-empresas', ok, f'emp02 inicial={v2} emp02 F5={v2f5} emp01 volta={v1} prod={n1} emp01 F5={v1f5} chaves IDB={keys}')
        c.close()

    if run('P5'):  # Exclusões legítimas não ressuscitam (com snapshot legado presente)
        d = tempfile.mkdtemp(); fake = FakeSupabase()
        c, pg = ctx_para(p, novo_html, d, fake); login_ui(pg); pg.evaluate(SEED, 'D'); pg.wait_for_timeout(600)
        pg.evaluate("() => localStorage.setItem('wms_db_guard_snapshot_v2:YLG-TESTE-01', JSON.stringify({version:2,db:JSON.parse(JSON.stringify(DB))}))")
        pg.evaluate("() => { DB.enderecos=DB.enderecos.filter(e=>e.id!=='END-D4'); save(); }"); pg.wait_for_timeout(500)
        pg.reload(); aguardar_boot(pg)
        tem = pg.evaluate("() => DB.enderecos.some(e=>e.id==='END-D4')")
        res('P5-exclusao-legitima-nao-ressuscita', not tem, f'endereço excluído reapareceu após F5={tem}')
        c.close()

    if run('P6'):  # Redução grande preserva versão anterior + rollback
        d = tempfile.mkdtemp(); fake = FakeSupabase()
        c, pg = ctx_para(p, novo_html, d, fake); login_ui(pg)
        pg.evaluate("""() => { for(let i=0;i<40;i++) DB.enderecos.push({id:'EG'+i,area:'B-01',modulo:i,nivel:0,addr:'B-01-'+i,status:'livre'}); save(); }"""); pg.wait_for_timeout(500)
        pg.evaluate("() => { DB.enderecos=[]; save(); }"); pg.wait_for_timeout(800)
        k = idb_canonico(pg)
        tem_anterior = 'db-canonico:anterior' in k and len(k.get('db-canonico',{}).get('clientes',[])) == 0
        # Rollback: procedimento documentado (console, perfil Master)
        negado = pg.evaluate("() => wmsRestaurarPontoDeRestauracao('anterior')")  # usuário de teste é Líder
        pg.evaluate("() => { usuarioAtual.perfil='master'; }")
        okr = pg.evaluate("() => wmsRestaurarPontoDeRestauracao('anterior')")
        pg.reload(); aguardar_boot(pg); n = pg.evaluate("() => DB.enderecos.length")
        res('P6-ponto-de-restauracao-e-rollback', 'db-canonico:anterior' in k and negado is False and okr and n == 40,
            f'chaves={list(k.keys())}; não-Master negado={negado is False}; rollback={okr}; endereços após rollback+F5={n}')
        c.close()

    if run('P7'):  # Compatibilidade de versões: espelho mais novo vence; sem versão = aditivo
        d = tempfile.mkdtemp(); fake = FakeSupabase()
        c, pg = ctx_para(p, novo_html, d, fake); login_ui(pg); pg.evaluate(SEED, 'E'); pg.wait_for_timeout(800)
        # espelho com rev maior (IndexedDB não concluiu a última gravação)
        pg.evaluate("() => { const m=JSON.parse(localStorage.getItem('wms_3cs_v2026')); m.produtos[0].qtd=555; m._persistMeta.rev+=5; localStorage.setItem('wms_3cs_v2026', JSON.stringify(m)); }")
        pg.reload(); aguardar_boot(pg); q = pg.evaluate("() => DB.produtos.find(x=>x.wmsId==='WMS-E0').qtd")
        res('P7-versao-mais-recente-prevalece', q == 555, f'qtd após F5 (espelho rev maior tinha 555)={q}')
        c.close()

    if run('P8'):  # Rede indisponível / resposta vazia não apaga dados
        d = tempfile.mkdtemp(); fake = FakeSupabase()
        c, pg = ctx_para(p, novo_html, d, fake); login_ui(pg); pg.evaluate(SEED, 'F'); pg.wait_for_timeout(600); antes = contagens(pg)
        fake.modo = 'offline'; pg.reload(); aguardar_boot(pg); pg.wait_for_timeout(2000); a = contagens(pg)
        fake.modo = 'ok'; fake.op_users[0]['ativo'] = True
        pg.evaluate("() => sincronizarUsuariosOperacionaisDaEmpresa('YLG-TESTE-01', true, true)"); pg.wait_for_timeout(1000); b = contagens(pg)
        ok = all(a[k] == antes[k] == b[k] for k in ('clientes','produtos','enderecos'))
        res('P8-falha-de-rede-nao-apaga', ok, f"antes={antes['produtos']}/{antes['clientes']} offline={a['produtos']}/{a['clientes']} pós-sync={b['produtos']}/{b['clientes']}")
        c.close()

    if run('P9'):  # Invalidação real após F5: usuário desativado / licença bloqueada
        d = tempfile.mkdtemp(); fake = FakeSupabase()
        c, pg = ctx_para(p, novo_html, d, fake); login_ui(pg); pg.evaluate(SEED, 'G'); pg.wait_for_timeout(500)
        fake.op_users[0]['ativo'] = False
        pg.reload(); aguardar_boot(pg); pg.wait_for_timeout(3000)
        a = logado(pg); msg = pg.evaluate("() => document.getElementById('loginErro').textContent"); dados = pg.evaluate("() => DB.produtos.length")
        res('P9-usuario-desativado-encerra-sessao', (not a) and 'desativado' in msg.lower() and dados == 5, f'logado={a} msg="{msg}" produtos preservados={dados}')
        c.close()

ok = sum(1 for r in res_list if r[1]); print(f'TOTAL {ok}/{len(res_list)} PASS')
