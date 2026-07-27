/**
 * Supabase Edge Function: notify-backend
 *
 * Triggered by a Supabase Database Webhook when a row is inserted/updated
 * in leads_cache with sync_status='pending' and origin='mobile'.
 *
 * Sends the record to the Flask backend POST /api/v1/sync/webhook
 * so the backend can write it into MySQL.
 *
 * Deploy:
 *   supabase functions deploy notify-backend
 *
 * Set secrets:
 *   supabase secrets set BACKEND_URL=https://your-backend.com
 *   supabase secrets set BACKEND_WEBHOOK_SECRET=your-shared-secret
 *   supabase secrets set BACKEND_SERVICE_JWT=<service-account-JWT>
 */

import { serve } from 'https://deno.land/std@0.168.0/http/server.ts';
import { createHmac } from 'https://deno.land/std@0.168.0/crypto/mod.ts';

const BACKEND_URL    = Deno.env.get('BACKEND_URL') ?? '';
const WEBHOOK_SECRET = Deno.env.get('BACKEND_WEBHOOK_SECRET') ?? '';
const SERVICE_JWT    = Deno.env.get('BACKEND_SERVICE_JWT') ?? '';

serve(async (req: Request) => {
  try {
    const payload = await req.json();

    const record: Record<string, unknown> = payload?.record ?? {};
    const origin      = record?.origin      as string | undefined;
    const syncStatus  = record?.sync_status as string | undefined;

    // Only forward mobile-originated pending records
    if (origin !== 'mobile' || syncStatus !== 'pending') {
      return new Response(JSON.stringify({ message: 'Skipped', origin, syncStatus }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      });
    }

    const body = JSON.stringify({
      type:   payload?.type ?? 'INSERT',
      table:  payload?.table ?? 'leads_cache',
      record,
      old_record: payload?.old_record ?? {},
    });

    // Compute HMAC-SHA256 signature
    let signature = '';
    if (WEBHOOK_SECRET) {
      const key = await crypto.subtle.importKey(
        'raw', new TextEncoder().encode(WEBHOOK_SECRET),
        { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
      );
      const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
      signature = 'sha256=' + Array.from(new Uint8Array(sig))
        .map((b) => b.toString(16).padStart(2, '0')).join('');
    }

    const response = await fetch(`${BACKEND_URL}/api/v1/sync/webhook`, {
      method:  'POST',
      headers: {
        'Content-Type':         'application/json',
        'Authorization':        `Bearer ${SERVICE_JWT}`,
        'x-supabase-signature': signature,
      },
      body,
    });

    const result = await response.json();
    return new Response(JSON.stringify({ forwarded: true, backend_status: response.status, result }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    });

  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500, headers: { 'Content-Type': 'application/json' },
    });
  }
});
