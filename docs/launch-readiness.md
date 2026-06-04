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

## Vercel setup

This repo includes `vercel.json` and a root `package.json` build script. In the
Vercel project:

- Framework preset: Other
- Root directory: repository root
- Build command: `npm run build`
- Output directory: `dist`
- Production domains: `antideepfakeai.com`, `www.antideepfakeai.com`

The build copies `frontend/` into `dist/`, so the marketing site remains at `/`
and the dashboard remains at `/app/`.

## Fly.io setup

This repo includes a root `Dockerfile`, `fly.toml`, `.dockerignore`, and
`backend/requirements-fly.txt` for a deployable API at
`https://api.antideepfakeai.com`. The root Dockerfile is intentional: Fly's
GitHub integration auto-detects a root Dockerfile before it reads nested backend
Dockerfiles.

One-time Fly.io setup:

```bash
flyctl apps create antideepfakeai
flyctl volumes create adf_data --app antideepfakeai --region iad --size 10
flyctl secrets set --app antideepfakeai \
  ADF_JWT_SECRET='<long-random-secret>' \
  ADF_CORS_ORIGINS='https://antideepfakeai.com,https://www.antideepfakeai.com'
flyctl certs add api.antideepfakeai.com --app antideepfakeai
```

If you have not created the app yet, run `flyctl apps create antideepfakeai`
first. If you created a Fly app with a different name, update the `app =` value
in `fly.toml` and replace `antideepfakeai` in the commands above.

Then add `FLY_API_TOKEN` as a GitHub repository secret. The included
`.github/workflows/fly-deploy.yml` deploys the backend on pushes to `main` and
can also be run manually from GitHub Actions.

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
ADF_TRIAL_FREE_SCANS_PER_IP=1
```

Optional premium detector consensus:

```bash
ADF_ENABLE_PAID_APIS=1
ADF_PREMIUM_DETECTORS='[{"name":"provider","url":"https://provider.example/api/detect","api_key_env":"PROVIDER_API_KEY"}]'
PROVIDER_API_KEY=<provider-secret>
```

Frontend:

- The marketing site and app automatically use `https://api.antideepfakeai.com`
  when loaded from `antideepfakeai.com`.
- Digistore24 checkout is configured as
  `https://www.checkout-ds24.com/product/693637`.

## Model and accuracy readiness

- Obtain licensed FaceForensics++ / Xception-style face-forgery weights,
  generator-fingerprint weights, and any commercial detector keys you want to
  use. This is required before making strong production accuracy claims.
- Run `python scripts/download_models.py --url-face "<licensed-url>"` during
  deployment or bake weights into the backend image.
- Keep `ADF_STRICT_MODELS=1` in production so missing model files fail loudly
  instead of silently falling back to heuristics.
- Validate against a gold set of known-real and known-fake images/video before
  publishing accuracy claims. No detector should be marketed as never missing;
  position the system as high-confidence screening plus human review.

## SaaS/product hardening

- Have counsel review the Privacy, Terms, Refund, About, and Contact pages.
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
