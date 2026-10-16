"""Harness de testes do YALog WMS em Chromium headless (Playwright).

- Serve o index.html em uma origem isolada (https://wms.test/).
- CDNs servidas a partir de cópias locais obtidas do npm (sandbox sem acesso às CDNs).
- Supabase SIMULADO por rota (o sandbox não alcança *.supabase.co). Os dados
  simulados são exclusivamente de TESTE (empresa YLG-TESTE-01), nunca de produção.
"""
import hashlib, json, os, re, time, uuid

VENDOR = os.environ.get('WMS_VENDOR', os.path.join(os.path.dirname(__file__), 'vendor'))
V = lambda *p: os.path.abspath(os.path.join(VENDOR, *p))
CDN = {
    'supabase.min.js': V('supabase-supabase-js-2.118.0', 'package', 'dist', 'umd', 'supabase.js'),
    'chart.umd.min.js': V('chart.js-4.4.1', 'package', 'dist', 'chart.umd.js'),
    'lucide.js': V('lucide-1.58.0', 'package', 'dist', 'umd', 'lucide.min.js'),
    'xlsx.full.min.js': V('xlsx-0.18.5', 'package', 'dist', 'xlsx.full.min.js'),
    'qrcode.min.js': V('qrcodejs-1.0.0', 'package', 'qrcode.min.js'),
    'JsBarcode.all.min.js': V('jsbarcode-3.11.6', 'package', 'dist', 'JsBarcode.all.min.js'),
}
ORIGIN = 'https://wms.test/'

CID = 'YLG-TESTE-01'
CID_OUTRA = 'YLG-TESTE-02'
OP_LOGIN, OP_SENHA = 'lider.teste', 'Teste@2026'
MASTER_LOGIN, MASTER_SENHA = 'master.teste', 'Master@2026'


def h(senha):
    return hashlib.sha256((senha + '::yalog').encode()).hexdigest()


class FakeSupabase:
    """Estado simulado do backend. modo: 'ok' | 'offline' | 'lento'."""
    def __init__(self):
        self.modo = 'ok'
        self.chamadas = []
        self.sessoes_modulo = {}  # token -> dict | 'revogada'
        self.op_users = [{
            'id': str(uuid.uuid4()), 'company_id': CID, 'login': OP_LOGIN, 'nome': 'Lider Teste',
            'perfil': 'lider', 'senha_hash': h(OP_SENHA), 'ativo': True, 'obrigar_troca_senha': False,
            'ultimo_login': None, 'ultima_troca_senha': None, 'criado_em': '2026-10-01T00:00:00Z',
            'atualizado_em': '2026-10-01T00:00:00Z', 'origem': 'teste', 'modulo': 'wms', 'nivel': 1, 'versao': 1}]
        self.masters = [{'id': 9001, 'company_id': CID, 'login': MASTER_LOGIN, 'nome': 'Master Teste', 'senha_hash': h(MASTER_SENHA),
                         'role': 'MASTER', 'ativo': True, 'obrigar_troca_senha': False}]
        u2 = dict(self.op_users[0]); u2.update({'id': str(uuid.uuid4()), 'company_id': CID_OUTRA, 'nome': 'Lider Teste Emp02'})
        self.op_users.append(u2)

    def handle(self, route, request):
        url = request.url
        self.chamadas.append((request.method, url))
        if self.modo == 'offline':
            return route.abort('internetdisconnected')
        if self.modo == 'lento':
            time.sleep(2.5)
        m = re.search(r'/rest/v1/(rpc/)?([a-z_]+)', url)
        nome = m.group(2) if m else ''
        cid = None
        mm = re.search(r'company_id=eq\.([A-Za-z0-9\-]+)', url)
        if mm:
            cid = mm.group(1)
        body = []
        status = 200
        if m and m.group(1):  # RPC
            if nome == 'validar_sessao_modulo':
                payload = json.loads(request.post_data or '{}')
                s = self.sessoes_modulo.get(payload.get('p_token'))
                body = [s] if isinstance(s, dict) else []
            elif nome == 'revogar_sessao_modulo':
                payload = json.loads(request.post_data or '{}')
                if payload.get('p_token') in self.sessoes_modulo:
                    self.sessoes_modulo[payload['p_token']] = 'revogada'
                body = True
            else:
                body = None
        elif nome == 'empresas':
            body = [{'company_id': cid, 'ativo': True, 'nome_fantasia': 'EMPRESA TESTE ' + (cid or '')}] if cid in (CID, CID_OUTRA) else []
        elif nome == 'licencas':
            body = [{'company_id': cid, 'status': 'ATIVA', 'validade': None}] if cid in (CID, CID_OUTRA) else []
        elif nome == 'modulos':
            body = [{'company_id': cid, 'modulo': 'wms', 'status': 'LIBERADO'}] if cid in (CID, CID_OUTRA) else []
        elif nome == 'usuarios_operacionais':
            if request.method == 'GET':
                body = [u for u in self.op_users if (cid is None or u['company_id'] == cid)]
            else:
                status, body = 201, []
        elif nome == 'usuarios':
            ml = re.search(r'login=eq\.([^&]+)', url)
            body = [u for u in self.masters if u['company_id'] == cid and (not ml or u['login'] == ml.group(1))]
        elif nome == 'logs':
            status, body = 201, []
        return route.fulfill(status=status, content_type='application/json', body=json.dumps(body))


def montar_contexto(browser_type, html_path, user_data_dir, fake, init_script=None):
    ctx = browser_type.launch_persistent_context(user_data_dir, headless=True, ignore_https_errors=True)
    html = open(html_path, 'rb').read()

    def rota(route, request):
        u = request.url
        if u.startswith(ORIGIN):
            return route.fulfill(status=200, content_type='text/html; charset=utf-8', body=html)
        if '.supabase.co' in u:
            return fake.handle(route, request)
        if 'fonts.googleapis' in u or 'fonts.gstatic' in u:
            return route.fulfill(status=200, content_type='text/css', body='')
        for nome, caminho in CDN.items():
            if u.split('?')[0].endswith(nome) or (nome == 'lucide.js' and 'lucide' in u):
                return route.fulfill(status=200, content_type='application/javascript', body=open(caminho, 'rb').read())
        return route.abort()

    ctx.route('**/*', rota)
    if init_script:
        ctx.add_init_script(init_script)
    return ctx


def abrir(ctx, logs=None):
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    if logs is not None:
        page.on('console', lambda m: logs.append(f'[{m.type}] {m.text}'))
        page.on('pageerror', lambda e: logs.append(f'[pageerror] {e}'))
    page.goto(ORIGIN)
    return page


def aguardar_boot(page, timeout=15000):
    page.wait_for_function("() => typeof DB !== 'undefined' && document.readyState === 'complete'", timeout=timeout)
    page.wait_for_timeout(1500)


def logado(page):
    return page.evaluate("() => !!(typeof usuarioAtual!=='undefined' && usuarioAtual) && getComputedStyle(document.getElementById('loginOverlay')).display==='none'")


def login_ui(page, cid=CID, login=OP_LOGIN, senha=OP_SENHA):
    page.wait_for_selector('#loginCompanyId', state='visible', timeout=15000)
    page.fill('#loginCompanyId', cid)
    page.fill('#loginUsuario', login)
    page.fill('#loginSenha', senha)
    page.click('#btnLoginWms')
    page.wait_for_function("() => typeof usuarioAtual!=='undefined' && !!usuarioAtual", timeout=15000)
    page.wait_for_timeout(1500)


def contagens(page):
    return page.evaluate("() => _dbContagens(DB)")


def idb_canonico(page):
    return page.evaluate("""() => new Promise(res => {
      const r = indexedDB.open('YALOG_WMS_LOCAL_DB');
      r.onsuccess = () => { const db = r.result; if(!db.objectStoreNames.contains('estado')){res(null);return;}
        const g = db.transaction('estado','readonly').objectStore('estado').getAll();
        g.onsuccess = () => { const keysReq = db.transaction('estado','readonly').objectStore('estado').getAllKeys();
          keysReq.onsuccess = () => { const out = {}; keysReq.result.forEach((k,i)=>{ const v=g.result[i]; out[k] = v && v.db ? {clientes:(v.db.clientes||[]).map(c=>c.id), produtos:(v.db.produtos||[]).map(p=>[p.wmsId,p.qtd]), meta:v.db._persistMeta||null} : (v && v.sessao ? 'sessao' : v); }); res(out); }; };
      };
      r.onerror = () => res(null);
    })""")
