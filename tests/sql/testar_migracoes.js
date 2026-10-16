// Testa as migrações 00–03 (e rollbacks) numa réplica isolada em PGlite
// (PostgreSQL real compilado para WASM). Nunca toca o projeto de produção.
// Uso: NODE_PATH=<node_modules com @electric-sql/pglite> node testar_migracoes.js
const fs = require('fs'), path = require('path');
const { PGlite } = require('@electric-sql/pglite');
const MIG = path.join(__dirname, '..', '..', 'supabase', 'migrations');
const ler = f => fs.readFileSync(path.join(MIG, f), 'utf8');
const resultados = [];
function rec(id, ok, ev) { resultados.push([id, ok]); console.log(`RESULT|${id}|${ok ? 'PASS' : 'FAIL'}|${ev}`); }

async function como(db, papel, uid, sql, params) {
  await db.exec('reset role');
  await db.query(`select set_config('request.jwt.claim.sub', $1, false)`, [uid || '']);
  if (papel) await db.exec(`set role ${papel}`);
  try { const r = await db.query(sql, params || []); return { ok: true, rows: r.rows, n: r.affectedRows }; }
  catch (e) { return { ok: false, erro: String(e.message || e) }; }
  finally { await db.exec('reset role'); }
}

(async () => {
  const db = new PGlite();
  await db.exec(fs.readFileSync(path.join(__dirname, 'replica_producao.sql'), 'utf8'));
  const INST = '11111111-1111-1111-1111-111111111111';

  // ── Linha de base: confirma os riscos na réplica antes das migrações ──
  let r = await como(db, 'anon', null, `select login, senha_hash from public.usuarios`);
  rec('S00-risco-hash-legivel-anon-ANTES', r.ok && r.rows.length === 2, `anon leu ${r.rows ? r.rows.length : 0} hashes de usuarios`);
  r = await como(db, 'anon', null, `delete from public.logs returning id`);
  rec('S00-risco-logs-apagaveis-ANTES', r.ok && r.rows.length === 1, `anon apagou ${r.rows ? r.rows.length : 0} log(s)`);
  await db.exec(`insert into public.logs(tipo, detalhe, company_id) values ('TESTE','log existente','YLG-TESTE-01')`);
  r = await como(db, 'authenticated', INST, `select public.registrar_instalacao_wms('YLG-TESTE-02')`);
  const vinc = await como(db, 'authenticated', INST, `select count(*)::int n from public.company_installations`);
  rec('S00-risco-vinculo-qualquer-empresa-ANTES', r.ok && vinc.rows[0].n === 1, `instalação anônima se vinculou a YLG-TESTE-02 sem credencial: ${r.ok}`);
  await db.exec(`delete from public.company_installations`);

  // ── Migração 00 (backup) ──
  await db.exec(ler('20261016120000_00_backup_pre_hardening.sql'));
  r = await db.query(`select (select count(*) from public.logs)::int a, (select count(*) from backup_20261016.logs)::int b, (select count(*) from pg_policies where schemaname='public')::int c, (select count(*) from backup_20261016.pg_policies_public)::int d`);
  rec('S01-backup-verificavel', r.rows[0].a === r.rows[0].b && r.rows[0].c === r.rows[0].d, JSON.stringify(r.rows[0]));
  r = await como(db, 'anon', null, `select count(*) from backup_20261016.logs`);
  rec('S01-backup-inacessivel-anon', !r.ok, r.erro || 'acessível!');

  // ── Migração 01 ──
  const polAntes = (await db.query(`select count(*)::int n from pg_policies where schemaname='public'`)).rows[0].n;
  await db.exec(ler('20261016120100_01_fase1_hardening_sem_impacto.sql'));
  r = await como(db, 'anon', null, `insert into public.logs(tipo, detalhe, company_id) values ('AUDITORIA_WMS','teste','YLG-TESTE-01') returning id`);
  rec('S02-logs-insert-anon-permitido', r.ok && r.rows.length === 1, r.erro || 'inseriu');
  r = await como(db, 'anon', null, `select count(*)::int n from public.logs`);
  rec('S02-logs-select-anon-permitido', r.ok && r.rows[0].n >= 2, r.erro || `linhas=${r.rows[0].n}`);
  r = await como(db, 'anon', null, `delete from public.logs`);
  rec('S02-logs-delete-anon-negado', !r.ok, r.erro || `apagou ${r.n}`);
  r = await como(db, 'anon', null, `update public.logs set detalhe='x'`);
  rec('S02-logs-update-anon-negado', !r.ok, r.erro || `alterou ${r.n}`);
  r = await como(db, 'anon', null, `select public.wms_kv_store_auditoria()`);
  rec('S02-trigger-fn-fora-da-api', !r.ok, r.erro || 'executou');
  await db.exec(`insert into public.company_installations(installation_id, company_id) values ('${INST}','YLG-TESTE-01')`);
  r = await como(db, 'authenticated', INST, `insert into public.wms_kv_store(key, value, company_id, module_id) values ('k1','{"a":1}','YLG-TESTE-01','wms') returning version, created_by::text`);
  rec('S02-trigger-auditoria-continua-disparando', r.ok && r.rows[0].version === 1 && r.rows[0].created_by === INST, r.erro || JSON.stringify(r.rows[0]));
  r = await como(db, 'authenticated', INST, `select count(*)::int n from public.wms_kv_store where company_id='YLG-TESTE-02'`);
  rec('S02-kv-isolamento-tenant-preservado', r.ok && r.rows[0].n === 0, r.erro || `n=${r.rows[0].n}`);
  r = await db.query(`select proname, proconfig::text c from pg_proc where proname in ('set_updated_at','gen_random_bytes','_patio_entidade_para_recurso') order by 1`);
  rec('S02-search-path-fixo', r.rows.every(x => (x.c || '').includes('search_path')), JSON.stringify(r.rows));
  r = await como(db, 'anon', null, `update public.usuarios set nome = nome where login='master.teste' returning updated_at`);
  rec('S02-set-updated-at-funciona', r.ok && r.rows.length === 1, r.erro || 'ok');

  // ── Migração 02 ──
  await db.exec(ler('20261016120200_02_fase2_rpcs_sessao_wms.sql'));
  const sessao = async (cid, login, hash) => (await como(db, 'anon', null, `select * from public.wms_criar_sessao($1,$2,$3)`, [cid, login, hash])).rows[0];
  let s = await sessao('YLG-TESTE-01', 'lider.teste', 'HASH-LIDER');
  rec('S03-sessao-operacional-ok', s.status === 'ok' && s.module_session_token && s.perfil === 'lider' && !('senha_hash' in s), JSON.stringify({ ...s, module_session_token: s.module_session_token ? '***' : null }));
  const tokLider = s.module_session_token;
  rec('S03-senha-invalida', (await sessao('YLG-TESTE-01', 'lider.teste', 'ERRADA')).status === 'senha-invalida', 'ok');
  rec('S03-usuario-inativo', (await sessao('YLG-TESTE-01', 'inativo.teste', 'HASH-IN')).status === 'inativo', 'ok');
  rec('S03-nao-encontrado', (await sessao('YLG-TESTE-01', 'ninguem', 'X')).status === 'nao-encontrado', 'ok');
  rec('S03-empresa-bloqueada', (await sessao('YLG-TESTE-BLOQ', 'x', 'x')).status === 'empresa-inativa', 'ok');
  s = await sessao('YLG-TESTE-01', 'MASTER.TESTE', 'HASH-MASTER');
  rec('S03-sessao-master-ok', s.status === 'ok' && s.perfil === 'master', s.status);
  const tokMaster = s.module_session_token;
  const tokOp = (await sessao('YLG-TESTE-01', 'operador.teste', 'HASH-OP')).module_session_token;
  const tokL2 = (await sessao('YLG-TESTE-02', 'lider.dois', 'HASH-L2')).module_session_token;
  r = await como(db, 'anon', null, `select * from public.wms_validar_sessao($1)`, [tokLider]);
  rec('S03-validar-sessao', r.ok && r.rows.length === 1 && r.rows[0].company_id === 'YLG-TESTE-01', r.erro || JSON.stringify(r.rows[0]));
  r = await como(db, 'anon', null, `select * from public.wms_operacionais_listar($1)`, [tokLider]);
  rec('S03-listar-sem-hash-e-so-propria-empresa', r.ok && r.rows.length === 3 && r.rows.every(x => !('senha_hash' in x) && x.company_id === 'YLG-TESTE-01'), r.erro || `n=${r.rows.length}`);
  r = await como(db, 'anon', null, `select * from public.wms_operacionais_listar($1)`, [tokOp]);
  rec('S03-listar-operador-negado', !r.ok, r.erro || 'listou');
  r = await como(db, 'anon', null, `select public.wms_operacionais_salvar($1, $2::jsonb) id`, [tokLider, JSON.stringify({ login: 'novo.teste', nome: 'Novo', perfil: 'conferente', senha_hash: 'H-NOVO' })]);
  rec('S03-lider-cria-usuario', r.ok, r.erro || 'criado');
  const idNovo = r.ok ? r.rows[0].id : null;
  r = await como(db, 'anon', null, `select public.wms_operacionais_salvar($1, $2::jsonb)`, [tokL2, JSON.stringify({ id: idNovo, login: 'sequestro', nome: 'X', perfil: 'lider' })]);
  rec('S03-cross-tenant-edicao-negada', !r.ok, r.erro || 'editou usuário de outra empresa!');
  r = await como(db, 'anon', null, `select public.wms_operacionais_excluir($1, $2::uuid)`, [tokLider, idNovo]);
  rec('S03-lider-nao-exclui', !r.ok, r.erro || 'excluiu');
  r = await como(db, 'anon', null, `select public.wms_operacionais_excluir($1, $2::uuid) ok`, [tokMaster, idNovo]);
  rec('S03-master-exclui', r.ok && r.rows[0].ok === true, r.erro || 'ok');
  r = await como(db, 'anon', null, `select public._wms_sessao_contexto($1)`, [tokLider]);
  rec('S03-funcao-interna-fora-da-api', !r.ok, r.erro || 'executou');
  const INST2 = '22222222-2222-2222-2222-222222222222';
  r = await como(db, 'authenticated', INST2, `select public.registrar_instalacao_wms_v2('token-falso')`);
  rec('S03-vinculo-v2-sem-sessao-negado', !r.ok, r.erro || 'vinculou');
  r = await como(db, 'authenticated', INST2, `select public.registrar_instalacao_wms_v2($1)`, [tokLider]);
  const ci = await db.query(`select company_id from public.company_installations where installation_id='${INST2}'`);
  rec('S03-vinculo-v2-com-sessao', r.ok && ci.rows[0] && ci.rows[0].company_id === 'YLG-TESTE-01', r.erro || JSON.stringify(ci.rows));
  await como(db, 'anon', null, `select public.wms_revogar_sessao($1)`, [tokOp]);
  r = await como(db, 'anon', null, `select * from public.wms_validar_sessao($1)`, [tokOp]);
  rec('S03-sessao-revogada-invalida', r.ok && r.rows.length === 0, r.erro || `linhas=${r.rows.length}`);
  await db.exec(`update public.usuarios_operacionais set ativo=false where login='lider.teste'`);
  r = await como(db, 'anon', null, `select * from public.wms_validar_sessao($1)`, [tokLider]);
  rec('S03-usuario-desativado-invalida-sessao', r.ok && r.rows.length === 0, r.erro || `linhas=${r.rows.length}`);
  await db.exec(`update public.usuarios_operacionais set ativo=true where login='lider.teste'`);
  r = await como(db, 'anon', null, `select login from public.usuarios`);
  rec('S03-fase2-nao-remove-acesso-legado', r.ok && r.rows.length === 2, 'login legado do WMS segue funcionando enquanto a Fase 3 não é aplicada');

  // ── Migração 03 (bloqueada para produção — testada aqui) ──
  await db.exec(ler('20261016120300_03_fase3_restricao_anon_BLOQUEADA.sql'));
  r = await como(db, 'anon', null, `select senha_hash from public.usuarios`);
  rec('S04-hash-nao-legivel-anon', !r.ok, r.erro || 'leu hashes');
  r = await como(db, 'anon', null, `select senha_hash from public.usuarios_operacionais`);
  rec('S04-hash-operacional-nao-legivel', !r.ok, r.erro || 'leu');
  r = await como(db, 'anon', null, `update public.licencas set validade='2099-01-01'`);
  rec('S04-licenca-nao-alteravel-anon', !r.ok, r.erro || 'alterou');
  r = await como(db, 'anon', null, `select count(*)::int n from public.empresas`);
  rec('S04-empresas-leitura-mantida', r.ok && r.rows[0].n === 3, r.erro || 'ok');
  s = await sessao('YLG-TESTE-01', 'lider.teste', 'HASH-LIDER');
  rec('S04-login-via-rpc-funciona', s && s.status === 'ok', s ? s.status : 'sem retorno');
  r = await como(db, 'authenticated', INST, `select public.registrar_instalacao_wms('YLG-TESTE-02')`);
  rec('S04-vinculo-v1-sem-prova-negado', !r.ok, r.erro || 'vinculou');

  // ── Rollbacks (ordem inversa) ──
  await db.exec(ler('20261016120300_03_fase3_restricao_anon_BLOQUEADA.rollback.sql'));
  r = await como(db, 'anon', null, `select count(*)::int n from public.usuarios`);
  rec('S05-rollback-03', r.ok && r.rows[0].n === 2, r.erro || 'ok');
  await db.exec(ler('20261016120200_02_fase2_rpcs_sessao_wms.rollback.sql'));
  r = await db.query(`select count(*)::int n from pg_proc where proname like 'wms\\_%' and proname not like 'wms_kv%'`);
  rec('S05-rollback-02', r.rows[0].n === 0, `funções wms_* restantes=${r.rows[0].n}`);
  await db.exec(ler('20261016120100_01_fase1_hardening_sem_impacto.rollback.sql'));
  const polDepois = (await db.query(`select count(*)::int n from pg_policies where schemaname='public'`)).rows[0].n;
  const difPol = await db.query(`select policyname, tablename, cmd, roles::text, qual, with_check from pg_policies where schemaname='public' except select policyname, tablename, cmd, roles::text, qual, with_check from backup_20261016.pg_policies_public`);
  rec('S05-rollback-01-politicas-identicas-ao-backup', polDepois === polAntes && difPol.rows.length === 0, `políticas antes=${polAntes} depois=${polDepois} diferenças=${difPol.rows.length}`);

  const ok = resultados.filter(x => x[1]).length;
  console.log(`TOTAL ${ok}/${resultados.length} PASS`);
  process.exit(ok === resultados.length ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
