# AntiDeepfake AI launch readiness

This checklist turns the current product into a production deployment for
`antideepfakeai.com`.

## Recommended production topology

- `https://antideepfakeai.com` and `https://www.antideepfakeai.com` — static
  frontend from `frontend/` on Cloudflare Pages, Vercel, Netlify, or S3 +
  CloudFront.
- `https://api.antideepfakeai.com` — FastAPI backend from `backend/Dockerfile`
  on Render, Fly.io, ECS, Railway, or a hardened VPS.
- PostgreSQL — managed database for users, scans, and history.
- Redis — optional queue backend if async/background processing is enabled.
- Object storage — recommended for uploaded media and generated reports once
  production volume grows beyond local disk.

## DNS records

Point your domain at the frontend host:

```text
@      A / ALIAS / CNAME  -> frontend host target
www    CNAME              -> frontend host target
api    CNAME              -> backend host target
```

Use your hosting provider's exact DNS target values. Enable HTTPS certificates
for all three hostnames.

## Required environment variables

Backend:

```bash
ADF_JWT_SECRET=<long-random-secret>
ADF_CORS_ORIGINS=https://antideepfakeai.com,https://www.antideepfakeai.com
DATABASE_URL=postgresql+psycopg2://...
REDIS_URL=redis://...
ADF_MODEL_DIR=/app/backend/weights
ADF_DATA_DIR=/data
ADF_STRICT_MODELS=1
ADF_DEVICE=cpu
```

Optional premium detector consensus:

```bash
ADF_ENABLE_PAID_APIS=1
ADF_PREMIUM_DETECTORS='[{"name":"provider","url":"https://provider.example/api/detect","api_key_env":"PROVIDER_API_KEY"}]'
PROVIDER_API_KEY=<provider-secret>
```

Frontend:

- Set the web app API base to `https://api.antideepfakeai.com` in
  `frontend/app/js/app.js`, or run in the browser console after deployment:
  `ADF.setApiBase("https://api.antideepfakeai.com")`.
- Replace every `YOURPRODUCTID` Digistore24 checkout URL in
  `frontend/index.html`.

## Model and accuracy readiness

- Obtain licensed FaceForensics++ weights and any commercial detector keys you
  want to use.
- Run `python scripts/download_models.py --url-face "<licensed-url>"` during
  deployment or bake weights into the backend image.
- Keep `ADF_STRICT_MODELS=1` in production so missing model files fail loudly
  instead of silently falling back to heuristics.
- Validate against a small gold set of known-real and known-fake media before
  publishing accuracy claims.

## SaaS/product hardening

- Replace legal templates with lawyer-reviewed Privacy, Terms, and Refund pages.
- Add a production email sender for account verification and password recovery.
- Add rate limits and abuse protection on `/api/auth/*` and `/api/detect`.
- Add server-side retention jobs for uploaded media and reports.
- Add payment fulfillment: after Digistore24 purchase, redirect buyers to
  `frontend/thank-you.html` and provision an account/API key.
- Add analytics/error monitoring such as Sentry plus uptime monitoring for
  `api.antideepfakeai.com/api/health`.

## Publish sequence

1. Deploy backend and confirm `https://api.antideepfakeai.com/api/health`.
2. Deploy frontend and set the API base to the backend URL.
3. Configure DNS and HTTPS.
4. Replace Digistore24 product links and success URL.
5. Run a real signed-in scan through the dashboard.
6. Test JSON/PDF report downloads.
7. Publish the Chrome extension after setting the default API URL.
