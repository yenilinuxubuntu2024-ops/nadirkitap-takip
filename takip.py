#!/usr/bin/env python3
"""nadirkitap.com'a yeni düşen kitap ilanlarını takip edip WhatsApp'a gönderir.

WhatsApp gönderimi CallMeBot (ücretsiz) ile yapılır. config.json içine:
  {"telefon": "+905xxxxxxxxx", "apikey": "123456"}
İlk çalıştırmada mevcut ilanlar "görüldü" sayılır (mesaj yağmuru olmasın diye).
Kullanım:  python3 takip.py            -> normal kontrol
           python3 takip.py --test     -> WhatsApp'a test mesajı
           python3 takip.py --hepsi    -> mevcut ilanların listesini de gönder
           python3 takip.py --derin    -> çok sayfa tara, fiyat geçmişini doldur (mesaj göndermez)

FIRSAT: Her kitap için görülen ilanların fiyatları saklanır. Yeni ilan, aynı türdeki
aynı cilt sayılı tam takım ilanlarının ortanca fiyatından FIRSAT_ORAN kadar ucuzsa 🔥 FIRSAT diye
işaretlenir. Fırsat olan takımlar alt fiyat sınırının altında olsa da bildirilir.
"""
import gzip, html, json, os, re, statistics, sys, time, unicodedata, urllib.parse, urllib.request
from pathlib import Path

DIR = Path(__file__).resolve().parent
SEEN = DIR / "gorulenler.json"
FIYATLAR = DIR / "fiyatlar.json"
CONFIG = DIR / "config.json"
FIRSAT_ORAN = 0.30  # ortancanın %30 altı = fırsat
MIN_ORNEK = 5       # ortanca için gereken en az ilan sayısı

# (ad, [arama kelimeleri], başlık şartları: gruplardan biri tam tutmalı, en düşük fiyat TL)
ARAMALAR = [
    ("Tefhimü'l-Kur'an", ["tefhimül kuran"], [["tefhim"]], 0),
    ("Fî Zılâli'l-Kur'an", ["fi zilalil kuran", "fizilal", "kuranın gölgesinde"],
     [["zilal"], ["kuraningolgesinde"]], 1000),
    ("Hak Dini Kur'an Dili", ["hak dini kuran dili", "elmalılı tefsiri"],
     [["hakdini"], ["elmalili", "tefsir"]], 1000),
    ("Safvetü't-Tefâsîr", ["safvetüt tefasir"], [["safvet"]], 1000),
    ("İbn Kesir Tefsiri", ["ibn kesir tefsiri", "ibni kesir tefsiri", "hadislerle kuranı kerim tefsiri"],
     [["kesir", "tefsir"], ["hadislerlekuran"]], 1000),
    ("Tefsîr-i Kebîr", ["tefsiri kebir", "mefatihul gayb", "razi tefsiri"],
     [["kebir", "tefsir"], ["mefatih"], ["razi", "tefsir"]], 1000),
    ("Allah Dostları", ["allah dostları"], [["allahdostlari"]], 1000),
    # yazarlar: başlıkta yazar adı geçen her ilan
    ("Ahmet Kalkan kitabı", ["ahmet kalkan"], [["ahmetkalkan"]], 0),
    ("Yusuf Kandehlevi kitabı", ["kandehlevi"], [["kandeh"]], 700),
    ("Hayatü's-Sahabe", ["hayatüs sahabe"], [["hayat", "sahabe"]], 700),
    ("Dört Mezhebe Göre İslam Fıkhı", ["dört mezhebe göre islam fıkhı"], [["dortmezheb", "fikh"]], 900),
    ("Cezîrî fıkıh kitabı", ["abdurrahman ceziri"], [["ceziri"]], 900),
]
SAYFA = 1  # yeni eklenenlere göre ilk kaç sayfa taranacak (10 dk aralıkla 1 sayfa yeterli)
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "tr-TR,tr;q=0.9", "Accept-Encoding": "gzip"}

ITEM = re.compile(
    r'<a href="(https://www\.nadirkitap\.com/[^"]*?kitap(\d+)\.html)" title="([^"]*)" class="nadirBook"'
    r'.*?class="price"[^>]*>([^<]*)<', re.S)


def get(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=40)
    veri = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        veri = gzip.decompress(veri)
    return veri.decode("utf-8", "replace")


def norm(t):
    t = t.replace("İ", "i").replace("I", "ı").lower().replace("ı", "i")
    t = unicodedata.normalize("NFKD", t)
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in t if not unicodedata.combining(c)))


def fiyat_sayi(f):
    try:
        return float(re.sub(r"[^\d,]", "", f).replace(",", "."))
    except ValueError:
        return 0.0


def tur(baslik):
    """Fiyat karşılaştırma grubu: 'takim16' gibi (tam takım + cilt sayısı) ya da 'diger'.
    Eksik takımlar ve cilt sayısı belli olmayanlar karşılaştırılmaz."""
    n = norm(baslik)
    if "eksik" in n or not re.search(r"takim|tamtakim|set", n):
        return "diger"
    sayilar = [int(x) for x in re.findall(r"(\d+)(?:cilt|kitap)", n)]
    sayilar = [x for x in sayilar if 2 <= x <= 60]
    return f"takim{max(sayilar)}" if sayilar else "diger"


def ilanlar(kelimeler, sart, sayfa=SAYFA):
    """Başlık şartını tutan tüm ilanlar (fiyat filtresi yok)."""
    out = {}
    for kelime in kelimeler:
        for p in range(1, sayfa + 1):
            url = ("https://www.nadirkitap.com/kitapara_sonuc.php?kelime=" + urllib.parse.quote_plus(kelime)
                   + f"&siralama=yenieklenenler&page={p}")
            bulunan = ITEM.findall(get(url))
            for link, kid, baslik, fiyat in bulunan:
                baslik = html.unescape(baslik).strip()
                n = norm(baslik)
                if any(all(k in n for k in grup) for grup in sart):
                    out[kid] = {"baslik": baslik, "fiyat": fiyat.strip(), "tl": fiyat_sayi(fiyat),
                                "tur": tur(baslik), "link": link}
            time.sleep(2)
            if not bulunan:
                break
    return out


def ortanca(gecmis, tur_, haric):
    fiyatlar = [f for kid, (f, t) in gecmis.items() if t == tur_ and kid != haric and f > 0]
    return statistics.median(fiyatlar) if len(fiyatlar) >= MIN_ORNEK else None


def whatsapp(metin):
    if os.environ.get("TELEFON"):  # GitHub Actions: bilgiler gizli değişkenlerden
        c = {"telefon": os.environ["TELEFON"], "apikey": os.environ["APIKEY"]}
    else:
        c = json.loads(CONFIG.read_text())
    url = ("https://api.callmebot.com/whatsapp.php?phone=" + urllib.parse.quote(c["telefon"])
           + "&text=" + urllib.parse.quote(metin) + "&apikey=" + urllib.parse.quote(str(c["apikey"])))
    r = get(url)
    if "queued" not in r.lower() and "sent" not in r.lower():
        print("WhatsApp hatası:", re.sub(r"<[^>]+>", " ", r)[:300])


def satir(x):
    s = f"📖 {x['baslik']}\n💰 {x['fiyat']}"
    if x.get("ortanca"):
        s = "🔥 FIRSAT!\n" + s + f" (piyasa ~{x['ortanca']:,.0f} TL, %{x['indirim']:.0f} ucuz)".replace(",", ".")
    return s + "\n" + x["link"]


def gonder(liste, bas):
    # CallMeBot mesaj uzunluğu sınırlı; 5'erli parçalar halinde gönder
    for i in range(0, len(liste), 5):
        whatsapp(bas + "\n\n" + "\n\n".join(satir(x) for x in liste[i:i + 5]))
        time.sleep(3)


def main():
    if "--test" in sys.argv:
        whatsapp("✅ Nadirkitap takip botu çalışıyor.")
        return
    derin = "--derin" in sys.argv
    kayit = json.loads(SEEN.read_text()) if SEEN.exists() else {}
    if isinstance(kayit, list):  # eski biçim: sadece Tefhim
        kayit = {"tefhimül kuran": kayit}
    fiyat_kayit = json.loads(FIYATLAR.read_text()) if FIYATLAR.exists() else {}
    gonderilen = set()  # aynı ilan birden çok aramada çıkarsa bir kez bildir
    for ad, kelimeler, sart, min_fiyat in ARAMALAR:
        anahtar = kelimeler[0]
        try:
            simdi = ilanlar(kelimeler, sart, 5 if derin else SAYFA)
        except Exception as e:
            print(ad, "hata:", e)
            continue
        gecmis = fiyat_kayit.setdefault(anahtar, {})
        ilk = anahtar not in kayit or derin
        gorulen = set(kayit.get(anahtar, []))
        bildir = []
        for kid, v in simdi.items():
            if kid in gorulen or kid in gonderilen:
                continue
            orta = ortanca(gecmis, v["tur"], kid)
            firsat = v["tur"] != "diger" and orta and v["tl"] > 0 and v["tl"] <= orta * (1 - FIRSAT_ORAN)
            if firsat:
                v["ortanca"], v["indirim"] = orta, 100 * (1 - v["tl"] / orta)
            # alt sınırın üstündekiler + sınırın altında kalsa da fırsat olan takımlar
            if v["tl"] > min_fiyat or firsat:
                bildir.append(v)
        gonderilen |= set(simdi)
        for kid, v in simdi.items():
            gecmis[kid] = [v["tl"], v["tur"]]
        sinir = f" ({min_fiyat:.0f} TL üstü)" if min_fiyat else ""
        if "--hepsi" in sys.argv and simdi:
            liste = [v for v in simdi.values() if v["tl"] > min_fiyat]
            if liste:
                gonder(liste, f"📚 Nadirkitap'ta şu an {len(liste)} {ad} ilanı{sinir}:")
        elif bildir and not ilk:
            bildir.sort(key=lambda x: not x.get("ortanca"))  # fırsatlar önce
            n_f = sum(1 for x in bildir if x.get("ortanca"))
            bas = f"🆕 Nadirkitap'a {len(bildir)} yeni {ad} ilanı düştü{sinir}"
            gonder(bildir, bas + (f" — {n_f} tanesi 🔥 FIRSAT:" if n_f else ":"))
        kayit[anahtar] = sorted(gorulen | set(simdi))
        SEEN.write_text(json.dumps(kayit, ensure_ascii=False))
        FIYATLAR.write_text(json.dumps(fiyat_kayit, ensure_ascii=False))
        print(f"{ad}: {len(simdi)} ilan, {len(bildir)} bildirim"
              f"{' (ilk/derin tarama, mesaj yok)' if ilk and not '--hepsi' in sys.argv else ''}.")


if __name__ == "__main__":
    main()
