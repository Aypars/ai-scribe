# AI-SCRIBE

Ses analizli toplantı asistanı ve iş takip sistemi.

Toplantı ses kayıtlarını (`.mp3`, `.wav`, `.m4a`) yükleyip Whisper ile metne çevirir; GPT-4o-mini ile özet, kararlar ve aksiyon maddeleri üretir; aksiyonları görev kartlarına dönüştürür.

## Teknoloji

| Katman | Stack |
|--------|--------|
| Frontend | Next.js + React + Tailwind CSS |
| Backend | Python FastAPI |
| DB | PostgreSQL |
| Depolama | Yerel (`backend/uploads/`) |
| AI | OpenAI Whisper + GPT-4o-mini |

Monorepo: `frontend/` + `backend/`.

## Hafta 1 teslimatı (analiz)

Detaylar `docs/week1/` altında:

1. [Teknoloji ve mimari](docs/week1/01-technology-and-architecture.md)
2. [Mockup’lar](docs/week1/02-mockups.md)
3. [Hafta 1-2 raporu (PDF)](docs/week1/week1.pdf)

## Repo yapısı

```text
ai-scribe/
├── docs/week1/          # Analiz & tasarım
├── frontend/            # Next.js (Hafta 2+)
├── backend/             # FastAPI (Hafta 2+)
├── .gitignore
└── README.md
```

## Kurulum (Hafta 2 iskeleti)

### Backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
copy .env.example .env            # OPENAI_API_KEY ve DATABASE_URL doldur
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Uygulama: http://localhost:3000

### PostgreSQL

`ai_scribe` adında bir veritabanı oluştur; `backend/.env` içindeki `DATABASE_URL` ile eşleştir.

## Yol haritası (özet)

| Hafta | Odak |
|-------|------|
| 1 | Analiz, mockup, şema, API ✅ |
| 2 | Geliştirme ortamı, repo, iskelet |
| 3 | UI + CRUD |
| 4 | Whisper / GPT entegrasyonu |
| 5 | Dashboard + görev panosu |
| 6 | Export / raporlama |
| 7 | Test, bugfix, performans |
| 8 | Deploy + demo |
