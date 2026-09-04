# AI-SCRIBE

AI-SCRIBE, toplantı sesini veya videosunu yazıya çeviren bir asistan. Konuşmacıları ayırır; sen istediğinde özet, karar ve aksiyon üretir. Transkript hazır olduktan sonra aynı kayda soru sorabilir, aksiyonları göreve çevirip kişi ve teslim tarihiyle takip edebilirsin.

Tipik sıra: **kayıt yükle → WhisperX transkript → Analiz yap → özet, kararlar, aksiyonlar.** Analiz kendiliğinden başlamaz. **Sor**, yalnızca o toplantının transkriptine bakarak cevap verir.

Proje tek depoda durur: `frontend/` (Next.js), `backend/` (FastAPI) ve PostgreSQL.

## Özellikler

- Hesap: kayıt ol, giriş yap, şifre sıfırla (SMTP), hesap ayarları
- Toplantı: ses (`mp3` / `wav` / `m4a`) veya video (`mp4` / `webm` / `mov`); yüklerken dil **Türkçe** veya **English**
- Transkript, ses oynatıcı, konuşmacı eşleme, satır düzeltme
- Analiz: özet (Çerçeve / Gündem / Sonuç), kararlar, aksiyonlar — toplantının diline göre
- Görev panosu, kişiler, dashboard’daki takvim
- Dışa aktarma: PDF, Word, Markdown — tarayıcıda üretilir; dil yine toplantıya göre
- Sor: cevap yalnız bu transkriptten gelir; alıntıya tıklayınca kayıt o ana atlar

Bir kişinin adını **Kişiler** sayfasından değiştirirsen, bağlı toplantılara da yansır. Transkriptteki konuşmacı etiketini değiştirmek kişi kaydının adını değiştirmez.

---

## Sistem mimarisi

### Teknoloji

| Katman | Teknoloji |
|--------|-----------|
| Arayüz | Next.js 16, React 19, Tailwind CSS 4 |
| API | Python 3.12, FastAPI, Uvicorn, Pydantic |
| Veritabanı | PostgreSQL (SQLAlchemy 2 + psycopg) |
| Kimlik | JWT (HS256, 7 gün), bcrypt, `Authorization: Bearer` |
| Konuşmayı yazıya çevirme | Bilgisayarda çalışan **WhisperX** (konuşmacı ayırmak için Hugging Face jetonu) |
| Medya | **ffmpeg** (videodan ses alma, süre) |
| Dil modeli | Google Gemini (`GEMINI_API_KEY`); yoksa OpenAI (`OPENAI_API_KEY`) |
| Dosya | `backend/uploads/{user_id}/` — en fazla 500 MB |
| Dışa aktarma | Tarayıcıda `jspdf` / `docx` / Markdown |

### Genel bakış

```mermaid
flowchart LR
  subgraph istemci ["Tarayıcı — Next.js :3000"]
    UI[Sayfalar ve bileşenler]
    EXP[PDF / Word / MD]
  end

  subgraph api ["FastAPI :8000"]
    R[api/v1]
    SVC[Servisler]
    REPO[Repository]
  end

  PG[(PostgreSQL)]
  UP[uploads/]
  WX[WhisperX + ffmpeg]
  LLM[Gemini / OpenAI]

  UI -->|JSON + JWT| R
  UI -->|multipart ses/video| R
  EXP -.-> UI
  R --> SVC
  SVC --> REPO
  REPO --> PG
  SVC --> UP
  SVC -->|Popen| WX
  SVC -->|HTTPS| LLM
```

Ön yüz ve API ayrı süreçlerdir. Ön yüz, API’yi `NEXT_PUBLIC_API_URL` ile çağırır (varsayılan `http://localhost:8000`). CORS `http://localhost:3000` ve `http://127.0.0.1:3000` için açıktır.

### Toplantı iş akışı

```mermaid
sequenceDiagram
  participant U as Kullanıcı
  participant FE as Next.js
  participant API as FastAPI
  participant WX as WhisperX
  participant DB as PostgreSQL
  participant LLM as Gemini / OpenAI

  U->>FE: Kayıt yükle (dil, katılımcılar)
  FE->>API: POST /api/v1/meetings (multipart)
  API->>DB: meeting status=uploaded
  API-->>FE: MeetingOut
  API->>WX: arka plan transkript
  WX-->>API: satırlar + konuşmacı etiketleri
  API->>DB: transcripts, status=transcribed
  Note over API: Konuşmacı eşleme (ad listesi varsa)
  U->>FE: Analiz yap
  FE->>API: POST /meetings/{id}/analyze
  API->>LLM: özet / karar / aksiyon
  LLM-->>API: JSON
  API->>DB: analyses, decisions, actions, status=analyzed
  U->>FE: Sor / görev ata / dışa aktar
```

Toplantı durumları: `uploaded` → `transcribed` → `analyzed`. Transkript başarısız olursa `failed`. Analiz, transkript bitmeden çalışmaz. Whisper’ın ürettiği konuşmacı etiketlerinden kişi kaydı **açılmaz**; kişi ya görev atarken ya da Kişiler sayfasından oluşur.

### Backend katmanları

```
backend/app/
├── main.py                 FastAPI uygulaması, CORS, açılış/kapanış (şema + Whisper iptali)
├── api/v1/                 HTTP uç noktaları
├── schemas/                İstek ve yanıt modelleri
├── models/                 SQLAlchemy tabloları
├── repositories/           PostgreSQL okuma / yazma
├── services/
│   ├── storage.py          Yükleme, uzantı, 500 MB sınırı
│   ├── transcription.py    WhisperX, ffmpeg, konuşmacı ayırma
│   ├── speakers.py         Ad listesi ile Konuşmacı A/B eşleme
│   ├── analysis.py         Özet / karar / aksiyon boru hattı
│   ├── analysis_prompts.py Analiz prompt metinleri
│   ├── llm.py              Gemini / OpenAI JSON çağrıları
│   ├── meeting_jobs.py     Transkript, konuşmacı eşleme, analiz işleri
│   ├── ask.py              Tek toplantıya soru
│   ├── transcript_review.py
│   ├── mail.py             Şifre sıfırlama e-postası
│   └── meeting_lang.py     tr | en
└── core/
    ├── config.py           .env
    ├── database.py         bağlantı, oturum, ensure_schema
    └── security.py         JWT, bcrypt
```

Uygulama açılırken `ensure_schema()` eksik kolonları ve `people` tablolarını ekler. İlk kurulumda tam şema `backend/sql/schema.sql` ile kurulur.

`--reload --reload-dir app` yalnızca geliştirme içindir. Transkript veya analiz sürerken `backend/app` altındaki bir dosyayı kaydetmek Uvicorn’u yeniden başlatır ve işi yarıda keser.

### Veri modeli

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

  users {
    int user_id PK
    string email UK
    string password
  }
  meetings {
    int meeting_id PK
    string status
    string language
    string named_attendees
    string audio_path
  }
  transcripts {
    int meeting_id PK
    int seq PK
    int timestamp
    string speaker
  }
  people {
    int person_id PK
    string name
  }
  tasks {
    int meeting_id PK
    int action_seq PK
    string status
    date due_date
  }
```

- **users** — giriş hesabı. Şifre bcrypt ile tutulur; sıfırlama jetonu hash’lenerek saklanır.
- **meetings** — başlık, tarih, dil (`tr` / `en`), senin yazdığın katılımcılar (`named_attendees`), konuşmacı özeti (`attendees`).
- **transcripts** — toplantıya bağlı satırlar; anahtar `(meeting_id, seq)`. `timestamp` saniye cinsinden. `speaker_origin` ilk diarization etiketidir.
- **people** — hesaba özel kişi listesi; aynı isim ikinci kez eklenemez. Bu kayıtlar giriş hesabı değildir.
- **meeting_people** — hangi kişinin hangi toplantıda olduğu; isteğe bağlı `speaker_label`.
- **analyses / decisions / actions** — analiz çıktısı. Aksiyon, göreve çevrilene kadar öneridir.
- **tasks** — bir aksiyonla bire bir `(meeting_id, action_seq)`. Durum: `in_progress` veya `done`. Teslim tarihi zorunludur.

### Ön yüz

Sayfalar JWT’yi `localStorage` içinde `access_token` olarak tutar. PDF / Word / Markdown sunucuda değil, tarayıcıda üretilir.

| Adres | Ekran |
|-------|--------|
| `/login`, `/login/forgot`, `/reset-password` | Giriş ve şifre |
| `/` | Dashboard (takvim, özet kartlar) |
| `/meetings`, `/meetings/new`, `/meetings/[id]` | Liste, yükleme, transkript / analiz / Sor |
| `/tasks` | Görev panosu ve öneriler |
| `/people` | Kişiler |
| `/settings` | Şifre değiştir |

---

## Kurulum

Geliştirirken üç şey ayrı çalışır: PostgreSQL, FastAPI, Next.js.

### Gereksinimler

- Python 3.12+
- Node.js 20+ (npm)
- PostgreSQL 14+
- ffmpeg (`PATH` içinde veya `FFMPEG_BIN`)
- WhisperX, FastAPI ortamından **ayrı** bir sanal ortamda (`whisperx` komutu). Uygulama sırasıyla `WHISPERX_BIN`, `PATH` ve masaüstündeki `whisperx-env` klasörüne bakar.
- Hugging Face jetonu (konuşmacı ayırma / pyannote)
- Gemini veya OpenAI API anahtarı (analiz ve Sor)

### 1. PostgreSQL

Veritabanı adı, `backend/.env` içindeki `DATABASE_URL` ile aynı olsun.

```sql
CREATE DATABASE "ai-scribe";
```

İlk şema:

```bash
psql -U postgres -d ai-scribe -f backend/sql/schema.sql
```

`schema.sql` tabloları silip yeniden oluşturur; dolu bir veritabanındaki veriyi yok eder. Daha sonra eklenen kolonlar uygulama açılışında `ensure_schema` ile gelir.

### 2. Backend

Windows (PowerShell):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

macOS / Linux:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` dosyasını doldur:

| Değişken | Açıklama |
|----------|----------|
| `DATABASE_URL` | `postgresql+psycopg://KULLANICI:SIFRE@localhost:5432/ai-scribe` |
| `SECRET_KEY` | JWT imzası; uzun, rastgele bir metin. `change-me` olarak bırakma |
| `GEMINI_API_KEY` | Analiz ve Sor (yoksa `OPENAI_API_KEY`) |
| `GEMINI_MODEL` | Varsayılan `gemini-3.1-flash-lite` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Gemini yoksa yedek (`gpt-4o-mini`) |
| `HF_TOKEN` | WhisperX konuşmacı ayırma |
| `FRONTEND_URL` | Şifre sıfırlama bağlantısı, varsayılan `http://localhost:3000` |
| `CORS_ORIGINS` | JSON dizisi; varsayılan localhost:3000 |
| `UPLOAD_DIR` | Varsayılan `uploads` (backend’in çalışma dizinine göre) |
| `WHISPERX_MODEL` | Varsayılan `large-v3` |
| `WHISPERX_BIN` | `whisperx.exe` / `whisperx` tam yolu (isteğe bağlı) |
| `FFMPEG_BIN` | `ffmpeg` tam yolu (isteğe bağlı) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | Şifre sıfırlama e-postası. SMTP yoksa bağlantı sunucu günlüğüne (ve yanıtta `reset_url` olarak) yazılır |

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload --reload-dir app
```

```bash
python -m uvicorn app.main:app --port 8000 --reload --reload-dir app
```

- API: http://localhost:8000
- OpenAPI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Sağlık kontrolü: http://localhost:8000/health

Komutu `backend/` klasöründen çalıştır. Aksi halde `uploads/` ve `.env` yanlış yerde aranır.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Uygulama: http://localhost:3000

İstersen `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### WhisperX

WhisperX’i FastAPI sanal ortamına kurma; ayrı tut. `whisperx` komutu `PATH`’te veya `WHISPERX_BIN` ile görünür olsun. GPU / CUDA kurulumu modele göre değişir. Konuşmacı ayırmak için `HF_TOKEN` ve pyannote koşulları gerekir. Video yüklenince ffmpeg sesi ayırır.

### Testler

PostgreSQL açık olsun. Whisper ve analiz bu testlerde çalışmaz.

```powershell
cd backend
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
```

```bash
cd backend
pip install -r requirements.txt
python -m pytest
```

---

## API

Tüm asıl uç noktalar **`/api/v1`** altındadır. Kökte ayrıca `GET /health` vardır.

Güncel şema http://localhost:8000/docs adresindedir. Aşağıdaki özet, koddaki yönlendiricilerle uyumludur.

### Kimlik doğrulama

Kayıt, giriş ve şifre sıfırlama dışında istekler `Authorization: Bearer <access_token>` ister. Jeton 7 gün geçerlidir. JWT **adres satırındaki sorgu parametresine konmaz**.

Hata gövdesi genelde `{ "detail": "…" }` şeklindedir (metin veya doğrulama listesi).

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Sağlık

| Metod | Yol | Giriş | Açıklama |
|-------|-----|-------|----------|
| GET | `/health` | — | Veritabanına ping; 503 = bağlantı yok |
| GET | `/api/v1/health` | — | Aynı |

Yanıt: `{ "status": "ok", "database": "connected" }`

### Auth — `/api/v1/auth`

| Metod | Yol | Giriş | Gövde | Başarı |
|-------|-----|-------|-------|--------|
| POST | `/register` | — | `{ "email", "password" }` (şifre en az 6 karakter) | 201 `TokenResponse` |
| POST | `/login` | — | `{ "email", "password" }` | 200 `TokenResponse` |
| GET | `/me` | evet | — | `UserOut` |
| POST | `/change-password` | evet | `{ "current_password", "new_password" }` | `UserOut` |
| POST | `/forgot-password` | — | `{ "email" }` | `{ "message", "reset_url"? }` (e-posta kayıtlı olmasa da aynı mesaj) |
| POST | `/reset-password` | — | `{ "token", "password" }` | `TokenResponse` |

`TokenResponse`: `{ "access_token", "token_type": "bearer", "user": { "user_id", "name", "email" } }`

E-posta zaten varsa 409. Yanlış e-posta veya şifre 401.

### Toplantılar — `/api/v1/meetings`

| Metod | Yol | Gövde | Açıklama |
|-------|-----|-------|----------|
| GET | `/` | — | Senin toplantıların (`MeetingListOut`) |
| POST | `/` | **multipart** | Yeni toplantı ve dosya; transkript kuyruğa alınır. 201 `MeetingOut` |
| GET | `/{id}` | — | Detay: transkript, özet, karar, aksiyon, kişiler, ilerleme. Durum `uploaded` ve çalışan iş yoksa transkript yeniden başlar |
| PATCH | `/{id}` | JSON `MeetingUpdate` | Başlık vb. ve aşağıdaki iç alanlar |
| DELETE | `/{id}` | — | 204; kayıt dosyası da silinir |
| GET | `/{id}/audio` | — | Kaydı oynatmak için dosya (`FileResponse`) |
| POST | `/{id}/analyze` | — | Analizi başlatır veya yeniler. Transkript yoksa 409 |
| POST | `/{id}/ask` | `{ "question" }` (1–2000 karakter) | Transkripte soru. `{ "answer", "cites": [{ seq, timestamp, speaker, text }] }` |
| PATCH | `/{id}/speakers` | `SpeakerRenameIn` | Konuşmacı: tek satır, tüm etiket veya tahmin onayı / reddi |
| PATCH | `/{id}/transcript` | `{ "seq", "text", "flags"? }` | Satır metni |

**POST /** form alanları:

| Alan | Zorunlu | Not |
|------|---------|-----|
| `title` | evet | 1–255 karakter |
| `date` | evet | ISO tarih-saat; gelecekte olamaz |
| `audio` | evet | mp3, wav, m4a, mp4, webm, mov; boş dosya 400; 500 MB üstü 400 |
| `attendees` | — | Virgülle isimler (`named_attendees`) |
| `description` | — | |
| `language` | — | `tr` (varsayılan) veya `en` |

**PATCH /{id}** — gönderdiğin alanlar uygulanır:

| Alan | Ne yapar |
|------|----------|
| `title`, `date`, `description` | Toplantı bilgileri |
| `named_attendees` veya `attendees` | Yazılan katılımcılar; transkript varsa konuşmacı eşlemesi yeniden çalışır |
| `summary` | Özet metni |
| `update_transcript` | `{ seq, text, flags }` |
| `update_action` | `{ seq, description?, assignee?, assignee_id?, speaker_label?, due_date?, notes? }` |
| `update_decision` | `{ seq, text }` |
| `dismiss_action` | Aksiyon önerisini siler (`seq`) |
| `analyze` | `true` ise analizi kuyruğa alır (transkript şart) |

Bu PATCH kısa kayıt (`MeetingOut`) döner. Tam detay için ardından `GET /{id}` çağır.

**PATCH /{id}/speakers** örnekleri:

```json
{ "from_speaker": "Konuşmacı F", "speaker": "Mehmet" }
```

```json
{ "seq": 12, "speaker": "Mehmet" }
```

```json
{ "from_speaker": "Ali ?", "action": "confirm" }
```

`action`: `confirm` veya `reject`. Aynı toplantıda bu isimde başka konuşmacı varsa 409. Bu uç, **Kişiler listesindeki adı değiştirmez**.

**MeetingOut:** `meeting_id`, `title`, `date`, `status`, `duration`, `attendees`, `named_attendees`, `description`, `language`, `audio_path`.

**MeetingDetailOut:** bunların üzerine `transcript[]`, `summary`, `decisions[]`, `actions[]`, `people[]`, isteğe bağlı `transcription` (`progress`, `message`, `error`, `elapsed_seconds`).

### Kişiler — `/api/v1/people`

Aynı hesapta aynı isim ikinci kez kullanılamaz (Türkçe büyük/küçük harf farkı yok sayılır). 409: `"Bu isimde biri zaten var"` veya o toplantıda başka konuşmacının adı çakışıyorsa.

| Metod | Yol | Açıklama |
|-------|-----|----------|
| GET | `/` | Kişi listesi. `?meeting_id=` ile o toplantıya bağlı olanlar |
| POST | `/` | `{ "name", "note?" }` → 201 |
| PATCH | `/{person_id}` | Ad ve/veya not. **Ad değişince** bağlı görev ve aksiyon yazıları ile o kişinin toplantılarındaki transkript etiketleri güncellenir |
| DELETE | `/{person_id}` | 204 |

`PersonOut`: `person_id`, `name`, `note`, `label`, `attendee`, `meetings[]`.

### Görevler — `/api/v1/tasks`

Teslim tarihi zorunludur; geçmiş bir gün 422 verir. Durum: `in_progress` veya `done`.

| Metod | Yol | Açıklama |
|-------|-----|----------|
| GET | `/` | `{ items, suggestions, people }` — görevler, henüz göreve çevrilmemiş aksiyonlar, kişi listesi |
| POST | `/` | Yeni görev. `action_seq` varsa o aksiyondan; yoksa toplantıya yeni aksiyon ve görev. 201. Aynı aksiyon ikinci kez görev olursa 409 |
| PATCH | `/{meeting_id}/{action_seq}` | Başlık, durum, sorumlu, tarih, açıklama |
| DELETE | `/{meeting_id}/{action_seq}` | 204 |

**POST gövdesi (`TaskCreate`):**

```json
{
  "meeting_id": 41,
  "title": "Teklifi gönder",
  "due_date": "2026-09-10",
  "description": "",
  "assignee": "Hasan",
  "assignee_id": null,
  "speaker_label": "Konuşmacı F",
  "action_seq": 3
}
```

`speaker_label`, konuşmacıyı kişiye bağlar ve transkript etiketini kişi adına çevirir. Kişi bir kez oluştuktan sonra transkriptte isim değiştirmek kişi kaydının adını değiştirmez.

---

## Örnek istekler

```bash
# Kayıt
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"sen@ornek.com\",\"password\":\"gizli12\"}"

# Liste (jetonu giriş yanıtından al)
curl -s http://localhost:8000/api/v1/meetings \
  -H "Authorization: Bearer ACCESS_TOKEN"

# Analiz
curl -s -X POST http://localhost:8000/api/v1/meetings/41/analyze \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

---

## Depo

```text
ai-scribe/
├── backend/
│   ├── app/                 FastAPI uygulaması
│   ├── tests/               pytest (API + birim)
│   ├── sql/schema.sql       İlk PostgreSQL şeması
│   ├── uploads/             Kayıt dosyaları (git’te yok)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/app/             Next.js sayfaları
├── docs/week1/              İlk tasarım notları; güncel bilgi bu README’de
└── README.md
```

Git’e girmez: `backend/.env`, `backend/uploads/*`, `downloads/`, `frontend/.next/`, sanal ortamlar.

Bu repoda Docker / Compose yok; yerelde üç süreci ayrı çalıştırırsın.
