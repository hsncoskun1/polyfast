# GPT'YE SORU: Polyfast Event Selection Bug

## PROBLEM

Bot her seferinde CURRENT slot event yerine BIR SONRAKI slot event'ine order gonderiyor.

## ORNEKLER

Test 1:
- Live event: btc-updown-5m-1775921100 (11:25-11:30 ET)
- Order gittigi: "11:30AM-11:35AM ET" (sonraki slot)

Test 2:
- Live event: btc-updown-5m-1775922600 (11:50-11:55 ET)  
- Order gittigi: "11:55AM-12:00PM ET" (sonraki slot)

Her seferinde tam 1 slot (5dk / 300s) ilerideki event'e gidiyor.

## SLUG CONVENTION

Polymarket'ta 2 farkli slug formati var:

1. Gamma API slug: btc-updown-5m-{END_TIMESTAMP}
   - Discovery'den gelen
   - end_ts = event bitiş zamanı

2. Polymarket page slug: btc-updown-5m-{START_TIMESTAMP}  
   - Event page URL'sinde kullanilan
   - start_ts = event baslangic zamani

Ornek — AYNI EVENT:
- Gamma: btc-updown-5m-1775922900 (END=1775922900)
- Page:  btc-updown-5m-1775922600 (START=1775922600)
- Event: 11:50-11:55 ET (start=1775922600, end=1775922900)

## MEVCUT is_current MANTIGI

```python
# Gamma slug'tan END timestamp parse
m = re.search(r'-(\d{10,})$', slug)
end_ts = int(m.group(1))
is_current = (end_ts - 300) <= now < end_ts
```

Bu hesap matematiksel olarak DOGRU gorunuyor.

## AMA NEDEN YANLIS EVENT'E ORDER GIDIYOR?

Debug sirasinda "is_current=True, Match live=True" donuyor.
Ama pozisyon title'ina bakildiginda HER ZAMAN 1 slot ilerideki event'e order gitmis.

Olasi nedenler:
1. Discovery callback zamani ile order dispatch zamani arasinda slot degisiyor
2. event_map'e yazilan event current degil upcoming
3. Gamma API event'leri siralamasi bekledigimizden farkli
4. is_current hesabindaki (end_ts - 300) hesabi yanlis

## GAMMA API'DEN GELEN EVENTLER

Discovery 5 BTC event donderiyor:
```
btc-updown-5m-1775922600  end=1775922600 start=1775922300 is_current=???
btc-updown-5m-1775922900  end=1775922900 start=1775922600 is_current=???
btc-updown-5m-1775923200  end=1775923200 start=1775922900 is_current=???
btc-updown-5m-1775923500  end=1775923500 start=1775923200 is_current=???
btc-updown-5m-1775923800  end=1775923800 start=1775923500 is_current=???
```

now=1775922700 ise (11:50-11:55 ET slot icindeyiz):
- btc-updown-5m-1775922600: start=1775922300, end=1775922600 → 1775922300 <= 1775922700 < 1775922600 → FALSE (end gecmis!)
- btc-updown-5m-1775922900: start=1775922600, end=1775922900 → 1775922600 <= 1775922700 < 1775922900 → TRUE ← CURRENT!

DOGRU event: btc-updown-5m-1775922900 (Gamma slug)
Polymarket page: btc-updown-5m-1775922600 (START)
Bunlar AYNI EVENT.

## PEKI NEDEN "YANLIS EVENT" GORUNUYOR?

Pozisyon title "11:55AM-12:00PM ET" → bu btc-updown-5m-1775922900 event'inin title'i MI?

HAYIR — bekle:
- btc-updown-5m-1775922900 → start=1775922600=11:50ET, end=1775922900=11:55ET
- Title: "11:50AM-11:55AM ET" OLMALI
- Ama title "11:55AM-12:00PM ET" yaziyor → bu btc-updown-5m-1775923200 event'i!

Yani bizim sectigimiz event btc-updown-5m-1775922900 (11:50-11:55) ama order btc-updown-5m-1775923200 (11:55-12:00) event'ine gitmis.

BU NASIL OLABILIR?

Ihtimaller:
1. discovery callback baska zamanda calisti ve farkli event secti
2. subscription_manager rotate sirasinda yanlis event secti
3. bridge token_id baska event'e ait
4. Gamma API bazen event siralamasini degistiriyor

## ESKI BACKEND

Eski backend'de live order execution YOKTU.
Paper mode: fill_price = dominant_price (0-1 range, sabit).
Order gonderilmediginden "yanlis event" sorunu hic yasamadik.

## SORU

1. Bu "1 slot ilerideki event'e order gitme" sorununun gercek kok nedeni ne?
2. is_current hesabi gercekten dogru mu?
3. Yoksa Gamma API slug timestamp'i biz yanlis mi anliyoruz?
4. En guvenilir "current live event" tespit yontemi ne?
5. CLOB API'de market'in resolved/active durumundan current event belirlenebilir mi?
