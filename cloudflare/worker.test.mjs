import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import worker from './worker.mjs';

function setup() {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec(readFileSync(new URL('./schema.sql', import.meta.url), 'utf8'));
  const DB = { prepare(sql) {
    let args = [];
    return { bind(...values) { args = values; return this; },
      async first() { return sqlite.prepare(sql).get(...args) || null; },
      async all() { return {results: sqlite.prepare(sql).all(...args)}; },
      async run() { return sqlite.prepare(sql).run(...args); } };
  } };
  const env = { DB, SYNC_TOKEN: 's'.repeat(40), READ_TOKEN: 'r'.repeat(40), CONTROL_TOKEN: 'c'.repeat(40) };
  const call = (path, method='GET', token=env.READ_TOKEN, body) => worker.fetch(new Request('https://test.local'+path,
    {method, headers: {Authorization:'Bearer '+token,'Content-Type':'application/json'}, body:body === undefined ? undefined : JSON.stringify(body)}),env);
  const entity = {entity_id:'cover.garagentor', name:'Garagentor', state:'open', device_class:'garage', unit:'', actions:['close_cover']};
  return {sqlite, env, call, entity};
}

test('independent credentials and authenticated routes', async () => {
  const {call, env} = setup();
  assert.equal((await call('/health','GET',env.SYNC_TOKEN)).status,200);
  assert.equal((await call('/states','GET',env.SYNC_TOKEN)).status,401);
  assert.equal((await call('/sync','POST',env.READ_TOKEN,{})).status,401);
  assert.equal((await call('/commands','POST',env.READ_TOKEN,{})).status,401);
});

test('snapshot replacement revokes removed entities and strips private fields', async () => {
  const {call,env,entity} = setup();
  assert.equal((await call('/sync','POST',env.SYNC_TOKEN,{entities:[{...entity,access_token:'secret'}]})).status,200);
  let data = await (await call('/states')).json();
  assert.equal(data.entities.length,1);
  assert.equal(JSON.stringify(data).includes('secret'),false);
  await call('/sync','POST',env.SYNC_TOKEN,{entities:[]});
  data = await (await call('/states')).json();
  assert.deepEqual(data.entities,[]);
});

test('read-only and stale snapshots cannot authorize commands', async () => {
  const {call,env,entity,sqlite} = setup();
  await call('/sync','POST',env.SYNC_TOKEN,{entities:[{...entity,actions:[]}]});
  const cmd = {id:'test',entity_id:entity.entity_id,action:'close_cover'};
  assert.equal((await call('/commands','POST',env.CONTROL_TOKEN,cmd)).status,403);
  await call('/sync','POST',env.SYNC_TOKEN,{entities:[entity]});
  sqlite.exec("UPDATE snapshot SET received_at='2000-01-01T00:00:00.000Z'");
  assert.equal((await call('/commands','POST',env.CONTROL_TOKEN,cmd)).status,409);
});

test('duplicate delivery, atomic claim, expiry and acknowledgement', async () => {
  const {call,env,entity,sqlite} = setup();
  await call('/sync','POST',env.SYNC_TOKEN,{entities:[entity]});
  const cmd = {id:'alexa-request',entity_id:entity.entity_id,action:'close_cover'};
  for (let i=0;i<2;i++) assert.equal((await call('/commands','POST',env.CONTROL_TOKEN,cmd)).status,200);
  let data = await (await call('/sync','POST',env.SYNC_TOKEN,{})).json();
  assert.equal(data.commands.length,1);
  assert.equal((await (await call('/sync','POST',env.SYNC_TOKEN,{})).json()).commands.length,0);
  await call('/ack','POST',env.SYNC_TOKEN,{id:cmd.id,status:'done'});
  assert.equal(sqlite.prepare('SELECT status FROM commands WHERE id=?').get(cmd.id).status,'done');
  await call('/commands','POST',env.CONTROL_TOKEN,{...cmd,id:'expired'});
  sqlite.exec("UPDATE commands SET expires_at='2000-01-01T00:00:00.000Z' WHERE id='expired'");
  data = await (await call('/sync','POST',env.SYNC_TOKEN,{})).json();
  assert.equal(data.commands.length,0);
});

test('malformed data, excessive entities, unsupported actions', async () => {
  const {call,env,entity} = setup();
  for (const entities of [null,[entity,entity],[{...entity,actions:['unlock']}],[{...entity,name:'x'.repeat(121)}]]) {
    assert.equal((await call('/sync','POST',env.SYNC_TOKEN,{entities})).status,400);
  }
  assert.equal((await call('/sync','POST',env.SYNC_TOKEN,{entities:[],extra:'x'.repeat(131072)})).status,413);
});
