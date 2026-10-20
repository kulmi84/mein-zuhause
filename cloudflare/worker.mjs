const MAX_BYTES = 131072;
const reply = (data, status = 200) => Response.json(data, { status,
  headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });

async function authorized(request, secret) {
  if (!secret || secret.length < 32) return false;
  const digest = async value => new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)));
  const [a, b] = await Promise.all([digest(request.headers.get('Authorization') || ''), digest(`Bearer ${secret}`)]);
  let different = 0;
  for (let i = 0; i < a.length; i++) different |= a[i] ^ b[i];
  return different === 0;
}

export function actionsFor(id) {
  const domain = id.split('.')[0];
  if (['light', 'switch', 'fan', 'input_boolean'].includes(domain)) return ['turn_on', 'turn_off'];
  return domain === 'cover' ? ['open_cover', 'close_cover'] : [];
}

export function validEntities(entities) {
  return Array.isArray(entities) && entities.length <= 100
    && new Set(entities.map(e => e?.entity_id)).size === entities.length
    && entities.every(e => e && typeof e.entity_id === 'string'
      && /^(binary_sensor|sensor|cover|light|switch|fan|input_boolean|lock|climate)\.[a-z0-9_]+$/.test(e.entity_id)
      && ['name', 'state', 'device_class', 'unit'].every(k => typeof e[k] === 'string' && e[k].length <= ({ name:120, state:255, device_class:60, unit:30 })[k])
      && Array.isArray(e.actions) && e.actions.every(a => actionsFor(e.entity_id).includes(a)));
}

async function readBody(request) {
  if (!request.headers.get('Content-Type')?.startsWith('application/json')) throw { status: 415, code: 'json_required' };
  const reader = request.body?.getReader();
  if (!reader) throw { status: 400, code: 'invalid_json' };
  const chunks = []; let length = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    length += value.length;
    if (length > MAX_BYTES) { await reader.cancel(); throw { status: 413, code: 'too_large' }; }
    chunks.push(value);
  }
  const joined = new Uint8Array(length); let offset = 0;
  for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.length; }
  try {
    const data = JSON.parse(new TextDecoder().decode(joined));
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw Error();
    return data;
  } catch { throw { status: 400, code: 'invalid_json' }; }
}

async function snapshot(env) {
  const row = await env.DB.prepare('SELECT entities_json, received_at FROM snapshot WHERE id = 1').first();
  if (!row) return null;
  const age = Math.max(0, Math.floor((Date.now() - Date.parse(row.received_at)) / 1000));
  return { entities: JSON.parse(row.entities_json), received_at: row.received_at, age_seconds: age, stale: age > 180 };
}

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    const routes = { '/health': ['GET','SYNC_TOKEN'], '/sync': ['POST','SYNC_TOKEN'],
      '/states': ['GET','READ_TOKEN'], '/commands': ['POST','CONTROL_TOKEN'], '/ack': ['POST','SYNC_TOKEN'] };
    const route = routes[path];
    if (!route) return reply({error:'not_found'},404);
    if (request.method !== route[0]) return reply({error:'method_not_allowed'},405);
    if (!await authorized(request, env[route[1]])) return reply({error:'unauthorized'},401);
    try {
      if (path === '/health') return reply({ service: 'mein_zuhause', version: '0.1.0' });
      if (path === '/states') {
        const data = await snapshot(env);
        return data ? reply(data) : reply({error:'no_data'},404);
      }
      const input = await readBody(request);
      const now = new Date().toISOString();
      if (path === '/sync') {
        if ('entities' in input) {
          if (!validEntities(input.entities)) return reply({error:'invalid_entities'},400);
          // Store only fields in our contract; never arbitrary HA attributes.
          const entities = input.entities.map(({entity_id,name,state,device_class,unit,actions}) => ({entity_id,name,state,device_class,unit,actions}));
          await env.DB.prepare('INSERT INTO snapshot(id,entities_json,received_at) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET entities_json=excluded.entities_json, received_at=excluded.received_at')
            .bind(JSON.stringify(entities), now).run();
        }
        await env.DB.prepare('DELETE FROM commands WHERE expires_at < ?').bind(new Date(Date.now()-86400000).toISOString()).run();
        // Atomic claim. A lost response cannot cause an action to be repeated.
        const claimed = await env.DB.prepare("UPDATE commands SET status='claimed' WHERE id IN (SELECT id FROM commands WHERE status='pending' AND expires_at > ? ORDER BY created_at LIMIT 10) AND status='pending' RETURNING id,entity_id,action,expires_at")
          .bind(now).all();
        return reply({ok:true,commands:claimed.results || []});
      }
      if (path === '/ack') {
        if (typeof input.id !== 'string' || !['done','failed'].includes(input.status)) return reply({error:'invalid_ack'},400);
        await env.DB.prepare("UPDATE commands SET status=? WHERE id=? AND status='claimed'").bind(input.status,input.id).run();
        return reply({ok:true});
      }
      if (typeof input.entity_id !== 'string' || typeof input.action !== 'string'
          || typeof input.id !== 'string' || !/^[a-zA-Z0-9-]{1,128}$/.test(input.id)) return reply({error:'invalid_command'},400);
      const data = await snapshot(env);
      if (!data || data.stale) return reply({error:'stale'},409);
      const entity = data.entities.find(e => e.entity_id === input.entity_id);
      if (!entity || !entity.actions.includes(input.action)) return reply({error:'not_allowed'},403);
      if (['unavailable','unknown'].includes(entity.state)) return reply({error:'unavailable'},409);
      const expires = new Date(Date.now()+15000).toISOString();
      await env.DB.prepare("INSERT INTO commands(id,entity_id,action,status,created_at,expires_at) VALUES(?,?,?,'pending',?,?) ON CONFLICT(id) DO NOTHING")
        .bind(input.id,input.entity_id,input.action,now,expires).run();
      return reply({ok:true,id:input.id,status:'accepted'});
    } catch (error) {
      return reply({error: error.code || 'storage_unavailable'},error.status || 503);
    }
  }
};
