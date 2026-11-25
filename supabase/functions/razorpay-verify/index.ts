import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

// Checks Razorpay's signature for a finished payment and, only if it is valid, marks the purchase as paid.
const ALLOWED_ORIGINS = ["https://plan4it.co", "https://www.plan4it.co", "https://staging--plan4it-app.netlify.app"];
const corsFor = (req: Request) => {
  const o = req.headers.get("Origin") || "";
  return {
    ...(ALLOWED_ORIGINS.includes(o) ? { "Access-Control-Allow-Origin": o } : {}),
    "Vary": "Origin",
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
  };
};
async function hmacHex(secret: string, msg: string) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const s = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(msg));
  return [...new Uint8Array(s)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
const safeEq = (a: string, b: string) => { if (a.length !== b.length) return false; let r = 0; for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i); return r === 0; };

Deno.serve(async (req: Request) => {
  const cors = corsFor(req);
  const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...cors, "Content-Type": "application/json" } });
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "method" }, 405);
  const secret = Deno.env.get("RAZORPAY_KEY_SECRET");
  if (!secret) return json({ error: "payments are not set up yet" }, 503);
  const url = Deno.env.get("SUPABASE_URL")!;
  const asUser = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, { global: { headers: { Authorization: req.headers.get("Authorization") || "" } } });
  const { data: u } = await asUser.auth.getUser();
  if (!u?.user) return json({ error: "sign in first" }, 401);

  let b: { razorpay_order_id?: string; razorpay_payment_id?: string; razorpay_signature?: string } = {};
  try { b = await req.json(); } catch { return json({ error: "bad request" }, 400); }
  const oid = String(b.razorpay_order_id || ""), pid = String(b.razorpay_payment_id || ""), sig = String(b.razorpay_signature || "");
  if (!oid || !pid || !sig || oid.length > 64 || pid.length > 64 || sig.length > 128) return json({ error: "bad request" }, 400);
  const expected = await hmacHex(secret, `${oid}|${pid}`);
  if (!safeEq(expected, sig)) return json({ ok: false, error: "signature mismatch" }, 400);

  const db = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: row } = await db.from("purchases").select("id,status").eq("razorpay_order_id", oid).eq("user_id", u.user.id).maybeSingle();
  if (!row) return json({ ok: false, error: "order not found" }, 404);
  if (row.status !== "paid") await db.from("purchases").update({ status: "paid", razorpay_payment_id: pid, paid_at: new Date().toISOString() }).eq("id", row.id);
  return json({ ok: true });
});
