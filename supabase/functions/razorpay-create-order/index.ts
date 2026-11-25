import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

// Creates a Razorpay order for the signed-in person. The PRICE IS SET HERE ON THE SERVER, never taken from the browser.
// Secrets: RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET (both required; use the live pair in production).
const PRICES: Record<string, number> = { full: 29900, career: 9900 }; // in paise: Rs 299 and Rs 99
const MAX_ORDERS_PER_HOUR = 15; // per person; stops a script from spamming Razorpay and filling the purchases table

// Only the site itself may call this from a browser.
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

Deno.serve(async (req: Request) => {
  const cors = corsFor(req);
  const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...cors, "Content-Type": "application/json" } });
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "method" }, 405);
  const secret = Deno.env.get("RAZORPAY_KEY_SECRET");
  const keyId = Deno.env.get("RAZORPAY_KEY_ID");
  if (!secret || !keyId) return json({ error: "payments are not set up yet" }, 503);

  const url = Deno.env.get("SUPABASE_URL")!;
  const authHeader = req.headers.get("Authorization") || "";
  const asUser = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, { global: { headers: { Authorization: authHeader } } });
  const { data: u } = await asUser.auth.getUser();
  const user = u?.user;
  if (!user) return json({ error: "sign in first" }, 401);

  let body: { kind?: string; careerId?: string; scope?: string; snapshot?: string; ageDecl?: string } = {};
  try { body = await req.json(); } catch { return json({ error: "bad request" }, 400); }
  const kind = String(body.kind || "");
  // Payment confirmation is mandatory: the payer is 18+, or the student is under 18 and a parent/guardian was consulted.
  if (body.ageDecl !== "adult" && body.ageDecl !== "minor_with_guardian") return json({ error: "age confirmation required" }, 400);
  if (!(kind in PRICES)) return json({ error: "bad request" }, 400);
  let careerId: string | null = null;
  let scope: string | null = null;
  // The snapshot is a fingerprint of the quiz answers or saved items the report is built from. A purchase only
  // unlocks the report for that exact snapshot; if the person changes their data they buy again.
  let snapshot: string | null = /^[qs]:[a-z0-9]{6,40}$/.test(String(body.snapshot || "")) ? String(body.snapshot) : null;
  if (kind === "career") {
    careerId = String(body.careerId || "");
    if (!/^[a-z0-9-]{1,80}$/.test(careerId)) return json({ error: "bad request" }, 400);
    scope = body.scope === "me" ? "me" : "general";
    if (scope === "general") snapshot = null; // the general guide does not depend on the person's answers
  }

  // never take a payment that could not unlock anything: the full report and the personal report need a snapshot
  if ((kind === "full" || scope === "me") && !snapshot) return json({ error: "bad request" }, 400);

  const db = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

  // Rate limit: at most MAX_ORDERS_PER_HOUR new orders per person per hour.
  const since = new Date(Date.now() - 3600_000).toISOString();
  const { count: recent } = await db.from("purchases").select("id", { count: "exact", head: true }).eq("user_id", user.id).gte("created_at", since);
  if ((recent ?? 0) >= MAX_ORDERS_PER_HOUR) return json({ error: "too many attempts, please try again in a while" }, 429);

  const { data: owned } = await db.from("purchases").select("kind,career_id,scope,snapshot").eq("user_id", user.id).eq("status", "paid");
  type P = { kind: string; career_id: string | null; scope: string | null; snapshot: string | null };
  const has = (owned || []).some((p: P) => {
    if (kind === "full") return p.kind === "full" && !!snapshot && p.snapshot === snapshot;
    if (p.kind !== "career" || p.career_id !== careerId) return false;
    // a personal report purchase also covers the general guide for that career; a general guide does not cover the personal report
    return scope === "general" ? true : p.scope === "me" && !!snapshot && p.snapshot === snapshot;
  });
  if (has) return json({ already: true });

  const amount = PRICES[kind];
  const r = await fetch("https://api.razorpay.com/v1/orders", {
    method: "POST",
    headers: { Authorization: "Basic " + btoa(`${keyId}:${secret}`), "Content-Type": "application/json" },
    body: JSON.stringify({ amount, currency: "INR", receipt: `p4_${Date.now()}`.slice(0, 40), notes: { user_id: user.id, kind, career_id: careerId || "", scope: scope || "", snapshot: snapshot || "", age_declaration: body.ageDecl === "minor_with_guardian" ? "minor_with_guardian" : "adult" } }),
  });
  if (!r.ok) return json({ error: "could not start the payment" }, 502);
  const order = await r.json();
  const { error } = await db.from("purchases").insert({ user_id: user.id, kind, career_id: careerId, amount_paise: amount, currency: "INR", razorpay_order_id: order.id, status: "created", scope, snapshot });
  if (error) return json({ error: "could not start the payment" }, 500);
  return json({ orderId: order.id, amount, currency: "INR", keyId });
});
