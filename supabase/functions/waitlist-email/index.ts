import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

// Sends the "thanks for joining the waitlist" email. It only ever emails an address that is already on the
// learnership_waitlist table, and only once per row, so it cannot be used to mail arbitrary people.
// Secrets needed (Supabase > Edge Functions > Secrets): RESEND_API_KEY, and optionally WAITLIST_FROM.
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...cors, "Content-Type": "application/json" } });
const esc = (t: string) => t.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "method" }, 405);
  let body: { email?: string; track?: string } = {};
  try { body = await req.json(); } catch { return json({ error: "bad request" }, 400); }
  const email = String(body.email || "").trim().toLowerCase();
  const track = String(body.track || "").trim();
  if (!email || !track) return json({ error: "bad request" }, 400);

  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: row } = await db.from("learnership_waitlist").select("id,name,email,track,duration,email_sent_at,created_at")
    .ilike("email", email).eq("track", track).maybeSingle();
  if (!row) return json({ error: "not on the waitlist" }, 404);
  if (row.email_sent_at) return json({ sent: true, already: true });
  // only for a sign-up made in the last 15 minutes, so this cannot be used to re-trigger mail later
  if (Date.now() - new Date(row.created_at).getTime() > 15 * 60 * 1000) return json({ sent: false, reason: "too old" });

  const key = Deno.env.get("RESEND_API_KEY");
  if (!key) {
    await db.from("learnership_waitlist").update({ email_error: "email service not set up" }).eq("id", row.id);
    return json({ sent: false, reason: "not configured" });
  }
  const from = Deno.env.get("WAITLIST_FROM") || "Plan4it <hello@plan4it.co>";
  const first = esc(String(row.name || "").trim().split(/\s+/)[0] || "there");
  const html = `<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#0f172a;max-width:520px">
<p>Hi ${first},</p>
<p>Thank you for joining the Plan4it Learnership waitlist.</p>
<p>We will update you with the information soon via email.</p>
<p>Thanks,<br>Plan4it</p>
<p style="font-size:12px;color:#64748b">Joining the waitlist is free and does not commit you to anything. You are receiving this because this email address was used to join the waitlist at plan4it.co.</p></div>`;
  const text = `Hi ${String(row.name || "").trim().split(/\s+/)[0] || "there"},\n\nThank you for joining the Plan4it Learnership waitlist.\n\nWe will update you with the information soon via email.\n\nThanks,\nPlan4it\n\nJoining the waitlist is free and does not commit you to anything.`;
  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from, to: [row.email], subject: "Thanks for joining the Plan4it waitlist", html, text }),
    });
    if (!r.ok) {
      const msg = (await r.text()).slice(0, 300);
      await db.from("learnership_waitlist").update({ email_error: `send failed (${r.status}): ${msg}` }).eq("id", row.id);
      return json({ sent: false, reason: "send failed" });
    }
    await db.from("learnership_waitlist").update({ email_sent_at: new Date().toISOString(), email_error: null }).eq("id", row.id);
    return json({ sent: true });
  } catch (e) {
    await db.from("learnership_waitlist").update({ email_error: `send failed: ${String((e as Error).message || e).slice(0, 200)}` }).eq("id", row.id);
    return json({ sent: false, reason: "send failed" });
  }
});
