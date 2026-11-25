// Checks the Supabase edge functions in supabase/functions/ with a mock database (no network, no Deno needed).
// Covers: browser origin allow-list, login required, price set on the server, order rate limit, signature checks,
// and the waitlist lookup treating % and _ literally. Run: node scripts/ci/check_edge_functions.mjs
import fs from 'node:fs'; import { stripTypeScriptTypes } from 'node:module';
const load = (name, mock) => {
  let src = fs.readFileSync(new URL(`../../supabase/functions/${name}/index.ts`, import.meta.url), 'utf8').replace(/^import .*$/mg, '');
  const js = stripTypeScriptTypes(src);
  let handler; const Deno = { serve: (h) => { handler = h; }, env: { get: (k) => mock.env[k] } };
  new Function('Deno', 'createClient', js)(Deno, mock.createClient); return handler;
};
const fails = []; const ok = (c, m) => { console.log((c ? 'PASS ' : 'FAIL ') + m); if (!c) fails.push(m); };
const q = (rows, count) => { const o = { _filters: [], select() { return o; }, eq(k, v) { o._filters.push([k, v]); return o; }, gte() { return o; }, ilike(k, v) { o.ilikeArg = v; return o; }, maybeSingle: async () => ({ data: rows }), then(res) { res({ data: [], count: count ?? 0 }); }, insert: async () => ({ error: null }), update() { return o; } }; return o; };
const req = (origin, body, extra = {}) => new Request('https://x/f', { method: 'POST', headers: { 'Content-Type': 'application/json', ...(origin ? { Origin: origin } : {}), ...(extra.auth ? { Authorization: 'Bearer t' } : {}) }, body: JSON.stringify(body) });

// ---- create-order
{
  let recent = 0; const calls = [];
  const mock = { env: { RAZORPAY_KEY_SECRET: 's', RAZORPAY_KEY_ID: 'k', SUPABASE_URL: 'u', SUPABASE_ANON_KEY: 'a', SUPABASE_SERVICE_ROLE_KEY: 'r' },
    createClient: (u, key, opts) => key === 'a' ? { auth: { getUser: async () => ({ data: { user: (opts?.global?.headers?.Authorization || '').length > 7 ? { id: 'u1' } : null } }) } } : { from: () => q([], recent) } };
  const h = load('razorpay-create-order', mock);
  let r = await h(new Request('https://x/f', { method: 'OPTIONS', headers: { Origin: 'https://plan4it.co' } }));
  ok(r.headers.get('Access-Control-Allow-Origin') === 'https://plan4it.co', 'create-order: allowed origin is echoed');
  r = await h(new Request('https://x/f', { method: 'OPTIONS', headers: { Origin: 'https://evil.example' } }));
  ok(!r.headers.get('Access-Control-Allow-Origin'), 'create-order: other origin gets no CORS permission');
  ok(r.headers.get('Vary') === 'Origin', 'create-order: Vary: Origin set');
  r = await h(req('https://plan4it.co', { kind: 'full', ageDecl: 'adult', snapshot: 'q:abcdef' }));
  ok(r.status === 401, 'create-order: no login -> 401');
  r = await h(req('https://plan4it.co', { kind: 'full', snapshot: 'q:abcdef' }, { auth: 1 }));
  ok(r.status === 400, 'create-order: missing age declaration -> 400');
  r = await h(req('https://plan4it.co', { kind: 'free', ageDecl: 'adult' }, { auth: 1 }));
  ok(r.status === 400, 'create-order: unknown product -> 400');
  recent = 15;
  r = await h(req('https://plan4it.co', { kind: 'full', ageDecl: 'adult', snapshot: 'q:abcdef' }, { auth: 1 }));
  ok(r.status === 429, 'create-order: 15 orders in the last hour -> 429');
  recent = 3; const realFetch = globalThis.fetch; globalThis.fetch = async () => new Response(JSON.stringify({ id: 'order_1' }), { status: 200 });
  r = await h(req('https://plan4it.co', { kind: 'full', ageDecl: 'adult', snapshot: 'q:abcdef' }, { auth: 1 }));
  const j = await r.json(); globalThis.fetch = realFetch;
  ok(r.status === 200 && j.amount === 29900 && j.orderId === 'order_1', 'create-order: normal purchase still works, price set on server (29900)');
}
// ---- waitlist-email
{
  let seen; const mock = { env: { SUPABASE_URL: 'u', SUPABASE_SERVICE_ROLE_KEY: 'r' }, createClient: () => ({ from: () => { const o = q(null); const il = o.ilike; o.ilike = (k, v) => { seen = v; return il(k, v); }; return o; } }) };
  const h = load('waitlist-email', mock);
  let r = await h(req('https://plan4it.co', { email: '%@%.com', track: 'data' }));
  ok(r.status === 400, 'waitlist-email: wildcard address "%@%.com" rejected');
  r = await h(req('https://plan4it.co', { email: 'a_b@x.com', track: 'data' }));
  ok(r.status === 404 && seen === 'a\\_b@x.com', 'waitlist-email: "_" is matched literally (' + seen + ')');
  r = await h(req('https://plan4it.co', { email: 'x'.repeat(300) + '@x.com', track: 'data' }));
  ok(r.status === 400, 'waitlist-email: oversize address rejected');
  r = await h(req('https://evil.example', { email: 'a@x.com', track: 'data' }));
  ok(!r.headers.get('Access-Control-Allow-Origin'), 'waitlist-email: other origin gets no CORS permission');
}
// ---- verify
{
  const mock = { env: { RAZORPAY_KEY_SECRET: 's', SUPABASE_URL: 'u', SUPABASE_ANON_KEY: 'a', SUPABASE_SERVICE_ROLE_KEY: 'r' }, createClient: (u, key) => key === 'a' ? { auth: { getUser: async () => ({ data: { user: { id: 'u1' } } }) } } : { from: () => q({ id: 1, status: 'created' }) } };
  const h = load('razorpay-verify', mock);
  let r = await h(req('https://plan4it.co', { razorpay_order_id: 'o', razorpay_payment_id: 'p', razorpay_signature: 'bad' }, { auth: 1 }));
  ok(r.status === 400, 'verify: wrong signature -> 400');
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode('s'), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = [...new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode('o|p')))].map(b => b.toString(16).padStart(2, '0')).join('');
  r = await h(req('https://plan4it.co', { razorpay_order_id: 'o', razorpay_payment_id: 'p', razorpay_signature: sig }, { auth: 1 }));
  ok(r.status === 200, 'verify: correct signature -> 200');
  r = await h(req('https://plan4it.co', { razorpay_order_id: 'o'.repeat(100), razorpay_payment_id: 'p', razorpay_signature: sig }, { auth: 1 }));
  ok(r.status === 400, 'verify: oversize order id rejected');
}
// ---- webhook
{
  const mock = { env: { RAZORPAY_WEBHOOK_SECRET: 'w', SUPABASE_URL: 'u', SUPABASE_SERVICE_ROLE_KEY: 'r' }, createClient: () => ({ from: () => q(null) }) };
  const h = load('razorpay-webhook', mock);
  let r = await h(new Request('https://x/f', { method: 'POST', headers: { 'x-razorpay-signature': 'nope' }, body: '{}' }));
  ok(r.status === 400, 'webhook: bad signature -> 400');
  r = await h(new Request('https://x/f', { method: 'POST', body: 'x'.repeat(200000) }));
  ok(r.status === 413, 'webhook: oversize body -> 413');
  ok(!r.headers.get('Access-Control-Allow-Origin'), 'webhook: sends no CORS permission');
}
console.log(fails.length ? '\n' + fails.length + ' FAILED' : '\nALL PASSED'); process.exit(fails.length ? 1 : 0);
