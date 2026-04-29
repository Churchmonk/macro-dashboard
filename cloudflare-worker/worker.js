/**
 * DS Macro Jungle — 1-click Refresh Worker
 * ==========================================
 * Cloudflare Worker가 대시보드의 "즉시 실행" 버튼 요청을 받아
 * Clerk JWT 검증 후 GitHub Actions workflow_dispatch를 트리거합니다.
 *
 * 환경변수 (Cloudflare Worker Settings → Variables):
 *   GITHUB_PAT          — fine-grained PAT (Repository: Churchmonk/macro-dashboard, Permission: Actions: Read+Write)
 *   CLERK_JWKS_URL      — https://settling-albacore-3.clerk.accounts.dev/.well-known/jwks.json
 *   ALLOWED_ORIGIN      — https://churchmonk.github.io   (CORS)
 *   ADMIN_EMAIL         — (선택) 특정 이메일만 허용. 빈 값이면 모든 인증된 사용자 허용
 *
 * 엔드포인트: POST /
 *   Headers: Authorization: Bearer <Clerk JWT>
 *   Body:    { "mode": "daily" | "weekly" | "monthly" }
 *   Resp:    { "success": true, "mode": ..., "triggered_by": ..., "timestamp": ... }
 */

const GITHUB_OWNER = 'Churchmonk';
const GITHUB_REPO = 'macro-dashboard';
const ALLOWED_MODES = ['daily', 'weekly', 'monthly'];

export default {
  async fetch(request, env) {
    const corsHeaders = {
      'Access-Control-Allow-Origin': env.ALLOWED_ORIGIN || '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      'Access-Control-Max-Age': '86400',
    };

    // Preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // GET: 헬스체크
    if (request.method === 'GET') {
      return jsonResponse(
        { service: 'macro-dashboard-refresh', status: 'ok', allowed_modes: ALLOWED_MODES },
        200, corsHeaders
      );
    }

    if (request.method !== 'POST') {
      return jsonResponse({ error: 'Method not allowed' }, 405, corsHeaders);
    }

    // 1. JWT 검증 (Clerk)
    const auth = request.headers.get('Authorization') || '';
    const token = auth.replace(/^Bearer\s+/i, '');
    if (!token) {
      return jsonResponse({ error: 'Missing token' }, 401, corsHeaders);
    }

    let payload;
    try {
      payload = await verifyClerkJwt(token, env.CLERK_JWKS_URL);
    } catch (e) {
      return jsonResponse({ error: 'Invalid token: ' + e.message }, 401, corsHeaders);
    }

    // 2. (선택) Admin email 화이트리스트
    if (env.ADMIN_EMAIL) {
      const allowedEmails = env.ADMIN_EMAIL.toLowerCase().split(',').map(s => s.trim());
      const userEmail = (payload.email || '').toLowerCase();
      if (!allowedEmails.includes(userEmail)) {
        return jsonResponse({ error: 'Forbidden — email not in allowlist' }, 403, corsHeaders);
      }
    }

    // 3. 요청 모드
    let body = {};
    try { body = await request.json(); } catch (_) {}
    const mode = body.mode;
    if (!ALLOWED_MODES.includes(mode)) {
      return jsonResponse({ error: 'Invalid mode. Use one of: ' + ALLOWED_MODES.join(', ') }, 400, corsHeaders);
    }

    // 4. GitHub Actions workflow_dispatch
    const ghUrl = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${mode}.yml/dispatches`;
    const ghResp = await fetch(ghUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.GITHUB_PAT}`,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'macro-dashboard-worker/1.0',
      },
      body: JSON.stringify({ ref: 'main' }),
    });

    if (!ghResp.ok) {
      const errText = await ghResp.text();
      return jsonResponse(
        { error: 'GitHub API failed', status: ghResp.status, detail: errText.slice(0, 500) },
        502, corsHeaders
      );
    }

    return jsonResponse({
      success: true,
      mode,
      triggered_by: payload.email || payload.sub || 'unknown',
      timestamp: new Date().toISOString(),
    }, 200, corsHeaders);
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function jsonResponse(obj, status, extra) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json', ...(extra || {}) },
  });
}

// Clerk JWT 검증 (RS256 / JWKS)
async function verifyClerkJwt(token, jwksUrl) {
  if (!jwksUrl) throw new Error('CLERK_JWKS_URL not configured');

  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('Malformed JWT');

  const [headerB64, payloadB64, sigB64] = parts;
  const header = JSON.parse(b64UrlDecodeText(headerB64));
  const payload = JSON.parse(b64UrlDecodeText(payloadB64));

  // 기본 클레임 검증
  const now = Math.floor(Date.now() / 1000);
  if (payload.exp && payload.exp < now) throw new Error('Token expired');
  if (payload.nbf && payload.nbf > now + 30) throw new Error('Token not yet valid');

  // JWKS fetch (간단한 캐시)
  const jwks = await fetchJwks(jwksUrl);
  const jwk = jwks.keys.find(k => k.kid === header.kid);
  if (!jwk) throw new Error('Key not found in JWKS');

  // 서명 검증
  const cryptoKey = await crypto.subtle.importKey(
    'jwk',
    { ...jwk, ext: true },
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify']
  );

  const signedData = new TextEncoder().encode(headerB64 + '.' + payloadB64);
  const signature = b64UrlDecodeBytes(sigB64);
  const valid = await crypto.subtle.verify(
    'RSASSA-PKCS1-v1_5', cryptoKey, signature, signedData
  );
  if (!valid) throw new Error('Invalid signature');

  return payload;
}

let _jwksCache = { url: null, data: null, fetchedAt: 0 };
async function fetchJwks(url) {
  const now = Date.now();
  if (_jwksCache.url === url && _jwksCache.data && (now - _jwksCache.fetchedAt) < 60 * 60 * 1000) {
    return _jwksCache.data;
  }
  const resp = await fetch(url);
  if (!resp.ok) throw new Error('JWKS fetch failed: ' + resp.status);
  const data = await resp.json();
  _jwksCache = { url, data, fetchedAt: now };
  return data;
}

function b64UrlDecodeText(b64) {
  const std = b64.replace(/-/g, '+').replace(/_/g, '/').padEnd(b64.length + (4 - b64.length % 4) % 4, '=');
  return atob(std);
}

function b64UrlDecodeBytes(b64) {
  const text = b64UrlDecodeText(b64);
  const buf = new Uint8Array(text.length);
  for (let i = 0; i < text.length; i++) buf[i] = text.charCodeAt(i);
  return buf.buffer;
}
