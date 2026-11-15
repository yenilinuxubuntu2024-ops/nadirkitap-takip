#!/usr/bin/env python3
"""nadirkitap.com'a yeni düşen Tefhimü'l-Kur'an ilanlarını takip edip WhatsApp'a gönderir.

WhatsApp gönderimi CallMeBot (ücretsiz) ile yapılır. config.json içine:
  {"telefon": "+905xxxxxxxxx", "apikey": "123456"}
İlk çalıştırmada mevcut ilanlar "görüldü" sayılır (mesaj yağmuru olmasın diye).
Kullanım:  python3 takip.py            -> normal kontrol
           python3 takip.py --test     -> WhatsApp'a test mesajı
           python3 takip.py --hepsi    -> mevcut ilanların listesini de gönder
"""
import gzip, html, json, re, sys, time, unicodedata, urllib.parse, urllib.request
from pathlib import Path

DIR = Path(__file__).resolve().parent
SEEN = DIR / "gorulenler.json"
CONFIG = DIR / "config.json"
# (ad, arama kelimesi, başlıkta geçmesi gereken kelimeler, en düşük fiyat TL)
ARAMALAR = [
    ("Tefhimü'l-Kur'an", "tefhimül kuran", ["tefhim"], 0),
    ("Fî Zılâli'l-Kur'an", "fi zilalil kuran", ["zilal"], 1000),
    ("Hak Dini Kur'an Dili", "hak dini kuran dili", ["hakdini"], 1000),
    ("Safvetü't-Tefâsîr", "safvetüt tefasir", ["safvet"], 1000),
    ("İbn Kesir Tefsiri", "ibn kesir tefsiri", ["kesir", "tefsir"], 1000),
    ("Tefsîr-i Kebîr", "tefsiri kebir", ["kebir", "tefsir"], 1000),
    ("Allah Dostları", "allah dostları", ["allahdostlari"], 1000),
    # yazarlar: başlıkta yazar adı geçen her ilan
    ("Ahmet Kalkan kitabı", "ahmet kalkan", ["ahmetkalkan"], 0),
    ("Yusuf Kandehlevi kitabı", "kandehlevi", ["kandeh"], 700),
    ("Hayatü's-Sahabe", "hayatüs sahabe", ["hayat", "sahabe"], 700),
    ("Dört Mezhebe Göre İslam Fıkhı", "dört mezhebe göre islam fıkhı", ["dortmezheb", "fikh"], 900),
    ("Cezîrî fıkıh kitabı", "abdurrahman ceziri", ["ceziri"], 900),
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


def ilanlar(kelime, sart, min_fiyat):
    out = {}
    for p in range(1, SAYFA + 1):
        url = ("https://www.nadirkitap.com/kitapara_sonuc.php?kelime=" + urllib.parse.quote_plus(kelime)
               + f"&siralama=yenieklenenler&page={p}")
        for link, kid, baslik, fiyat in ITEM.findall(get(url)):
            baslik = html.unescape(baslik).strip()
            n = norm(baslik)
            if all(k in n for k in sart) and fiyat_sayi(fiyat) > min_fiyat:
                out[kid] = {"baslik": baslik, "fiyat": fiyat.strip(), "link": link}
        time.sleep(2)
    return out


def whatsapp(metin):
    import os
    if os.environ.get("TELEFON"):  # GitHub Actions: bilgiler gizli değişkenlerden
        c = {"telefon": os.environ["TELEFON"], "apikey": os.environ["APIKEY"]}
    else:
        c = json.loads(CONFIG.read_text())
    url = ("https://api.callmebot.com/whatsapp.php?phone=" + urllib.parse.quote(c["telefon"])
           + "&text=" + urllib.parse.quote(metin) + "&apikey=" + urllib.parse.quote(str(c["apikey"])))
    r = get(url)
    if "queued" not in r.lower() and "sent" not in r.lower():
        print("WhatsApp hatası:", re.sub(r"<[^>]+>", " ", r)[:300])


def gonder(liste, bas):
    # CallMeBot mesaj uzunluğu sınırlı; 5'erli parçalar halinde gönder
    for i in range(0, len(liste), 5):
        satirlar = [f"📖 {x['baslik']}\n💰 {x['fiyat']}\n{x['link']}" for x in liste[i:i + 5]]
        whatsapp(bas + "\n\n" + "\n\n".join(satirlar))
        time.sleep(3)


def main():
    if "--test" in sys.argv:
        whatsapp("✅ Nadirkitap takip botu çalışıyor.")
        return
    kayit = json.loads(SEEN.read_text()) if SEEN.exists() else {}
    if isinstance(kayit, list):  # eski biçim: sadece Tefhim
        kayit = {"tefhimül kuran": kayit}
    gonderilen = set()  # aynı ilan birden çok aramada çıkarsa bir kez bildir
    for ad, kelime, sart, min_fiyat in ARAMALAR:
        try:
            simdi = ilanlar(kelime, sart, min_fiyat)
        except Exception as e:
            print(ad, "hata:", e)
            continue
        ilk = kelime not in kayit
        gorulen = set(kayit.get(kelime, []))
        yeni = [v for k, v in simdi.items() if k not in gorulen and k not in gonderilen]
        gonderilen |= set(simdi)
        sinir = f" ({min_fiyat:.0f} TL üstü)" if min_fiyat else ""
        if "--hepsi" in sys.argv and simdi:
            gonder(list(simdi.values()), f"📚 Nadirkitap'ta şu an {len(simdi)} {ad} ilanı{sinir}:")
        elif yeni and not ilk:
            gonder(yeni, f"🆕 Nadirkitap'a {len(yeni)} yeni {ad} ilanı düştü{sinir}:")
        kayit[kelime] = sorted(gorulen | set(simdi))
        SEEN.write_text(json.dumps(kayit, ensure_ascii=False))
        print(f"{ad}: {len(simdi)} ilan, {len(yeni)} yeni{' (ilk tarama, mesaj yok)' if ilk else ''}.")


if __name__ == "__main__":
    main()
