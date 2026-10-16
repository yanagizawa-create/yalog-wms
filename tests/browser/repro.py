"""Cenários que reproduzem os defeitos. Uso: python3 repro.py <index.html> [cenario...]
Cada cenário roda em perfil de navegador novo e isolado, com dados identificados como TESTE.
Saída: linhas 'RESULT|<id>|PASS/FAIL|evidência'."""
import sys, tempfile, json
from playwright.sync_api import sync_playwright
from harness import *

html = sys.argv[1]
so = set(sys.argv[2:])
resultados = []


def res(cid, ok, ev):
    resultados.append((cid, ok, ev))
    print(f"RESULT|{cid}|{'PASS' if ok else 'FAIL'}|{ev}", flush=True)


def novo(p, fake=None, init=None):
    fake = fake or FakeSupabase()
    logs = []
    ctx = montar_contexto(p.chromium, html, tempfile.mkdtemp(), fake, init)
    page = abrir(ctx, logs)
    aguardar_boot(page)
    return ctx, page, fake, logs


SEED_JS = """(n) => {
  DB.clientes.push({id:'CLI-T1', nome:'CLIENTE TESTE 1', sites:[]});
  for(let i=0;i<n;i++){
    DB.enderecos.push({id:'END-T'+i, area:'A-01', modulo:i, nivel:0, addr:'A-01-'+i+'-0', status:'livre'});
    DB.produtos.push({wmsId:'WMS-T'+i, clienteId:'CLI-T1', descricao:'PRODUTO TESTE '+i, qtd:10, um:'UN', status:'LIBERADO', endereco:'A-01-'+i+'-0', paleteId:'PAL-T'+i});
  }
  save();
}"""


def run(nome):
    return not so or nome in so


with sync_playwright() as p:
    # R1 — snapshot/cofre antigo sobrescreve edição recente
    if run('R1'):
        ctx, page, fake, logs = novo(p)
        login_ui(page)
        page.evaluate(SEED_JS, 3)
        page.wait_for_timeout(500)
        # cofre gravado por build anterior (015-017) com o estado de então
        page.evaluate("() => localStorage.setItem('wms_data_vault_v1', JSON.stringify({version:1,data:new Date().toISOString(),db:JSON.parse(JSON.stringify(DB))}))")
        page.evaluate("() => { DB.produtos.find(p=>p.wmsId==='WMS-T0').qtd = 4; save(); }")
        q_mem = page.evaluate("() => DB.produtos.find(p=>p.wmsId==='WMS-T0').qtd")
        page.wait_for_timeout(600)
        page.reload(); aguardar_boot(page)
        q_f5 = page.evaluate("() => DB.produtos.find(p=>p.wmsId==='WMS-T0').qtd")
        res('R1-cofre-antigo-reverte-edicao', q_mem == 4 and q_f5 == 4, f'qtd editada=4; após save()={q_mem}; após F5={q_f5}')
        ctx.close()

    if run('R1b'):
        ctx, page, fake, logs = novo(p)
        login_ui(page)
        page.evaluate(SEED_JS, 3)
        page.wait_for_timeout(500)
        page.evaluate("() => localStorage.setItem('wms_db_guard_snapshot_v2:YLG-TESTE-01', JSON.stringify({version:2,data:new Date().toISOString(),motivo:'build-antigo',db:JSON.parse(JSON.stringify(DB))}))")
        page.evaluate("() => { DB.produtos.find(p=>p.wmsId==='WMS-T1').qtd = 7; save(); }")
        page.wait_for_timeout(600)
        page.reload(); aguardar_boot(page)
        q = page.evaluate("() => DB.produtos.find(p=>p.wmsId==='WMS-T1').qtd")
        res('R1b-snapshot-guard-antigo-reverte-edicao', q == 7, f'qtd editada=7; após F5={q}')
        ctx.close()

    # R3 — isolamento entre empresas na mesma instalação/navegador
    if run('R3'):
        ctx, page, fake, logs = novo(p)
        login_ui(page, cid=CID_OUTRA)
        page.evaluate("() => { DB.clientes.push({id:'CLI-DA-EMPRESA-02', nome:'CLIENTE EMPRESA 02', sites:[]}); save(); }")
        page.wait_for_timeout(600)
        # logout explícito
        page.evaluate("() => { window.wmsConfirm = async () => true; }")
        page.evaluate("() => fazerLogoff()")
        page.wait_for_timeout(1500)
        login_ui(page, cid=CID)
        ids = page.evaluate("() => DB.clientes.map(c=>c.id)")
        page.reload(); aguardar_boot(page)
        ids_f5 = page.evaluate("() => DB.clientes.map(c=>c.id)")
        res('R3-isolamento-empresas', 'CLI-DA-EMPRESA-02' not in ids and 'CLI-DA-EMPRESA-02' not in ids_f5,
            f'empresa 01 enxerga clientes={ids}; após F5={ids_f5}')
        ctx.close()

    if run('R3b'):
        ctx, page, fake, logs = novo(p)
        page.evaluate("() => localStorage.setItem('wms:YLG-TESTE-02:wms_3cs_v2026', JSON.stringify({clientes:[{id:'CLI-CACHE-EMP02',nome:'CACHE EMPRESA 02',sites:[]}],produtos:[],usuarios:[{id:'u2',company_id:'YLG-TESTE-02',login:'x',perfil:'lider'}]}))")
        page.reload(); aguardar_boot(page)
        login_ui(page, cid=CID)
        ids = page.evaluate("() => DB.clientes.map(c=>c.id)")
        res('R3b-cache-tenant-de-outra-empresa', 'CLI-CACHE-EMP02' not in ids, f'clientes visíveis para YLG-TESTE-01: {ids}')
        ctx.close()

    # R4 — gravação antes da hidratação (carregamento lento do IndexedDB)
    if run('R4'):
        ctx, page, fake, logs = novo(p)
        login_ui(page)
        page.evaluate(SEED_JS, 50)
        page.wait_for_timeout(800)
        antes = contagens(page)
        # Atraso artificial apenas na LEITURA do IndexedDB (simula base grande / disco lento)
        # Base grande: espelho localStorage não coube na quota (cenário real com ~2 MB+)
        page.evaluate("() => { localStorage.removeItem('wms_3cs_v2026'); localStorage.setItem('__simular_quota','1'); }")
        page.add_init_script("""(() => {
          if(localStorage.getItem('__simular_quota')){ const os=Storage.prototype.setItem; Storage.prototype.setItem=function(k,v){ if(k==='wms_3cs_v2026') throw new DOMException('QuotaExceededError','QuotaExceededError'); return os.call(this,k,v); }; }
          const origOpen = IDBFactory.prototype.open; let n=0; const __t0=performance.now();
          IDBFactory.prototype.open = function(){ const req = origOpen.apply(this, arguments); n++; if(performance.now()-__t0>1500) return req;
            let h=null; Object.defineProperty(req,'onsuccess',{configurable:true,set(fn){h=fn;},get(){return h;}});
            req.addEventListener('success', ev => setTimeout(()=>{ if(h) h.call(req, ev); }, 3000));
            return req; };
        })()""")
        page.reload()
        page.wait_for_function("() => typeof save==='function' && typeof DB!=='undefined'")
        page.wait_for_timeout(1800)
        # Ação do usuário/rotina que grava durante o boot (ex.: login rápido -> save())
        info = page.evaluate("() => { const c=_dbContagens(DB).produtos; try{ DB.auditoria.unshift({id:'AUD-BOOT',acao:'teste'}); save(); }catch(e){} return c; }")
        page.wait_for_timeout(400)
        # usuário pressiona F5 de novo antes de o carregamento terminar
        page.reload(); aguardar_boot(page); page.wait_for_timeout(5000)
        page.reload(); aguardar_boot(page); page.wait_for_timeout(5000)
        print('   produtos em memória no instante do save() durante o boot:', info)
        depois = contagens(page)
        res('R4-save-antes-da-hidratacao', depois['produtos'] == antes['produtos'] and depois['clientes'] == antes['clientes'],
            f"antes produtos={antes['produtos']} clientes={antes['clientes']}; depois produtos={depois['produtos']} clientes={depois['clientes']}")
        ctx.close()

    # R4b — F5 repetido durante o carregamento (beforeunload grava estado não hidratado)
    if run('R4b'):
        ctx, page, fake, logs = novo(p)
        login_ui(page)
        page.evaluate(SEED_JS, 50)
        page.wait_for_timeout(800)
        antes = contagens(page)
        page.evaluate("() => { localStorage.removeItem('wms_3cs_v2026'); localStorage.setItem('__simular_quota','1'); }")
        page.add_init_script("""(() => {
          if(localStorage.getItem('__simular_quota')){ const os=Storage.prototype.setItem; Storage.prototype.setItem=function(k,v){ if(k==='wms_3cs_v2026') throw new DOMException('QuotaExceededError','QuotaExceededError'); return os.call(this,k,v); }; }
          const origOpen = IDBFactory.prototype.open; const __t0=performance.now();
          IDBFactory.prototype.open = function(){ const req = origOpen.apply(this, arguments); if(performance.now()-__t0>1500) return req;
            let h=null; Object.defineProperty(req,'onsuccess',{configurable:true,set(fn){h=fn;},get(){return h;}});
            req.addEventListener('success', ev => setTimeout(()=>{ if(h) h.call(req, ev); }, 3000));
            return req; };
        })()""")
        page.reload()
        page.wait_for_function("() => typeof DB!=='undefined'")
        page.wait_for_timeout(1800)
        page.reload()  # F5 de novo antes de terminar de carregar
        page.wait_for_function("() => typeof DB!=='undefined'")
        page.wait_for_timeout(1800)
        page.reload()
        aguardar_boot(page); page.wait_for_timeout(5000)
        page.reload(); aguardar_boot(page); page.wait_for_timeout(5000)
        depois = contagens(page)
        res('R4b-F5-durante-carregamento', depois['produtos'] == antes['produtos'] and depois['clientes'] == antes['clientes'],
            f"antes produtos={antes['produtos']} clientes={antes['clientes']}; depois produtos={depois['produtos']} clientes={depois['clientes']}")
        ctx.close()

    # R5 — sessão revogada no servidor não pode ser restaurada localmente
    if run('R5'):
        ctx, page, fake, logs = novo(p)
        login_ui(page)
        page.evaluate("() => { const s = Core.sessionGet(SESSAO_KEY); Core.sessionSet(SESSAO_KEY, {...s, module_session_token:'tok-revogado-teste'}); }")
        page.wait_for_timeout(500)
        fake.sessoes_modulo['tok-revogado-teste'] = 'revogada'
        page.reload(); aguardar_boot(page); page.wait_for_timeout(5000)
        res('R5-sessao-revogada-nao-restaura', not logado(page), f'logado após F5 com token revogado={logado(page)}')
        ctx.close()

    # R6 — F5 com rede indisponível mantém a sessão
    if run('R6'):
        ctx, page, fake, logs = novo(p)
        login_ui(page)
        fake.modo = 'offline'
        page.reload(); aguardar_boot(page); page.wait_for_timeout(2000)
        a = logado(page)
        page.keyboard.press('Control+R'); aguardar_boot(page); page.wait_for_timeout(2000)
        b = logado(page)
        res('R6-F5-offline-mantem-sessao', a and b, f'F5 offline logado={a}; Ctrl+R offline logado={b}')
        ctx.close()

    # R7 — sessão SSO com falha transitória de rede não deve derrubar
    if run('R7'):
        ctx, page, fake, logs = novo(p)
        login_ui(page)
        fake.sessoes_modulo['tok-valido-teste'] = {'company_id': CID, 'login': OP_LOGIN, 'modulo': 'wms', 'nome': 'Lider Teste', 'perfil': 'LIDER'}
        page.evaluate("() => { const s = Core.sessionGet(SESSAO_KEY); Core.sessionSet(SESSAO_KEY, {...s, module_session_token:'tok-valido-teste'}); }")
        page.wait_for_timeout(400)
        fake.modo = 'offline'
        page.reload(); aguardar_boot(page); page.wait_for_timeout(6000)
        a = logado(page)
        fake.modo = 'ok'
        page.reload(); aguardar_boot(page); page.wait_for_timeout(3000)
        b = logado(page)
        res('R7-sso-falha-transitoria', a and b, f'offline logado={a}; online token válido logado={b}')
        ctx.close()

    # R8 — logout explícito encerra e F5 não restaura
    if run('R8'):
        ctx, page, fake, logs = novo(p)
        login_ui(page)
        page.evaluate("() => { window.wmsConfirm = async () => true; }")
        page.evaluate("() => fazerLogoff()")
        page.wait_for_timeout(1500)
        page.reload(); aguardar_boot(page); page.wait_for_timeout(1500)
        res('R8-logout-explicito', not logado(page), f'logado após logout+F5={logado(page)}')
        ctx.close()

ok = sum(1 for r in resultados if r[1])
print(f'TOTAL {ok}/{len(resultados)} PASS')
