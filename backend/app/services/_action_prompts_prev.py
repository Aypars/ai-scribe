"""Previous action prompts, kept for revert."""

ANALYSIS_ACTIONS_TR = """- actions: Toplantıdan SONRA kalacak iş. Kart, A’nın sormasından değil B’nin üstlenmesinden veya atamasından doğar.
  Şüphede kart yazma. Açık teslim veya açık atama yoksa boş bırak.
  Aynı oturumda okunan, aynı teslim türündeki (yazılı rapor / yazılı cevap) kalemler, müdürlükleri ayrı olsa da tek pakettir: tek kart; alt başlıklar notes’ta.
  Somut fiil söylendiyse (yazın, çevirin, hazırlayın) description’da o fiili koru; “incelensin / değerlendirilsin”e yumuşatma.
  Yalnız soru, şikayet, iddia, önerge metni, durum güncellemesi kart değildir.
  Odada bilgi istenip cevaplandıysa brifing kartı yazma. Cevaptan sonra kalan somut iş varsa yalnız onu yaz.
  Oylanmış gündem maddesinin uygulama adımı karar olarak kalsın; yeni aksiyon kartı yapma.
  Oylanmamış “gündeme alınsın / değerlendirilsin / uygun görüyoruz” önerisi kart değildir.
  Farklı yerleri tek karta yapıştırma. İki yer konuşulduysa yalnız somut emir verilen yer kalsın. Aynı konuşmacının peş peşe sorduğu yerler tek iş değildir.
  Oylanmamış önerge kart değildir. Önergenin “grupta/komisyonda görüşülmesi” de kart değildir; bu ertelemedir.
  Kartta iki yer adı varsa (ve/ile) birleştirme yapma: yalnız somut emir verilen yer kalsın; bilgi verilen yer adını notes’tan da sil.
  description net iş cümlesi olsun. notes yalnız o işe ait bağlam içersin.
  assignee her zaman null. due_date yalnız açık tarih."""

CHUNK_ACTIONS_TR = """AKSİYON (toplantıdan SONRA kalacak iş):
- Şüphede yazma. Açık teslim veya açık atama yoksa kart yok. Yöneticinin verdiği kısa somut emir (çevirin, yazın, çalışın) karttır.
- Kart, A’nın talebinden değil B’nin üstlenmesinden/atamasından doğar.
- Aynı oturumda okunan yazılı rapor/cevap kalemleri, müdürlükleri ayrı olsa da tek karttır; alt başlıklar notes’ta.
- Somut fiili koru; “incele / değerlendir”e yumuşatma.
- Soru, şikayet, iddia, önerge metni, durum bildirimi kart değildir.
- Odada bilgi istenip cevaplandıysa brifing kartı yazma; cevap sonrası kalan somut emir varsa onu yaz. Üye peş peşe iki yer sorup biri cevaplandıysa yalnız emir verilen yer kart olur.
- Oylanmış maddenin uygulama adımını ve oylanmamış “değerlendirilsin” önerisini kart yapma.
- Karar listesini görev listesine kopyalama.
- Farklı yerleri tek karta yapıştırma. Aynı konuşmacının peş peşe sorduğu yerler tek iş değildir. Aynı işi tekrarlama.
- description net ve tek iş olsun. notes yalnız o işin bağlamı olsun. assignee null."""

REFINE_ACTIONS_TR = """AKSİYONLAR:
- Aynı oturumda okunan yazılı rapor/cevap/önerge kalemleri, konu başlıkları farklı görünse de TEK pakettir: tek kart. Alt başlıkları notes’ta sırala. Müdürlük müdürlük ayrı kart bırakma.
- Açık teslimi veya açık ataması olmayan kartı sil.
- Kart B’nin üstlendiği/atadığı teslim olsun. Somut fiil ve isimleri koru; yumuşatma.
- Teslimi olmayan erteleme, salt durum, salt soru/şikayet/iddia, oylanmamış öneriyi sil.
- Odada bilgi istenip cevaplanan başlığı sil. İki yer konuşulduysa yalnız somut emir verilen yer kalsın; bilgi verilen yeri diğerine yapıştırma. Aynı konuşmacının peş peşe sorduğu yerler tek iş değildir.
- Cevaptan sonra kalan somut emir varsa o emri ayrı kart olarak bırak; soyutlaştırma.
- Üyenin oylanmayan “uygun görüyoruz / öneriyoruz” işlemini aksiyona çevirme.
- Aynı işin kopyasını sil. Farklı yer adı taşıyan kartları birleştirme. İki yer “güvenlik” temasında olsa bile tek kart yapma.
- Karar listesini actions’a kopyalama.
- assignee her zaman null."""

ACTION_DEDUP_PROMPT = """Aksiyon listesini yalnız kendi içinde süz.

Kurallar:
- Ham listeyi geri verme; yalnız nihai listeyi ver.
- Aynı oturumda okunan yazılı rapor/cevap kalemleri konu başlıkları farklı görünse de TEK karta indir; alt başlıkları notes’ta sırala.
- Aynı işin kopyasını/dar-geniş tekrarını tek karta indir.
- Karar cümlesini ve oylanmış maddenin uygulama adımını görev kartına çevirme.
- Oylanmamış önerge metnini ve önergenin grupta görüşülmesini çıkar.
- Odada bilgi istenip cevaplanan başlığı çıkar. Cevaptan sonra kalan somut emir varsa o emri bırak; rapor paketine yapıştırma.
- Farklı yer adı taşıyan kartları birleştirme. Aynı tema (güvenlik, rapor) olsa bile mahalle/yer birleştirmek yasak. Aynı konuşmacının peş peşe sorduğu iki yer tek kart olmaz.
- Somut fiili koru, yumuşatma.
- Yeni kart ekleme; yalnız birleştir, böl veya çıkar.

JSON: actions. assignee null. due_date yalnız listede açık tarih varsa.
"""

ACTION_QA_PROMPT = """Aksiyonları son kalite kontrolünden geçir. Transkript kanıtını esas al.
Yeni iş uydurma. Listedeki konuyu başka bir gündem maddesine çevirme. Girdide yoksa yeni kart ekleme; yalnız birleştir veya çıkar.

Zorunlu:
1) Aynı oturumda okunan yazılı rapor/cevap kartlarını, konu başlıkları farklı görünse de TEK karta birleştir. Alt başlıkları notes’ta sırala. Bunu atlama.
2) Odada cevaplanan brifing kartını çıkar. Cevaplanmış bilgi talebini sonradan “yazılı rapor sunulsun” kartına çevirme. Ana fiili bilgi vermek / gözden geçirmek / incelemek olan ve somut emri olmayan kartı çıkar.
3) Kartta iki yer adı varsa (ve/ile bağlacı) birleştirmedir. Kart sayısını artırma. Yalnız somut emir verilen yer kalsın; bilgi verilen yer adını başlıktan ve notes’tan sil.
4) Salt iddia üzerine “inceleme başlatın” kartı yazma. Somut teslim yoksa kart değildir.
5) Oylanmamış önergeyi çıkar. Kartın bütün işi bir önergeyi grupta veya komisyonda görüşmekse çıkar; bu teslim değil ertelemedir.

Korunacak:
- Brifingden sonra verilen somut emri koru. Bu emri rapor paketiyle birleştirme ve silme. Somut fiili soyutlaştırma.
- Başkanın ayrı bir konu için “çalışın / başlayalım” dediği iş. Bunu güvenlik veya rapor kartına yapıştırma.
- Birleştirilmiş rapor paketi.

Yanlış: aynı paketin alt başlıklarını ayrı kart yapmak; cevaplanmış brifingi tutmak; iki yeri tek karta yapıştırmak.
Doğru: tek rapor paketi + somut emir verilen ayrı iş kartları.

JSON: actions. assignee null. due_date yalnız açık tarih varsa.
"""

ACTION_DEDUP_PROMPT_EN = """Filter the action list against itself.

Rules:
- Return the filtered final list, not the raw dump.
- Merge duplicates and narrow-vs-wide restatements of the same job.
- Written-report / written-reply items from one packet are ONE card even if directorates differ; keep sub-items in notes.
- Do not convert decision statements or voted-item implementation into action cards.
- Remove cards that are only questions, complaints, allegations, motion text, status updates, or unvoted “please consider this”.
- If a briefing was asked and answered in-room, drop the briefing. Keep a remaining concrete order if one was then assigned; do not drop that order as “just a briefing”.
- Do not merge cards that name different places. Same theme (security, reports) does not make them one job.
- Preserve concrete action verbs.
- If ownership or deliverable is unclear, drop the card.
- Invent no new jobs.

JSON: actions. assignee null. due_date only if an explicit date already in the list.
"""

ACTION_QA_PROMPT_EN = """Run a final quality gate on action cards. Trust the transcript evidence.
Invent no new jobs. Do not rewrite the list into a different agenda item.

Required:
1) Merge written-report / written-reply cards into ONE card even if directorates differ. List sub-items in notes. Do not skip this.
2) Drop a briefing that was answered in-room. Drop a card whose main verb is brief / review / look into with no remaining concrete order.
3) If a card names two places joined by and/with, that is a glue. Do not add cards. Keep only the place that received a remaining concrete order; delete the briefed place name from the title and from notes.
4) Do not write an “open an investigation” card from an allegation alone. “They will inform us / we will look together” is not a card without a concrete deliverable.
5) Drop an unvoted proposal. If the whole card is “discuss this motion in the group/committee”, drop it; that is a deferral, not a deliverable.

Keep:
- A remaining concrete order after a briefing.
- The merged report packet.

Bad: leaving report cards split; keeping an answered briefing; gluing two neighborhoods into one card.
Good: one report-packet card plus remaining concrete-order cards.

JSON: actions. assignee null. due_date only when explicitly spoken.
"""

USER_PROMPT_V1 = """<role>
Toplantı transkriptini analiz eden ve yalnızca toplantı SONRASINA kalan somut görevleri (actions) çıkaran bir asistansın.
</role>

<definitions>
- AKSİYON: Toplantı sırasında bir yöneticinin açıkça atadığı (örn: "yapın", "çevirin", "çalışın") veya birinin üstlendiği, toplantı bittikten sonra yapılması gereken somut iş.
- AKSİYON OLMAYANLAR: Oylanmamış önergeler, sadece grupta/komisyonda görüşüleceği söylenen konular, salt şikayet/iddia metinleri, bilgi verilip anında odayı aydınlatan (brifing) cevaplar ve alınan kararların uygulama adımları.
</definitions>

<rules>
1. KOPYALARI İMHA ET (DEDUP): Aynı işin kopyasını veya dar/geniş tekrarını üreten maddeleri kesinlikle tek bir karta indir. Aynı konuşmacının peş peşe sorduğu aynı konudaki yerleri iki ayrı iş gibi yazma.
2. YAZILI RAPORLAR (BİRLEŞTİR): Aynı oturumda okunan tüm "yazılı rapor", "yazılı cevap" veya "önerge cevaplanması" taleplerini müdürlükleri farklı olsa dahi TEK bir görev kartı yap. İstenen alt kalemleri (sosyal tesisler, marinyat vb.) `notes` alanında liste halinde ver.
3. LOKASYONLAR (AYIR): Farklı mekanlar/yerler için ayrı ayrı emirler verilmişse, bunları "A ve B mahallesinde..." diye tek karta yapıştırma. Yalnızca somut emir verilen yer(ler) için net kartlar oluştur. Sadece bilgi verilen yeri tamamen yoksay.
4. FİİLLERİ KORU: Transkriptteki somut emir fiilini (yazın, çevirin, bariyer koyun) doğrudan `description` alanına taşı. Fiilleri soyutlaştırıp "incelenecek", "değerlendirilecek" şekline çevirme.
5. GÖREVLENDİRME: `assignee` her zaman `null` olacak. `due_date` yalnızca metinde kesin bir tarih söylenmişse dolacak, aksi halde boş kalacak.
6. NETLİK: `description` tek ve net bir iş cümlesi içermeli, görevin bağlamı yalnızca `notes` kısmında yer almalı.
</rules>
"""
