import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

// Creates a Razorpay order for the signed-in person. The PRICE IS SET HERE ON THE SERVER, never taken from the browser.
// Secrets: RAZORPAY_KEY_SECRET (required). RAZORPAY_KEY_ID is optional; the test key id below is used if it is not set.
const PRICES: Record<string, number> = { full: 29900, career: 9900 }; // in paise: Rs 299 and Rs 99
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...cors, "Content-Type": "application/json" } });

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "method" }, 405);
  const secret = Deno.env.get("RAZORPAY_KEY_SECRET");
  const keyId = Deno.env.get("RAZORPAY_KEY_ID") || "rzp_test_U0qOhf5wTHJHXP";
  if (!secret) return json({ error: "payments are not set up yet" }, 503);

  const url = Deno.env.get("SUPABASE_URL")!;
  const authHeader = req.headers.get("Authorization") || "";
  const asUser = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, { global: { headers: { Authorization: authHeader } } });
  const { data: u } = await asUser.auth.getUser();
  const user = u?.user;
  if (!user) return json({ error: "sign in first" }, 401);

  let body: { kind?: string; careerId?: string } = {};
  try { body = await req.json(); } catch { return json({ error: "bad request" }, 400); }
  const kind = String(body.kind || "");
  if (!(kind in PRICES)) return json({ error: "bad request" }, 400);
  let careerId: string | null = null;
  if (kind === "career") {
    careerId = String(body.careerId || "");
    if (!/^[a-z0-9-]{1,80}$/.test(careerId)) return json({ error: "bad request" }, 400);
  }

  const db = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: owned } = await db.from("purchases").select("kind,career_id").eq("user_id", user.id).eq("status", "paid");
  const has = (owned || []).some((p: { kind: string; career_id: string | null }) => p.kind === "full" || (kind === "career" && p.career_id === careerId));
  if (has) return json({ already: true });

  const amount = PRICES[kind];
  const r = await fetch("https://api.razorpay.com/v1/orders", {
    method: "POST",
    headers: { Authorization: "Basic " + btoa(`${keyId}:${secret}`), "Content-Type": "application/json" },
    body: JSON.stringify({ amount, currency: "INR", receipt: `p4_${Date.now()}`.slice(0, 40), notes: { user_id: user.id, kind, career_id: careerId || "" } }),
  });
  if (!r.ok) return json({ error: "could not start the payment" }, 502);
  const order = await r.json();
  const { error } = await db.from("purchases").insert({ user_id: user.id, kind, career_id: careerId, amount_paise: amount, currency: "INR", razorpay_order_id: order.id, status: "created" });
  if (error) return json({ error: "could not start the payment" }, 500);
  return json({ orderId: order.id, amount, currency: "INR", keyId });
});
