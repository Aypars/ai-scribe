# AI-SCRIBE

Toplantı kaydını yazıya çevirir, özet / karar / görev çıkarır, tutanak indirir.

Kayıt yükle → WhisperX transkript → sen **Analiz yap** → özet, kararlar, aksiyonlar. Transkript hazırsa **Sor** ile bu kayda soru sorulur. Analiz otomatik başlamaz.

## Ne var

- Hesap: kayıt, giriş, şifre sıfırlama (SMTP), hesap ayarları
- Toplantı: ses (mp3 / wav / m4a) veya video (mp4 / webm / mov); yüklerken **Türkçe / English**
- Transkript + oynatıcı, konuşmacı eşleme, satır düzeltme
- Analiz: Çerçeve / Gündem / Sonuç (EN: Context / Agenda / Outcome), kararlar, aksiyonlar
- Görev panosu, kişiler, dashboard takvim
- Dışa aktarma: PDF, Word, Markdown — dil toplantı diline göre
- Sor: yalnız bu transkriptten yanıt; damgaya basınca sese atlar

Monorepo: `frontend/` (Next.js) + `backend/` (FastAPI) + PostgreSQL.

## Yerelde çalıştırma

Şu an geliştirme böyle: kendi makinede üç parça ayrı çalışır.

### 1. PostgreSQL

`ai-scribe` adında veritabanı oluştur. `backend/.env` içindeki `DATABASE_URL` ile aynı olsun.

### 2. Backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

`.env` içinde doldur:

| Değişken | Ne |
|----------|----|
| `DATABASE_URL` | Postgres |
| `SECRET_KEY` | JWT, rastgele uzun string |
| `GEMINI_API_KEY` | Analiz ve Sor (yoksa `OPENAI_API_KEY`) |
| `HF_TOKEN` | WhisperX diarization (konuşmacı ayırma) |
| `FRONTEND_URL` | Şifre sıfırlama linki, varsayılan `http://localhost:3000` |
| `SMTP_*` | Şifre sıfırlama maili; boşsa link log’a düşer |

```bash
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload --reload-dir app
```

API: http://localhost:8000/docs — şema açılışta `ensure_schema` ile tamamlanır.

Transkript için makinede **ffmpeg** ve **WhisperX** gerekir (ayrı `whisperx-env`). Video yüklemede ffmpeg ses çıkarır. Analiz çalışırken `backend/app` dosyasını kaydetme: `--reload` işi öldürür.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Uygulama: http://localhost:3000  
İsteğe bağlı: `NEXT_PUBLIC_API_URL` (varsayılan `http://localhost:8000`).

## Docker ne, ne zaman

Docker, uygulamayı “bu makinede Python / Node / Postgres kur” yerine **kutuya koyup aynı şekilde çalıştırır**.

Şu an sende üç ayrı şey var: Postgres servisi, uvicorn, `npm run dev`. Hepsi senin Windows’una bağlı (venv, whisperx-env yolu, portlar).

Docker’da tipik kutu üç servis olur:

1. **postgres** — veritabanı
2. **backend** — FastAPI + (ileride) ffmpeg / Whisper ağırlığı
3. **frontend** — Next.js production build

`docker compose up` deyince üçü birden ayağa kalkar. Yeni PC, sunucu, jüri makinesi: aynı komut. “Bende çalışıyor sende yok” azalır.

**Ne işe yaramaz:** kod yazmayı hızlandırmaz, bug da düzeltmez. Uygulama bitmiş ve yerelde sağlamsa **dağıtım / demo** içindir.

**Ne zaman:** küçük işler ve bariz bug’lar kapanınca. WhisperX GPU ve büyük modeller kutuyu şişirir; o yüzden Docker’ı sona bırakmak doğru. Bu repoda henüz `Dockerfile` / `compose` yok.

Kutu gelince `.env` yine gerekir (API anahtarları kutunun içine gömülmez). Ses dosyaları volume ile `uploads/`’a yazılır.

## Repo

```text
ai-scribe/
├── backend/          FastAPI, şema, uploads
├── frontend/         Next.js
├── docs/week1/       İlk analiz notları
└── README.md
```

`downloads/` ve `backend/.env` gitmez.
