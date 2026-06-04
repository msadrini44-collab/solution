# AntiDeepfake AI

**Detect deepfakes instantly with 8 core forensic layers plus optional premium-provider consensus.**

AntiDeepfake AI is a full-stack product for detecting deepfakes, face swaps, and
AI-generated images & video. It combines **8 independent core detectors** into a
calibrated ensemble verdict, can fuse optional external premium detector
providers, ships with a high-converting sales page, a product web
app, a REST API, and a Chrome extension — all containerized for one-command
deployment.

---

## Features

- **8-layer core detection engine** — face forgery, frequency analysis, liveness,
  temporal consistency, audio-visual sync, GAN fingerprinting, metadata
  forensics, and pixel forensics, fused by a weighted ensemble.
- **Premium detector consensus** — optional external provider hooks can add
  another independent signal when provider API keys are configured.
- **Images & video** — JPEG/PNG/WebP/BMP and MP4/MOV/AVI/MKV/WebM (frame-sampled).
- **FastAPI backend** with JWT + API-key auth, async scanning, and Swagger docs.
- **Evidence reports** — JSON + PDF with anomaly heatmaps and FFT spectrum plots.
- **Sales site** (Digistore24-compliant) + **product web app** + **Chrome extension**.
- **Graceful degradation** — runs end-to-end even without multi-GB model weights
  by falling back to documented heuristics; frontend works in **demo mode** with
  simulated results when the backend is offline.

---

## Architecture

```
                         ┌─────────────────────────────────────────────┐
                         │                Frontend (static)            │
                         │  Sales page · Web app · Browser extension   │
                         └───────────────┬─────────────────────────────┘
                                         │ HTTPS (JWT / X-API-Key)
                                         ▼
┌──────────────┐   enqueue    ┌────────────────────────┐    read/write   ┌────────────┐
│   Redis      │◄────────────►│   FastAPI (backend/)   │◄───────────────►│ PostgreSQL │
│ (Celery bus) │   (optional) │  /api/detect, /auth …  │   users, scans  │            │
└──────┬───────┘              └───────────┬────────────┘                 └────────────┘
       │ tasks                            │ run_pipeline()
       ▼                                  ▼
┌──────────────┐              ┌────────────────────────────────────────────────────┐
│ Celery worker│              │             Detector Ensemble (models/)            │
│ (scale-out)  │              │ face_forgery · frequency · liveness · temporal ·    │
└──────────────┘              │ audio_sync · gan_fingerprint · metadata · pixel     │
                              └───────────────────────┬────────────────────────────┘
                                                      ▼
                                       scoring.py → report_generator.py
                                     (verdict + heatmaps + JSON/PDF report)
```

---

## Tech Stack

| Layer        | Technology |
|--------------|------------|
| API          | FastAPI, Uvicorn, Pydantic |
| Detectors    | PyTorch, torchvision, facenet-pytorch (MTCNN), OpenCV, NumPy, SciPy, librosa, mediapipe, dlib |
| Reports      | matplotlib, reportlab |
| Auth         | python-jose (JWT), PBKDF2 password hashing |
| Persistence  | SQLAlchemy + PostgreSQL (SQLite for local dev) |
| Queue        | Celery + Redis (optional) |
| Frontend     | Vanilla HTML/CSS/JS (no build step) |
| Extension    | Chrome Manifest V3 |
| Infra        | Docker, docker-compose |

---

## File Structure

```
solution/
├── backend/
│   ├── main.py                 # FastAPI app: auth, detect, results, history, /docs
│   ├── pipeline.py             # Orchestrates frame sampling + all detectors
│   ├── scoring.py              # Weighted ensemble → score + verdict
│   ├── report_generator.py     # JSON/PDF reports + heatmap & spectrum plots
│   ├── config.py               # Env-driven configuration
│   ├── auth.py                 # JWT, password hashing, API keys
│   ├── database.py             # SQLAlchemy models (User, Scan)
│   ├── schemas.py              # Pydantic request/response models
│   ├── tasks.py                # Optional Celery task definitions
│   ├── requirements.txt
│   ├── Dockerfile
│   └── models/                 # Core detectors + optional premium consensus
│       ├── base.py             # DetectorResult contract + helpers
│       ├── face_forgery.py     # 1. EfficientNet/Xception + MTCNN (FF++)
│       ├── frequency_analysis.py # 2. FFT/DCT spectral artifacts
│       ├── liveness.py         # 3. Eye-blink / micro-expression / texture
│       ├── temporal_analysis.py# 4. Optical-flow video consistency
│       ├── audio_sync.py       # 5. Lip-sync + AI-voice detection
│       ├── gan_fingerprint.py  # 6. GAN/diffusion source identification
│       ├── metadata_forensics.py # 7. EXIF / quantization / editing traces
│       └── pixel_forensics.py  # 8. ELA / noise / clone / lighting
├── frontend/
│   ├── index.html              # Sales page (Digistore24-ready)
│   ├── thank-you.html          # Post-purchase quick-start
│   ├── privacy-policy.html · terms.html · refund-policy.html
│   ├── assets/css/style.css · assets/js/main.js
│   └── app/                    # Product web app
│       ├── index.html          # Dashboard
│       ├── scanner.html        # Drag & drop upload
│       ├── results.html        # Gauge + method breakdown + heatmaps
│       ├── api-docs.html        # API reference w/ curl & Python examples
│       └── css/app.css · js/app.js
├── extension/                  # Chrome extension (Manifest V3)
│   ├── manifest.json · background.js · content.js
│   ├── popup.html · popup.js · icons/
├── scripts/
│   └── download_models.py      # Fetch/prepare pretrained weights
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Setup

### Option A — Docker (recommended)

```bash
cp .env.example .env            # optional: edit secrets
docker-compose up --build
```

- API:        http://localhost:8000
- Swagger UI: http://localhost:8000/docs

Then serve the static frontend (any static server), e.g.:

```bash
cd frontend && python -m http.server 5500
# open http://localhost:5500/index.html  (sales page)
# open http://localhost:5500/app/index.html  (web app)
```

### Option B — Local Python (no Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ..
uvicorn backend.main:app --reload      # http://localhost:8000/docs
```

> The full `requirements.txt` includes heavy ML libraries (torch, mediapipe,
> dlib). For a lightweight run that still works end-to-end on images, you only
> need: `fastapi uvicorn python-multipart "pydantic[email]" python-jose numpy
> scipy Pillow opencv-python-headless sqlalchemy matplotlib`. Detectors that
> need the heavy libs automatically fall back to heuristics.

---

## Pretrained Model Weights

Detectors that use neural networks (`face_forgery`, `gan_fingerprint`) load
weights from `backend/weights/`. To prepare them:

```bash
# Generate runnable placeholder checkpoints (demo):
python scripts/download_models.py

# Or download real FaceForensics++ weights you have access to:
python scripts/download_models.py --url-face "https://your-mirror/ffpp.pth"
#   (FF++ is gated — accept the license at
#    https://github.com/ondyari/FaceForensics first.)
```

If no weights are present, the detectors use documented heuristic fallbacks and
mark their results as `degraded`, so the pipeline still runs end-to-end. Set
`ADF_STRICT_MODELS=1` to require real weights instead.

### Optional premium detector providers

The core engine is self-hosted. To add paid external detector signals, set:

```bash
ADF_ENABLE_PAID_APIS=1
ADF_PREMIUM_DETECTORS='[{"name":"provider","url":"https://provider.example/api/detect","api_key_env":"PROVIDER_API_KEY"}]'
PROVIDER_API_KEY=...
```

Each provider must accept a `multipart/form-data` upload under the `file` field
and return JSON with one of `fake_probability`, `deepfake_probability`,
`synthetic_probability`, `score`, or `verdict`. Provider scores are combined as
the optional `premium_consensus` detector.

---

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Create account → JWT + API key |
| POST | `/api/auth/login` | Log in → JWT + API key |
| POST | `/api/detect` | Upload image/video (`?sync=true` for inline result) |
| GET  | `/api/results/{scan_id}` | Fetch scan results |
| GET  | `/api/history` | Scan history (auth required) |
| GET  | `/api/health` | Health check |
| GET  | `/docs` | Interactive Swagger UI |

```bash
curl -X POST "http://localhost:8000/api/detect?sync=true" \
  -H "X-API-Key: adf_your_key" \
  -F "file=@photo.jpg"
```

Full reference with Python examples lives in `frontend/app/api-docs.html`.

---

## Browser Extension

1. Open `chrome://extensions`, enable **Developer mode**.
2. Click **Load unpacked** and select the `extension/` folder.
3. Open the popup, set your **API Base URL** and **API key**.
4. Right-click any image on the web → **Check for deepfake**.

---

## Connecting Digistore24

1. Create your product in Digistore24 and copy its **product ID**.
2. The live checkout link is configured as
   `https://www.checkout-ds24.com/product/693637`.
3. Set the buyer **thank-you / success URL** in Digistore24 to your hosted
   `frontend/thank-you.html`.
4. Replace the placeholder **trust/footer badges** with the official Digistore24
   badge assets.
5. The included **Refund Policy** is aligned with Digistore24's 60-day
   money-back guarantee.

---

## Deployment

- **Vercel frontend**: `vercel.json` builds `frontend/` into `dist/`; connect
  the repo with root directory set to the repository root and output directory
  set to `dist`.
- **Fly.io backend**: the root `Dockerfile` + `fly.toml` deploy
  `antideepfakeai`, using the lightweight Fly requirements profile. Set
  `ADF_JWT_SECRET` as a Fly secret and add `FLY_API_TOKEN` to GitHub Actions for
  automatic deploys from `main`.
- **Other backend hosts**: deploy the `backend/Dockerfile` image (or the whole
  `docker-compose.yml`) to any container host. Provide `DATABASE_URL`,
  `REDIS_URL`, `ADF_JWT_SECRET`, and production `ADF_CORS_ORIGINS` via env vars.
- **Frontend API base**: when hosted on `antideepfakeai.com`, the app defaults
  to `https://api.antideepfakeai.com`; otherwise set it with
  `ADF.setApiBase("https://api.yourdomain.com")`.
- **Extension**: zip the `extension/` folder and publish to the Chrome Web Store.
- **Launch checklist**: see `docs/launch-readiness.md` for DNS, SSL,
  Digistore24, environment variables, and production hardening for
  `antideepfakeai.com`.

---

## Disclaimer

Deepfake detection is **probabilistic**. AntiDeepfake AI provides confidence
scores and forensic indicators — not legal proof. Always review the full
per-detector breakdown and use results as one signal among others.
