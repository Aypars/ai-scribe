# AI-SCRIBE

Toplantı ses ve video kayıtlarından konuşmacı ayrımlı transkript üreten, kullanıcı onayıyla özet / karar / aksiyon çıkaran ve aksiyonları görev olarak takip eden yerel asistan.

İstemci (`frontend/`, Next.js), REST API (`backend/`, FastAPI) ve PostgreSQL ayrı süreçler olarak çalışır.

---

## Kapsam

| Yetenek | Davranış |
|---------|----------|
| Yazıya çevirme | Yükleme sonrası WhisperX arka planda çalışır. Çıktı: zaman damgalı satırlar, konuşmacı etiketleri. |
| Konuşmacı | Diarization etiketleri (`Konuşmacı A` …). Beyan edilen katılımcı adlarıyla eşleme denenir; satır veya etiket kullanıcı tarafından düzeltilir. Ardışık satırlar birleştirilebilir. |
| Analiz | Otomatik başlamaz. Transkript hazırken `Analiz yap`: çerçeve / gündem / sonuç özeti, kararlar, aksiyon önerileri. |
| Soru | Yanıt yalnızca o toplantının transkriptine dayanır. Alıntılar kayıt üzerinde seek eder. |
| İş takibi | Aksiyon öneridir. Görev panosuna alınca teslim tarihi zorunludur. Kişi dizini ve takvim ayrı yüzeylerdir. |
| Dışa aktarma | PDF, Word ve Markdown tarayıcıda üretilir. |

Uygulama yüzeyleri: `/` (dashboard), `/meetings`, `/meetings/new`, `/meetings/[id]`, `/tasks`, `/people`, `/settings`.

Konuşmacı etiketini değiştirmek `people` kaydının adını değiştirmez. `people` adını değiştirmek bağlı görev, aksiyon ve transkript etiketlerine yansır.

---

## Mimari

İstemci `http://localhost:3000` üzerinden JSON ve JWT ile `http://localhost:8000/api/v1` konuşur. API meta veriyi PostgreSQL’e, medyayı `backend/uploads/{user_id}/` altına yazar (en fazla 500 MB). Yazıya çevirme yerel WhisperX ve ffmpeg ile; özet, karar, aksiyon ve soru Gemini (yoksa OpenAI) ile yapılır. CORS: `http://localhost:3000` ve `http://127.0.0.1:3000`.

Toplantı durumu: `uploaded` → `transcribed` → `analyzed`. Transkripsiyon hatası `failed`. Konuşmacı etiketi kişi kaydı oluşturmaz; kişi, Kişiler ekranından veya görev atamasından doğar.

Kimlik: HS256 JWT (`sub` = `user_id`, 7 gün). Kayıt, giriş ve şifre sıfırlama dışındaki uçlar `Authorization: Bearer` ister. Kayıtlar kullanıcıya aittir.

```mermaid
flowchart LR
  subgraph istemci ["İstemci — Next.js :3000"]
    UI[Sayfalar]
    EXP[PDF / Word / MD]
  end

  subgraph api ["API — FastAPI :8000"]
    R["/api/v1"]
    SVC[Servisler]
    REPO[Repository]
  end

  PG[(PostgreSQL)]
  UP[uploads/]
  WX[WhisperX + ffmpeg]
  LLM[Gemini / OpenAI]

  UI -->|JSON + JWT| R
  UI -->|ses / video| R
  EXP -.-> UI
  R --> SVC
  SVC --> REPO
  REPO --> PG
  SVC --> UP
  SVC --> WX
  SVC --> LLM
```

```mermaid
sequenceDiagram
  participant U as Kullanıcı
  participant FE as İstemci
  participant API as FastAPI
  participant WX as WhisperX
  participant DB as PostgreSQL
  participant LLM as Gemini / OpenAI

  U->>FE: Kayıt yükle
  FE->>API: POST /api/v1/meetings
  API->>DB: status = uploaded
  API->>WX: transkripsiyon (arka plan)
  WX-->>API: satırlar
  API->>DB: status = transcribed
  U->>FE: Analiz yap
  FE->>API: POST /meetings/{id}/analyze
  API->>LLM: özet / karar / aksiyon
  API->>DB: status = analyzed
```

Uzun işler HTTP yanıtını bekletmez. İstemci `GET /api/v1/meetings/{id}` ile `status` ve `transcription` alanını izler.

### Backend katmanları (`backend/app`)

| Katman | Sorumluluk |
|--------|------------|
| `api/v1/` | HTTP uçları |
| `schemas/` | İstek / yanıt doğrulama |
| `models/` | SQLAlchemy tabloları |
| `repositories/` | Kalıcılık |
| `services/` | Transkripsiyon, analiz, depolama, e-posta |
| `core/` | Ayarlar, bağlantı, JWT |

`services`: `storage.py`, `transcription.py`, `speakers.py`, `analysis.py`, `analysis_prompts.py`, `llm.py`, `meeting_jobs.py`, `ask.py`, `mail.py`, `meeting_lang.py`.

---

## Veri modeli

Şema dosyası: `backend/sql/schema.sql`.

Güçlü varlıklar: `users`, `meetings`, `people`. Zayıf varlıkların birincil anahtarı sahibiyle tanımlıdır: `transcripts (meeting_id, seq)`, `decisions` / `actions (meeting_id, seq)`, `tasks (meeting_id, action_seq)`. `analyses` toplantı ile 1:1 (`PK = meeting_id`).

Çoğu yabancı anahtar `ON DELETE CASCADE`. `actions.assignee_id` ve `tasks.assignee_id` kişi silinince `SET NULL` olur. `decisions.source_seq` transkript satırına yabancı anahtar değildir.

| Tablo | Rol |
|-------|-----|
| `users` | Hesap; şifre bcrypt; sıfırlama jetonu hash’li |
| `meetings` | Başlık, tarih, dil, `audio_path`, `status` |
| `transcripts` | Satır metni, saniye, konuşmacı, `flags` (JSON metin) |
| `people` | Hesaba özel kişi dizini |
| `meeting_people` | Toplantı–kişi ilişkisi ve `speaker_label` |
| `analyses` | Özet |
| `decisions` | Karar metni ve transkript aralığı |
| `actions` | Analiz önerisi |
| `tasks` | Aksiyonla 1:1 görev; `in_progress` / `done` |

```mermaid
erDiagram
  users ||--o{ meetings : sahip
  users ||--o{ people : dizin
  meetings ||--o{ transcripts : satir
  meetings ||--o| analyses : ozet
  meetings ||--o{ meeting_people : katilim
  people ||--o{ meeting_people : bag
  analyses ||--o{ decisions : karar
  analyses ||--o{ actions : aksiyon
  actions ||--o| tasks : gorev
  people ||--o{ actions : sorumlu
  people ||--o{ tasks : sorumlu
```

---

## Teknoloji

Next.js 16, FastAPI, PostgreSQL 14+, JWT, WhisperX (`large-v3`), ffmpeg, Gemini veya OpenAI, istemcide `jspdf` / `docx`.

---

## Kurulum

Gerekli yazılımlar: Python 3.12+, Node.js 20+, PostgreSQL 14+, ffmpeg. WhisperX, FastAPI sanal ortamından ayrı kurulur. Konuşmacı ayırmak için Hugging Face jetonu ve pyannote modeli; özet ve soru için Gemini veya OpenAI anahtarı. `large-v3` ile yazıya çevirmede NVIDIA GPU önerilir.

Yapılandırma `backend/.env.example` dosyasından kopyalanır; değerler aşağıdaki tablodadır.

### Veritabanı

`backend/.env` içindeki `DATABASE_URL` ile aynı ad:

```sql
CREATE DATABASE "ai-scribe";
```

Boş şema (`DROP` içerir; mevcut veriyi siler):

```bash
psql -U postgres -d ai-scribe -f backend/sql/schema.sql
```

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

macOS / Linux: `source .venv/bin/activate`, `cp .env.example .env`.

Oluşan `backend/.env` içinde doldurulacak alanlar:

| Değişken | Ne zaman | Açıklama |
|----------|----------|----------|
| `DATABASE_URL` | her zaman | `postgresql+psycopg://postgres:SIFRE@localhost:5432/ai-scribe` |
| `SECRET_KEY` | her zaman | JWT imzası; örnekteki `change-me` değeri değiştirilmeli |
| `GEMINI_API_KEY` | özet, karar, soru | Yoksa `OPENAI_API_KEY` kullanılır |
| `HF_TOKEN` | konuşmacı ayırma | Hugging Face `read` jetonu. Hugging Face’te pyannote lisansları kabul edilmeli (`pyannote/speaker-diarization-3.1` ve bağlı segmentation modeli). |
| `WHISPERX_BIN` | `whisperx` PATH’te değilse | Binary’nin tam yolu |
| `FFMPEG_BIN` | `ffmpeg` PATH’te değilse | ffmpeg’in tam yolu |
| `WHISPERX_MODEL` | isteğe bağlı | Varsayılan `large-v3` |
| `GEMINI_MODEL` | isteğe bağlı | Varsayılan `gemini-3.1-flash-lite` |
| `OPENAI_MODEL` | isteğe bağlı | Varsayılan `gpt-4o-mini` |
| `FRONTEND_URL`, `CORS_ORIGINS` | isteğe bağlı | Şifre sıfırlama bağlantısının kök adresi ve CORS |
| `UPLOAD_DIR` | isteğe bağlı | Varsayılan `uploads` |
| SMTP | isteğe bağlı | Tanımlı değilse sıfırlama bağlantısı sunucu günlüğüne ve yanıtın `reset_url` alanına yazılır |

Anahtar adresleri: Gemini [Google AI Studio](https://aistudio.google.com/apikey), OpenAI [platform.openai.com](https://platform.openai.com/api-keys), Hugging Face [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).

### WhisperX ve ffmpeg

WhisperX, API’nin `.venv` ortamına kurulmaz. Ayrı bir sanal ortam kullanılır (örneğin masaüstünde `whisperx-env`), içinde GPU’lu PyTorch ve `whisperx` bulunur. Windows:

```powershell
cd %USERPROFILE%\Desktop
python -m venv whisperx-env
.\whisperx-env\Scripts\activate
pip install whisperx
```

Uygulama `whisperx` komutunu `WHISPERX_BIN`, sistem `PATH` ve `Desktop/whisperx-env` altında arar. Bulamazsa toplantı kaydı oluşur, durum `failed` olur.

ffmpeg PATH’te olmalıdır (videodan ses ayırma ve oynatma). Windows: `winget install Gyan.FFmpeg`.

Konuşmacı ayırma `HF_TOKEN` ister. Özet ve soru Gemini veya OpenAI anahtarı ister.

### Frontend

```powershell
cd frontend
npm install
```

Gerekirse `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Çalıştırma

PostgreSQL, API (`:8000`) ve istemci (`:3000`) aynı anda çalışır.

**API** (çalışma dizini `backend`):

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload --reload-dir app
```

`GET http://localhost:8000/health` → `{ "status": "ok", "database": "connected" }`.

**İstemci:**

```powershell
cd frontend
npm run dev
```

Tarayıcı: `http://localhost:3000`.

Unix: `source .venv/bin/activate` sonra aynı `uvicorn` komutu.

OpenAPI: `http://localhost:8000/docs` — ReDoc: `/redoc`.

---

## HTTP API

Taban: `/api/v1`. Hata gövdesi `{ "detail": "…" }`. Açık şema: `http://localhost:8000/docs`.

### Sağlık

| Metod | Yol | Açıklama |
|-------|-----|----------|
| GET | `/health` | Veritabanı ping; kapalıysa 503 |
| GET | `/api/v1/health` | Aynı |

### Kimlik — `/api/v1/auth`

| Metod | Yol | Auth | Gövde | Sonuç |
|-------|-----|------|-------|--------|
| POST | `/register` | — | `{ email, password }` (min. 6) | 201 token |
| POST | `/login` | — | `{ email, password }` | 200 token |
| GET | `/me` | evet | — | kullanıcı |
| POST | `/change-password` | evet | `{ current_password, new_password }` | kullanıcı |
| POST | `/forgot-password` | — | `{ email }` | Aynı mesaj; SMTP yoksa `reset_url` |
| POST | `/reset-password` | — | `{ token, password }` | token |

Token: `{ access_token, token_type: "bearer", user }`. Çift e-posta 409. Hatalı giriş 401.

### Toplantılar — `/api/v1/meetings`

| Metod | Yol | Açıklama |
|-------|-----|----------|
| GET | `/` | Kullanıcının toplantıları |
| POST | `/` | `multipart/form-data`; transkripsiyon kuyruğa. 201 |
| GET | `/{id}` | Toplantı detayı ve transkripsiyon ilerlemesi |
| PATCH | `/{id}` | Başlık, tarih, özet, aksiyon, karar ve transkript güncellemeleri |
| DELETE | `/{id}` | 204; medya silinir |
| GET | `/{id}/audio` | Oynatma (inline) |
| POST | `/{id}/analyze` | Analiz kuyruğu. Transkript yoksa 409 |
| POST | `/{id}/ask` | `{ question }` (1–2000) → `{ answer, cites }` |
| PATCH | `/{id}/speakers` | Satır / toplu etiket / tahmin onay-red |
| PATCH | `/{id}/transcript` | `{ seq, text, flags? }` |
| POST | `/{id}/transcript/merge` | `{ seq }`: sonraki satırı bu satıra ekler, alt satırı siler |

`POST` form: `title`, `date` (gelecek an +1 dk’dan ileri 422), `audio` (mp3/wav/m4a/mp4/webm/mov; boş veya >500 MB → 400); isteğe `attendees`, `description`, `language` (`tr` \| `en`).

`PATCH /{id}` alanları: `title`, `date`, `description`, `named_attendees` / `attendees` (transkript varsa eşleme yeniden), `summary`, `update_transcript`, `update_action`, `update_decision`, `dismiss_action`, `analyze: true`.

Konuşmacı gövdesi:

```json
{ "from_speaker": "Konuşmacı F", "speaker": "Mehmet" }
```

```json
{ "seq": 12, "speaker": "Mehmet" }
```

```json
{ "from_speaker": "Ali ?", "action": "confirm" }
```

`action`: `confirm` \| `reject`. Aynı toplantıda çakışan kişi adı 409. Bu uç `people.name` güncellemez.

### Kişiler — `/api/v1/people`

Aynı hesapta aynı görünen ad yok (İ/i eşlenir) → 409.

| Metod | Yol | Açıklama |
|-------|-----|----------|
| GET | `/` | Liste; `?meeting_id=` süzgeci |
| POST | `/` | `{ name, note? }` → 201 |
| PATCH | `/{person_id}` | Ad değişince görev, aksiyon, transkript etiketleri |
| DELETE | `/{person_id}` | 204 |

### Görevler — `/api/v1/tasks`

Kimlik `(meeting_id, action_seq)`. Teslim tarihi zorunlu; geçmiş gün 422. Durum: `in_progress` \| `done`.

| Metod | Yol | Açıklama |
|-------|-----|----------|
| GET | `/` | Görevler, göreve çevrilmemiş aksiyonlar, kişiler |
| POST | `/` | `action_seq` varsa o aksiyondan; tekrar 409 |
| PATCH | `/{meeting_id}/{action_seq}` | Başlık, durum, sorumlu, tarih |
| DELETE | `/{meeting_id}/{action_seq}` | 204; aksiyon kalır |

```json
{
  "meeting_id": 41,
  "title": "Teklifi gönder",
  "due_date": "2026-09-10",
  "assignee": "Hasan",
  "action_seq": 3
}
```

`speaker_label` konuşmacıyı kişi kaydına bağlar.

### Örnek

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"ornek@example.com\",\"password\":\"gizli12\"}"

curl -s http://localhost:8000/api/v1/meetings \
  -H "Authorization: Bearer ACCESS_TOKEN"

curl -s -X POST http://localhost:8000/api/v1/meetings/41/analyze \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

---

## Test

PostgreSQL açık olmalıdır.

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

---

## Depo düzeni

```text
ai-scribe/
├── backend/       FastAPI, tests/, sql/schema.sql, uploads/, .env.example
├── frontend/      Next.js
├── docs/week1/    Tasarım notları
└── README.md
```
