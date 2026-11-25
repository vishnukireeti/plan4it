import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

// Razorpay calls this when a payment is captured, so the purchase is recorded even if the customer closes the page.
// It is not called by browsers: it is protected by Razorpay's signature (RAZORPAY_WEBHOOK_SECRET), not a login.
// (Deployed with "verify JWT" off on purpose: Razorpay cannot send a Supabase login. No CORS headers: browsers must not call it.)
async function hmacHex(secret: string, msg: string) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const s = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(msg));
  return [...new Uint8Array(s)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
const safeEq = (a: string, b: string) => { if (a.length !== b.length) return false; let r = 0; for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i); return r === 0; };

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return new Response("method", { status: 405 });
  const secret = Deno.env.get("RAZORPAY_WEBHOOK_SECRET");
  if (!secret) return new Response("not configured", { status: 503 });
  const raw = await req.text();
  if (raw.length > 100_000) return new Response("too large", { status: 413 });
  const sig = req.headers.get("x-razorpay-signature") || "";
  if (!safeEq(await hmacHex(secret, raw), sig)) return new Response("bad signature", { status: 400 });

  let ev: { event?: string; payload?: { payment?: { entity?: { id?: string; order_id?: string } }; order?: { entity?: { id?: string } } } } = {};
  try { ev = JSON.parse(raw); } catch { return new Response("bad body", { status: 400 }); }
  if (ev.event === "payment.captured" || ev.event === "order.paid") {
    const pay = ev.payload?.payment?.entity;
    const orderId = pay?.order_id || ev.payload?.order?.entity?.id;
    if (orderId) {
      const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
      await db.from("purchases").update({ status: "paid", razorpay_payment_id: pay?.id || null, paid_at: new Date().toISOString() }).eq("razorpay_order_id", orderId).eq("status", "created");
    }
  }
  return new Response("ok", { status: 200 });
});
