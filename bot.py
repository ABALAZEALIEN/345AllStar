"""345 All Star - Cevap Anahtarı Telegram Botu

Menü yapısı:  Ders  ->  Kitap (konu)  ->  Test  ->  Cevap anahtarı
- Her ekranda ⭐ Favorilere Ekle / Çıkar tuşu (ders, kitap ve test favorilenebilir)
- Her ekranda ⬅️ Geri ve 🏠 Ana Menü tuşu
- Test numarası (örn. 4709) veya konu adı yazarak arama

Kurulum:
    pip install "python-telegram-bot>=20"
    BOT_TOKEN ortam değişkenini ayarla (ya da token.txt dosyasına yaz)
    python bot.py
"""

import html
import json
import logging
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("bot")
logging.getLogger("httpx").setLevel(logging.WARNING)

BASE_DIR = Path(__file__).resolve().parent
ANAHTAR_DOSYA = BASE_DIR / "anahtarlar.txt"
FAVORILER_DOSYA = BASE_DIR / "favoriler.json"
TOKEN_DOSYA = BASE_DIR / "token.txt"

MARKA = "345 All Star"
KITAP_SAYFA_BOYUTU = 10  # bir sayfada kaç kitap
TEST_SAYFA_BOYUTU = 12  # bir sayfada kaç test
FAV_SAYFA_BOYUTU = 8  # bir sayfada kaç favori
CEVAP_SAYFA_BOYUTU = 150  # bir mesajda kaç soru
SIFIR_HATA_GRUP = 50  # Sıfır Hata testleri 50'şerli kitaplara bölünür

# --------------------------------------------------------------------------
# Ders sınıflandırması
# --------------------------------------------------------------------------
# anahtarlar.txt içinde ders bilgisi yok; sadece "Konu - Test" başlıkları var.
# Dersi, konu adından aşağıdaki anahtar kelimelerle buluyoruz (ilk eşleşen kazanır).

DERS_SIRASI = [
    ("Matematik", "📐"),
    ("Geometri", "📏"),
    ("Fizik", "⚛️"),
    ("Kimya", "🧪"),
    ("Biyoloji", "🧬"),
    ("Türkçe", "📖"),
    ("Edebiyat", "✍️"),
    ("Tarih", "🏛"),
    ("Coğrafya", "🌍"),
    ("Felsefe Grubu", "🤔"),
    ("Deneme Sınavları", "📝"),
    ("Hata Testleri", "🎯"),
    ("Diğer", "📦"),
]
DERS_EMOJI = dict(DERS_SIRASI)

DERS_KURALLARI = [
    ("Deneme Sınavları", r"deneme sinavi|kocluk"),
    ("Felsefe Grubu", r"felsefe|felsefi|mantiga giris|klasik mantik|sembolik mantik|mantik ve dil|psikoloji|ogrenme - bellek|ruh sagligi|^ms\. 2|^mo 6"),
    ("Diğer", r"is sagligi"),
    ("Coğrafya", r"ic ve dis kuvvet|dis kuvvet|ic kuvvet|basinc ve ruzgar|biyocesitlilik|uluslararasi orgutler|cevre ve toplum|dogal kaynak|doga, insan|su, toprak|^bitkiler$|su kaynaklari|yer yuvarlagi|kayac|kay\. coz|harita|iklim|cografi|ekonomik faaliyet|nufus|bolge|dunya'nin sekli|dunya'da ve turkiye|turkiye'de|turkiye'nin|turkiye' de|^tr'|^tr\. |insan ve cevre|ekstrem|atmosfer|nem ve yagis|ulkeler"),
    ("Biyoloji", r"yasam bilimi|canli|hucre|kalitim|insan fizyolojisi|bitki biyoloji|bitkilerin|bitki fizyoloji|bitkilerde|genden proteine|gende proteine|komunite|populas|ekosistem ekoloji|ekosistem eko|eko\. ekolo|sinir sistemi|hormon|besinler|enzim|nukleik|^atp|duyu organlari|destek ve hareket|sindirim|dolasim|solunum|uriner|insanda ureme|fotosentez|kemosentez|otozomal|gonozo|esexli|genetik"),
    ("Kimya", r"kimya|\basit|\bbaz|tuz|periyodik|atomun |atom modelleri|modern atom|elektron diz|elementleri|yukseltgenme|\bgaz|gercek gaz|cozun|cozucu|derisim|koligatif|entalpi|bag enerji|tepkime|tep\. |kimyasal denge|dengeyi etkileyen|cozunurluk dengesi|sulu cozelti|maddenin|katilar|sivi|hal degisimi|karisimlar|karisimlarin|ayirma ve saflas|mol kavrami|su ve hayat|gidalar|yaygin gunluk|simyadan|enerji kaynaklari ve bilimsel|enerji kay\. ve|fosil yakit|alternatif enerji|surdurulebilirlik|nanoteknoloji|organik|karbon|alkan|alken|alkin|alkol|eterler|karbonil|karboksilik|esterler|aromatik|fonksiyonel gruplar|lewis|hibrit|basit ve molekul|elektroliz|elek\. huc|indirgenme|metalik aktiflik|guclu etkilesim|zayif etkilesim|kimyasal turler"),
    ("Fizik", r"fizik|manyetizma|elektrostatik|isigin|isik akisi|aydinlanma|aydin\.|golge|ses ve deprem|kaldirma|^basinc$|madde ve ozellik|^kuvvet$|dalga|isi ve sicaklik|mercek|prizma|is, guc|^elektrik|elektrik akimi|^hareket$|basit harmonik|basit makine|itme ve|vektor|^enerji$|boyutta|cembersel hareket|alternatif akim|newton|ivmeli|bagil hareket|radyoaktivite|denge ve denge|yansima ve|^yay "),
    ("Geometri", r"ucgen|\baci|kenarortay|cember|cokgen|dortgen|yamuk|paralelkenar|^kare|deltoid|nokta analitigi|dogru analitigi|kati cisim|donusumler|benzerlik|dairede alan|^alan$"),
    ("Matematik", r"sayi|rasyonel|mutlak|esitsizlik|denklem|uslu|karisim problem|kumeler|carpan|koklu|oruntulu|kesir|yas problem|yuzde|emek|grafik yorum|^mantik$|fonksiyon|polinom|parabol|logaritma|diziler|trigonometri|trigonomometri|limit|turev|integral|oran oranti|bolme|ebob|asal|sayma olasilik|faktoriyel|basamak|gercel|problem|gorsel zeka|tanim ve formul|temel kavram"),
    ("Edebiyat", r"tanzimat|edebiyat|islamiyet oncesi|turk siiri|cumhuriyet donemi|cosku|edebi|hikaye|tiyatro|roman|siir|ogretici metin"),
    ("Türkçe", r"cumlede|sozcuk|paragraf|ses yazim|ses bilgisi|yazim kural|noktalama|isim soylu|anlatim bozuk|anlama dayali|dil bilgisine|fiil|cumle|deyim|atasozu|anlatim teknik|zamir|sifat|^isim|zarf|edat|ek fiil|soz obek|karma dil|dil bilgisi|anlatim"),
    ("Tarih", r"tarih|islam medeniyet|ortacag|orta cag|turk dunyasi|islamiyeti kabul|osmanli|insanligin ilk|milli mucadele|devletlesme|devrim|uluslararasi iliskiler|degisim cagi|\bxix|\bxx\b|ii\. dunya|21\. yuzyil|selcuklu|ataturk|dunya gucu|iki savas|sultan|turk islam"),
]
_DERS_RE = [(d, re.compile(p)) for d, p in DERS_KURALLARI]

_TR_TABLO = str.maketrans("çğıöşü", "cgiosu")


def fold(s: str) -> str:
    """Türkçe harfleri ASCII'ye çevirip küçültür (arama ve eşleştirme için)."""
    return s.replace("İ", "i").replace("I", "ı").lower().translate(_TR_TABLO)


def anahtar(s: str) -> str:
    """Büyük/küçük harf, boşluk ve noktalama farklarını yok sayan karşılaştırma anahtarı."""
    return re.sub(r"[^a-z0-9]", "", fold(s))


def ders_bul(kitap_adi: str):
    f = fold(kitap_adi)
    for ders, rx in _DERS_RE:
        if rx.search(f):
            return ders
    return None


def baslik_ayir(baslik: str):
    """'Kimya Bilimi - Ödev 1A' -> ('Kimya Bilimi', 'Ödev 1A'). Son ' - ' ayracından böler."""
    t = re.sub(r"\s+", " ", baslik).strip()
    parcalar = re.split(r"\s+-\s*|\s*-\s+", t)
    if len(parcalar) == 1:
        return t, ""
    return " - ".join(parcalar[:-1]).strip(), parcalar[-1].strip()


# --------------------------------------------------------------------------
# Veri modeli
# --------------------------------------------------------------------------


class Test:
    __slots__ = ("id", "ad", "kitap", "cevap")

    def __init__(self, id_, ad, kitap, cevap):
        self.id = id_
        self.ad = ad  # butonda görünen ad
        self.kitap = kitap  # Kitap indeksi
        self.cevap = cevap  # "ACEBB..." gibi harf dizisi


class Kitap:
    __slots__ = ("idx", "ad", "key", "ders", "test_idler")

    def __init__(self, idx, ad, key, ders):
        self.idx = idx
        self.ad = ad
        self.key = key  # favoriler için kalıcı anahtar
        self.ders = ders  # Ders indeksi
        self.test_idler = []


class Ders:
    __slots__ = ("idx", "ad", "emoji", "kitaplar")

    def __init__(self, idx, ad, emoji):
        self.idx = idx
        self.ad = ad
        self.emoji = emoji
        self.kitaplar = []  # Kitap indeksleri


class Veri:
    def __init__(self):
        self.dersler = []
        self.kitaplar = []
        self.testler = {}  # exam_id -> Test
        self.ders_adi = {}  # ders adı -> Ders
        self.kitap_key = {}  # kitap.key -> Kitap


_BASLIK_RE = re.compile(r"^=== (.*) \(exam_id: (\d+)\) ===$")
_SORU_RE = re.compile(r"^\s*Soru\s+(\d+)\s*→\s*([A-Ea-e])\s*$")


def dosyayi_oku(yol: Path):
    """anahtarlar.txt -> [(exam_id, baslik, 'ACEBB...'), ...]  (aynı id'yi bir kez alır)."""
    bloklar = []
    goruldu = set()
    cur = None
    with open(yol, "r", encoding="utf-8") as f:
        for satir in f:
            m = _BASLIK_RE.match(satir.rstrip("\n"))
            if m:
                eid = int(m.group(2))
                if eid in goruldu:
                    cur = None
                    continue
                goruldu.add(eid)
                cur = (eid, m.group(1), [])
                bloklar.append(cur)
                continue
            if cur is None:
                continue  # "[SUNUCU/AĞ HATASI ...]" gibi satırlar buraya düşer, atlanır
            m = _SORU_RE.match(satir)
            if m:
                cur[2].append(m.group(2).upper())
    return [(eid, b, "".join(c)) for eid, b, c in bloklar if c]


def veri_olustur(bloklar) -> Veri:
    veri = Veri()
    for i, (ad, emoji) in enumerate(DERS_SIRASI):
        d = Ders(i, ad, emoji)
        veri.dersler.append(d)
        veri.ders_adi[ad] = d

    # 1) Normal testler: ders -> kitap(anahtar) -> test listesi
    gruplar = defaultdict(lambda: defaultdict(list))  # ders -> kitap_key -> [(eid, kitap_adi, test_adi, cevap)]
    hata_testleri = defaultdict(list)  # başlık -> [(eid, cevap)]
    ilk_id = {}  # (ders, key) -> ilk exam_id (sıralama için)
    ders_yok = []

    for eid, baslik, cevap in bloklar:
        if "Hata Testi" in baslik:
            hata_testleri[re.sub(r"\s+", " ", baslik).strip()].append((eid, cevap))
            continue
        kitap_adi, test_adi = baslik_ayir(baslik)
        ders = ders_bul(kitap_adi)
        if ders is None:
            ders_yok.append((eid, kitap_adi, test_adi or kitap_adi, cevap))
            continue
        key = anahtar(kitap_adi)
        gruplar[ders][key].append((eid, kitap_adi, test_adi or kitap_adi, cevap))

    # Dersi bulunamayanlar: ID olarak en yakın komşunun dersine
    if ders_yok:
        komsu = []
        for ders, kitaplar in gruplar.items():
            for lst in kitaplar.values():
                komsu.append((lst[0][0], ders))
        komsu.sort()
        for eid, kitap_adi, test_adi, cevap in ders_yok:
            ders = min(komsu, key=lambda x: abs(x[0] - eid))[1] if komsu else "Diğer"
            gruplar[ders][anahtar(kitap_adi)].append((eid, kitap_adi, test_adi, cevap))

    def kitap_ekle(ders_adi, key, ad, testler):
        ders = veri.ders_adi[ders_adi]
        kitap = Kitap(len(veri.kitaplar), ad, f"{ders_adi}|{key}", ders.idx)
        veri.kitaplar.append(kitap)
        ders.kitaplar.append(kitap.idx)
        veri.kitap_key[kitap.key] = kitap
        for eid, tad, cevap in testler:
            veri.testler[eid] = Test(eid, tad, kitap.idx, cevap)
            kitap.test_idler.append(eid)

    for ders_adi, _ in DERS_SIRASI:
        kitaplar = gruplar.get(ders_adi)
        if not kitaplar:
            continue
        # kitapları ilk test numarasına göre sırala (yayın sırası)
        for key, lst in sorted(kitaplar.items(), key=lambda kv: min(x[0] for x in kv[1])):
            lst.sort(key=lambda x: x[0])
            ad = lst[0][1]
            kullanilan = defaultdict(int)
            for _, _, tad, _ in lst:
                kullanilan[tad] += 1
            testler = [
                (eid, f"{tad} #{eid}" if kullanilan[tad] > 1 else tad, cevap)
                for eid, _, tad, cevap in lst
            ]
            kitap_ekle(ders_adi, key, ad, testler)

    # 2) Hata testleri: isimsiz oldukları için 50'şerli gruplara bölünür
    for baslik in sorted(hata_testleri):
        lst = sorted(hata_testleri[baslik])
        for i in range(0, len(lst), SIFIR_HATA_GRUP):
            parca = lst[i : i + SIFIR_HATA_GRUP]
            ad = f"{baslik} · #{parca[0][0]}–#{parca[-1][0]}"
            testler = [(eid, f"#{eid} · {len(c)} soru", c) for eid, c in parca]
            kitap_ekle("Hata Testleri", f"{baslik}|{parca[0][0]}", ad, testler)

    return veri


def veri_yukle() -> Veri:
    if not ANAHTAR_DOSYA.exists():
        raise FileNotFoundError(f"{ANAHTAR_DOSYA} bulunamadı. anahtarlar.txt bot.py ile aynı klasörde olmalı.")
    bloklar = dosyayi_oku(ANAHTAR_DOSYA)
    veri = veri_olustur(bloklar)
    log.info(
        "Veri yüklendi: %d ders, %d kitap, %d test",
        sum(1 for d in veri.dersler if d.kitaplar),
        len(veri.kitaplar),
        len(veri.testler),
    )
    return veri


# --------------------------------------------------------------------------
# Favoriler  (favoriler.json:  {"kullanici_id": ["d:Matematik", "k:<kitap_key>", "t:4709"]})
# --------------------------------------------------------------------------


class Favoriler:
    def __init__(self, yol: Path):
        self.yol = yol
        self.data = {}
        if yol.exists():
            try:
                with open(yol, "r", encoding="utf-8") as f:
                    ham = json.load(f)
                for uid, liste in ham.items():
                    self.data[str(uid)] = [x for x in liste if re.match(r"^[dkt]:", str(x))]
            except Exception:
                log.exception("favoriler.json okunamadı, boş başlanıyor")

    def liste(self, uid):
        return list(self.data.get(str(uid), []))

    def var_mi(self, uid, fav):
        return fav in self.data.get(str(uid), [])

    def degistir(self, uid, fav) -> bool:
        """Varsa çıkarır, yoksa ekler. Eklendiyse True döner."""
        liste = self.data.setdefault(str(uid), [])
        if fav in liste:
            liste.remove(fav)
            eklendi = False
        else:
            liste.append(fav)
            eklendi = True
        self._kaydet()
        return eklendi

    def cikar(self, uid, fav):
        liste = self.data.get(str(uid), [])
        if fav in liste:
            liste.remove(fav)
            self._kaydet()

    def _kaydet(self):
        fd, tmp = tempfile.mkstemp(dir=str(self.yol.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.yol)


# --------------------------------------------------------------------------
# Ekran üreticileri  (hepsi (metin, klavye) döndürür)
# --------------------------------------------------------------------------

esc = html.escape


def btn(text, data):
    return InlineKeyboardButton(text, callback_data=data)


def sayfa_say(toplam, boyut):
    return max(1, -(-toplam // boyut))


def sayfa_sinirla(sayfa, toplam_sayfa):
    return max(0, min(sayfa, toplam_sayfa - 1))


def nav_satiri(onek, sayfa, toplam_sayfa):
    """◀️  2/5  ▶️  satırı. Tek sayfa varsa None."""
    if toplam_sayfa <= 1:
        return None
    return [
        btn("◀️", f"{onek}:{sayfa - 1}") if sayfa > 0 else btn("·", "noop"),
        btn(f"{sayfa + 1}/{toplam_sayfa}", "noop"),
        btn("▶️", f"{onek}:{sayfa + 1}") if sayfa < toplam_sayfa - 1 else btn("·", "noop"),
    ]


def fav_tusu(uid, favs, tip, ref, sayfa, fav):
    var = favs.var_mi(uid, fav)
    etiket = "💔 Favorilerden Çıkar" if var else "⭐ Favorilere Ekle"
    return [btn(etiket, f"f:{tip}:{ref}:{sayfa}")]


def ana_menu(veri: Veri, uid, favs: Favoriler, karsilama=True):
    baslik = (
        f"🌟 <b>{MARKA} Cevap Anahtarlarına Hoş Geldin!</b>"
        if karsilama
        else f"🏠 <b>{MARKA} · Ana Menü</b>"
    )
    metin = (
        f"{baslik}\n\n📚 Bir ders seç:\n\n"
        "🔎 <i>İpucu: test numarası (örn. 4709) veya konu adı (örn. limit) yazarak da arayabilirsin.</i>"
    )
    satirlar, satir = [], []
    for d in veri.dersler:
        if not d.kitaplar:
            continue
        satir.append(btn(f"{d.emoji} {d.ad}", f"d:{d.idx}:0"))
        if len(satir) == 2:
            satirlar.append(satir)
            satir = []
    if satir:
        satirlar.append(satir)
    n = len(favs.liste(uid))
    satirlar.append([btn(f"⭐ Favorilerim ({n})", "fl:0")])
    return metin, InlineKeyboardMarkup(satirlar)


def ders_ekrani(veri, uid, favs, di, sayfa):
    ders = veri.dersler[di]
    toplam = sayfa_say(len(ders.kitaplar), KITAP_SAYFA_BOYUTU)
    sayfa = sayfa_sinirla(sayfa, toplam)
    parca = ders.kitaplar[sayfa * KITAP_SAYFA_BOYUTU : (sayfa + 1) * KITAP_SAYFA_BOYUTU]

    satirlar = []
    for ki in parca:
        k = veri.kitaplar[ki]
        satirlar.append([btn(f"📚 {k.ad} ({len(k.test_idler)})", f"k:{ki}:0")])
    nav = nav_satiri(f"d:{di}", sayfa, toplam)
    if nav:
        satirlar.append(nav)
    satirlar.append(fav_tusu(uid, favs, "d", di, sayfa, f"d:{ders.ad}"))
    satirlar.append([btn("⬅️ Geri (Ana Menü)", "m")])

    metin = (
        f"{ders.emoji} <b>{esc(ders.ad)}</b>\n"
        f"{len(ders.kitaplar)} kitap · lütfen kitap seç:"
    )
    return metin, InlineKeyboardMarkup(satirlar)


def kitap_ekrani(veri, uid, favs, ki, sayfa):
    kitap = veri.kitaplar[ki]
    ders = veri.dersler[kitap.ders]
    toplam = sayfa_say(len(kitap.test_idler), TEST_SAYFA_BOYUTU)
    sayfa = sayfa_sinirla(sayfa, toplam)
    idler = kitap.test_idler[sayfa * TEST_SAYFA_BOYUTU : (sayfa + 1) * TEST_SAYFA_BOYUTU]

    uzun = any(len(veri.testler[i].ad) > 18 for i in idler)
    kolon = 1 if uzun else 2
    satirlar, satir = [], []
    for tid in idler:
        t = veri.testler[tid]
        satir.append(btn(f"📄 {t.ad}", f"t:{tid}:0"))
        if len(satir) == kolon:
            satirlar.append(satir)
            satir = []
    if satir:
        satirlar.append(satir)
    nav = nav_satiri(f"k:{ki}", sayfa, toplam)
    if nav:
        satirlar.append(nav)
    satirlar.append(fav_tusu(uid, favs, "k", ki, sayfa, f"k:{kitap.key}"))

    geri_sayfa = ders.kitaplar.index(ki) // KITAP_SAYFA_BOYUTU
    satirlar.append([btn("⬅️ Geri", f"d:{ders.idx}:{geri_sayfa}"), btn("🏠 Ana Menü", "m")])

    metin = (
        f"{ders.emoji} {esc(ders.ad)} › 📚 <b>{esc(kitap.ad)}</b>\n"
        f"{len(kitap.test_idler)} test · lütfen test seç:"
    )
    return metin, InlineKeyboardMarkup(satirlar)


def test_ekrani(veri, uid, favs, tid, sayfa):
    t = veri.testler[tid]
    kitap = veri.kitaplar[t.kitap]
    ders = veri.dersler[kitap.ders]
    n = len(t.cevap)
    toplam = sayfa_say(n, CEVAP_SAYFA_BOYUTU)
    sayfa = sayfa_sinirla(sayfa, toplam)
    bas = sayfa * CEVAP_SAYFA_BOYUTU
    parca = t.cevap[bas : bas + CEVAP_SAYFA_BOYUTU]

    ogeler = [f"{bas + i + 1:>3}-{c}" for i, c in enumerate(parca)]
    satirlar_metin = ["  ".join(ogeler[i : i + 5]) for i in range(0, len(ogeler), 5)]
    dagilim = "  ".join(f"{h}:{t.cevap.count(h)}" for h in "ABCDE")

    metin = (
        f"{ders.emoji} {esc(ders.ad)} › 📚 {esc(kitap.ad)}\n"
        f"✅ <b>{esc(t.ad)}</b> · Cevap Anahtarı\n"
        f"🆔 {tid} · {n} soru"
        + (f" · Sayfa {sayfa + 1}/{toplam}" if toplam > 1 else "")
        + f"\n\n<pre>{esc(chr(10).join(satirlar_metin))}</pre>\n"
        f"📊 {dagilim}"
    )

    satirlar = []
    nav = nav_satiri(f"t:{tid}", sayfa, toplam)
    if nav:
        satirlar.append(nav)
    satirlar.append(fav_tusu(uid, favs, "t", tid, sayfa, f"t:{tid}"))
    geri_sayfa = kitap.test_idler.index(tid) // TEST_SAYFA_BOYUTU
    satirlar.append([btn("⬅️ Geri", f"k:{kitap.idx}:{geri_sayfa}"), btn("🏠 Ana Menü", "m")])
    return metin, InlineKeyboardMarkup(satirlar)


def fav_anahtari(veri, tip, ref):
    """Buton verisindeki (tip, indeks) -> favoriler.json'da saklanan kalıcı anahtar."""
    if tip == "d":
        return f"d:{veri.dersler[int(ref)].ad}"
    if tip == "k":
        return f"k:{veri.kitaplar[int(ref)].key}"
    if tip == "t":
        return f"t:{int(ref)}"
    raise ValueError(tip)


def fav_cozumle(veri, fav):
    """Saklanan anahtar -> (etiket, callback_data, tip, ref) ya da None (artık yoksa)."""
    tip, _, ref = fav.partition(":")
    if tip == "d":
        d = veri.ders_adi.get(ref)
        if d and d.kitaplar:
            return f"{d.emoji} {d.ad}", f"d:{d.idx}:0", "d", d.idx
    elif tip == "k":
        k = veri.kitap_key.get(ref)
        if k:
            d = veri.dersler[k.ders]
            return f"📚 {d.ad} › {k.ad}", f"k:{k.idx}:0", "k", k.idx
    elif tip == "t":
        try:
            t = veri.testler.get(int(ref))
        except ValueError:
            t = None
        if t:
            k = veri.kitaplar[t.kitap]
            return f"📄 {k.ad} › {t.ad}", f"t:{t.id}:0", "t", t.id
    return None


def fav_ekrani(veri, uid, favs, sayfa):
    cozulmus = []
    for fav in favs.liste(uid):
        c = fav_cozumle(veri, fav)
        if c:
            cozulmus.append((fav, *c))

    if not cozulmus:
        metin = (
            "⭐ <b>Favorilerim</b>\n\nHenüz favorin yok.\n"
            "Herhangi bir ders, kitap veya testte <b>⭐ Favorilere Ekle</b> tuşuna basarak buraya ekleyebilirsin."
        )
        return metin, InlineKeyboardMarkup([[btn("🏠 Ana Menü", "m")]])

    toplam = sayfa_say(len(cozulmus), FAV_SAYFA_BOYUTU)
    sayfa = sayfa_sinirla(sayfa, toplam)
    parca = cozulmus[sayfa * FAV_SAYFA_BOYUTU : (sayfa + 1) * FAV_SAYFA_BOYUTU]

    satirlar = []
    for fav, etiket, git, tip, ref in parca:
        satirlar.append([btn(etiket, git), btn("❌", f"x:{tip}:{ref}:{sayfa}")])
    nav = nav_satiri("fl", sayfa, toplam)
    if nav:
        satirlar.append(nav)
    satirlar.append([btn("⬅️ Geri (Ana Menü)", "m")])
    metin = f"⭐ <b>Favorilerim</b> ({len(cozulmus)})\nGitmek için dokun, silmek için ❌ bas:"
    return metin, InlineKeyboardMarkup(satirlar)


def arama_ekrani(veri, sorgu):
    """Metinle kitap arar. (metin, klavye) ya da None."""
    kelimeler = fold(sorgu).split()
    if not kelimeler:
        return None
    bulunan = []
    for k in veri.kitaplar:
        f = fold(k.ad)
        if all(w in f for w in kelimeler):
            bulunan.append(k)
    if not bulunan:
        return None
    satirlar = []
    for k in bulunan[:15]:
        d = veri.dersler[k.ders]
        satirlar.append([btn(f"{d.emoji} {k.ad} ({len(k.test_idler)})", f"k:{k.idx}:0")])
    satirlar.append([btn("🏠 Ana Menü", "m")])
    ek = f"\n(İlk 15 sonuç gösteriliyor, {len(bulunan)} sonuç var.)" if len(bulunan) > 15 else ""
    return f"🔎 <b>“{esc(sorgu)}”</b> için sonuçlar:{ek}", InlineKeyboardMarkup(satirlar)


KARSILAMA = (
    f"🌟 <b>{MARKA} Cevap Anahtarlarına Hoş Geldiniz!</b>\n\n"
    "Başlamak için aşağıdaki komuta dokunabilirsin 👇\n\n"
    "/start"
)

BOT_ACIKLAMA = (
    f"🌟 {MARKA} Cevap Anahtarlarına Hoş Geldiniz!\n\n"
    "Ders → Kitap → Test seçerek cevap anahtarına saniyeler içinde ulaş. "
    "Favorilerine ekle, test numarasıyla ara.\n\n"
    "Başlamak için aşağıdaki BAŞLA tuşuna bas 👇"
)


# --------------------------------------------------------------------------
# Telegram işleyicileri
# --------------------------------------------------------------------------


def _veri(context) -> Veri:
    return context.application.bot_data["veri"]


def _favs(context) -> Favoriler:
    return context.application.bot_data["favs"]


async def ekrani_goster(query, metin, klavye):
    try:
        await query.edit_message_text(metin, reply_markup=klavye, parse_mode=ParseMode.HTML)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    metin, klavye = ana_menu(_veri(context), uid, _favs(context), karsilama=True)
    await update.message.reply_text(metin, reply_markup=klavye, parse_mode=ParseMode.HTML)


async def favoriler_komutu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    metin, klavye = fav_ekrani(_veri(context), update.effective_user.id, _favs(context), 0)
    await update.message.reply_text(metin, reply_markup=klavye, parse_mode=ParseMode.HTML)


async def metin_mesaji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Komut olmayan mesajlar: sayı -> test numarası, yazı -> konu araması, bulunmazsa karşılama."""
    veri, favs = _veri(context), _favs(context)
    uid = update.effective_user.id
    yazi = (update.message.text or "").strip()

    if yazi.isdigit():
        tid = int(yazi)
        if tid in veri.testler:
            metin, klavye = test_ekrani(veri, uid, favs, tid, 0)
            await update.message.reply_text(metin, reply_markup=klavye, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ {tid} numaralı bir test bulunamadı.")
        return

    if len(yazi) >= 3:
        sonuc = arama_ekrani(veri, yazi)
        if sonuc:
            await update.message.reply_text(sonuc[0], reply_markup=sonuc[1], parse_mode=ParseMode.HTML)
            return

    await update.message.reply_text(KARSILAMA, parse_mode=ParseMode.HTML)


async def buton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    veri, favs = _veri(context), _favs(context)
    uid = query.from_user.id
    p = data.split(":")
    bildirim = None  # üstte kısa süre görünen uyarı (toast)

    try:
        if data == "noop":
            await query.answer()
            return

        if data == "m":
            metin, klavye = ana_menu(veri, uid, favs, karsilama=False)

        elif p[0] == "d":
            metin, klavye = ders_ekrani(veri, uid, favs, int(p[1]), int(p[2]))

        elif p[0] == "k":
            metin, klavye = kitap_ekrani(veri, uid, favs, int(p[1]), int(p[2]))

        elif p[0] == "t":
            metin, klavye = test_ekrani(veri, uid, favs, int(p[1]), int(p[2]))

        elif p[0] == "fl":
            metin, klavye = fav_ekrani(veri, uid, favs, int(p[1]))

        elif p[0] == "f":  # favori ekle / çıkar: f:<tip>:<ref>:<sayfa>
            tip, ref, sayfa = p[1], p[2], int(p[3])
            eklendi = favs.degistir(uid, fav_anahtari(veri, tip, ref))
            bildirim = "⭐ Favorilere eklendi!" if eklendi else "💔 Favorilerden çıkarıldı."
            if tip == "d":
                metin, klavye = ders_ekrani(veri, uid, favs, int(ref), sayfa)
            elif tip == "k":
                metin, klavye = kitap_ekrani(veri, uid, favs, int(ref), sayfa)
            else:
                metin, klavye = test_ekrani(veri, uid, favs, int(ref), sayfa)

        elif p[0] == "x":  # favoriler listesinden sil: x:<tip>:<ref>:<sayfa>
            tip, ref, sayfa = p[1], p[2], int(p[3])
            favs.cikar(uid, fav_anahtari(veri, tip, ref))
            bildirim = "🗑 Silindi."
            metin, klavye = fav_ekrani(veri, uid, favs, sayfa)

        else:
            await query.answer()
            return

    except (IndexError, ValueError, KeyError):
        log.exception("Geçersiz buton verisi: %r", data)
        await query.answer("Bu buton artık geçerli değil. /start ile yeniden başla.", show_alert=True)
        return

    await query.answer(bildirim)
    await ekrani_goster(query, metin, klavye)


async def sonrasi(app: Application):
    """Bot açılırken komut listesini ve 'sohbet boşken görünen' karşılama metnini ayarlar."""
    try:
        await app.bot.set_my_commands(
            [
                BotCommand("start", "Menüyü aç"),
                BotCommand("favoriler", "Favorilerim"),
            ]
        )
        await app.bot.set_my_description(BOT_ACIKLAMA)
        await app.bot.set_my_short_description(f"{MARKA} cevap anahtarları")
    except Exception:
        log.exception("Bot açıklaması / komutları ayarlanamadı (bot yine de çalışır)")


def token_al() -> str:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token and TOKEN_DOSYA.exists():
        token = TOKEN_DOSYA.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit(
            "Bot token bulunamadı. BOT_TOKEN ortam değişkenini ayarla ya da "
            "token.txt dosyasına token'ı yaz."
        )
    return token


def main():
    veri = veri_yukle()
    favs = Favoriler(FAVORILER_DOSYA)

    app = ApplicationBuilder().token(token_al()).post_init(sonrasi).build()
    app.bot_data["veri"] = veri
    app.bot_data["favs"] = favs

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("favoriler", favoriler_komutu))
    app.add_handler(CallbackQueryHandler(buton))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, metin_mesaji))

    print(f"{MARKA} botu çalışıyor...")
    app.run_polling()


if __name__ == "__main__":
    main()
