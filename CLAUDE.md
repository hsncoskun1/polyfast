# POLYMAX-5M — CLAUDE.md

Bu dosya, projede calisan Claude icin baglayici gelistirme kurallarini, urun amacini, mimari sinirlari, kalite beklentilerini ve degistirilemez ilkeleri tanimlar.

Bu proje sifirdan yazilacaktir.

Amac, eski kodlari yamalamak degil; dogru urun mantigini alip teknik borc tasimayan, katmanlari net ayrilmis, test edilebilir, aciklanabilir, guvenilir ve local-first calisan yeni bir uygulama uretmektir.

"Refactor sonradan yaparim", "simdilik dogru degeri saglasin sonra bakarim", "once calissin sonra temizleriz", "tek dosyada toparlariz" gibi yaklasimlar bu projede kabul edilmez.

Bu proje, ilk gunden itibaren production mantigi ile tasarlanacak, kucuk surumlerle ilerleyecek, her surumde test edilecek, raporlanacak ve dusuk teknik borcla buyutulecektir.

## 1. Urunun Amaci

Bu uygulama, Polymarket'in Crypto tabi altindaki Up/Down kategorisinde yer alan tum uygun 5 dakikalik (5M) event'leri otomatik kesfeden, surekli guncel tutan, izleyen, kurallara gore karar veren ve tamamen local ortamda calisan tek kullanicili bir trading uygulamasidir.

Sistemde tek karar ve veri otoritesi backend'dir. Frontend hicbir kosulda karar uretmez, yalnizca backend'den gelen authoritative state'i gosterir ve kullanici eylemlerini backend'e iletir.

## 2. Degistirilemez Temel Kurallar

- Uygulama her zaman tek kullanici icindir
- Uygulama local-first calisir
- Backend tek veri ve karar otoritesidir
- Frontend asla ikinci karar motoru olamaz
- Tum kritik davranislar loglanmalidir
- Tum kritik kararlar explainable olmalidir
- Her adim kucuk, kontrollu ve versiyonlu ilerlemelidir
- Bir sorun gecici hack ile kapatilmamali, kok sebep cozulmelidir

## 3. Tech Stack

- Backend: Python 3.12+ / FastAPI
- Frontend: React + Vite + TypeScript
- Storage: SQLite (aiosqlite)
- Test: pytest (backend), vitest (frontend)

## 4. Development Rules

- Test yapilmadan tamamlandi denemez
- Her surum delivery report ile kapanir
- Godfile yasak — her modul tek sorumluluk
- Config ile runtime state karistirilmaz
- Credential plaintext gosterilemez/loglanamaz
- "Simdilik boyle olsun" yasak
- Gecersiz veri (0, --, bos) evaluation katmanina ULASAMAZ
- External connectivity failure sessizce bypass EDILEMEZ

Detayli spec icin master plan dosyasina bakiniz.
