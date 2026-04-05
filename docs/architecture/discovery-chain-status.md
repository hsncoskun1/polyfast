# Discovery → Trade Pipeline Zinciri — Mevcut Durum

## Zincir Halkaları

| # | Halka | Durum | Dosya | Açıklama |
|---|-------|-------|-------|----------|
| 1 | Discovery engine | ✅ VAR | backend/discovery/engine.py | scan() çağrıldığında slug bazlı zaman filtresiyle aktif eventleri bulur |
| 2 | Periyodik discovery loop | ❌ YOK | — | scan()'ı düzenli aralıklarla çağıran background loop yok |
| 3 | Registry sync | ⚠️ KOD VAR, ÇAĞIRAN YOK | backend/registry/safe_sync.py | SafeSync.sync() var ama onu çağıran orchestrator yok |
| 4 | Registry expiration | ❌ YOK | — | Event süre dolunca EXPIRED'a otomatik geçiş yapan kod yok |
| 5 | Eligibility gate caller | ⚠️ MODEL VAR, ÇAĞIRAN YOK | backend/settings/coin_settings.py | is_trade_eligible var ama kontrol eden katman yok |
| 6 | Subscription orchestrator | ❌ YOK | — | Eligible event için WS subscribe, ineligible için unsubscribe yok |
| 7 | Evaluation loop | ❌ YOK | — | Context oluşturup RuleEngine.evaluate() çağıran periyodik döngü yok |

## Discovery Doğal Event Geçişi

Discovery engine tek başına çağrıldığında doğru event'i bulur:
- scan() her çağrıda slug timestamp'ini current time'a göre filtreler
- Event bittiyse (timestamp < now) otomatik olarak exclude edilir
- Yeni event (timestamp > now ama < now + 1800) dahil edilir

AMA: Onu çağıran, registry'yi güncelleyen, eligibility kontrol eden,
subscription yöneten ve evaluation tetikleyen orchestrator TAMAMEN EKSİK.

## Discovery Retry Politikası (Bağlayıcı Karar)

- Normal discovery scan cadence: config'den (default 10s)
- Failure retry cadence: aynı interval ile devam (hız düşürmez)
- Retry sonsuz — sistem discovery failure'da DURMAZ
- Health warning üretir
- Yeni event/trade opportunity geçici olarak durur
- AMA mevcut açık pozisyonlar discovery failure yüzünden DURMAZ
- Discovery retry admin/advanced safety altında olacak, normal kullanıcı ayarı DEĞİL

## Sonuç

Parçalar hazır ama birbirine BAĞLI DEĞİL. Orchestrator katmanı olmadan
sistem otomatik çalışmaz. Bu ileri fazda (v0.4.2+) implement edilecek.
