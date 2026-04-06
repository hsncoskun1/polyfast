# 7/24 Operasyonel Risk Haritası

## HEMEN DÜZELTİLEBİLİR (bu sürümde)

### 1. CoinPriceClient — COZULDU (v0.3.6+)
- **Dosya:** backend/market_data/coin_price_client.py
- **Eski Risk:** poll_once() one-shot, surekli loop yoktu
- **Cozum:** run_forever() persistent WS + 150ms resubscribe ile degistirildi
- **Durum:** COZULDU — telemetry (resub_count, reconnect_count, connection_uptime) eklendi
- **Kalan Risk:** Unofficial endpoint — soak test yapilmadi, rate limit bilinmiyor

### 2. Config stale threshold'ları coin_price_client'a bağlı değil
- **Dosya:** backend/market_data/coin_price_client.py
- **Risk:** MarketDataConfig.coin_price_stale_threshold_seconds tanımlı ama kullanılmıyor
- **Durum:** Hardcoded 15s (şans eseri config default ile aynı)

## 7/24 İÇİN RİSKLİ — İLERİ FAZDA ÇÖZÜLECEK

### 3. Registry records hiç silinmiyor (memory leak)
- **Risk:** CLOSED/EXPIRED event'ler bellekte kalır, ayda ~8640 record birikir
- **Çözüm:** Cleanup mekanizması (ileri faz)
- **Aciliyet:** ORTA — aylar içinde sorun olabilir

### 4. Health incident'lar trading'i bloke etmiyor
- **Risk:** RTDS kopsa bile trading devam edebilir (stale veriyle)
- **Çözüm:** Evaluation'da stale → WAITING zaten var, ama orchestrator seviyesinde de gate olmalı
- **Aciliyet:** ORTA — rule engine WAITING döndürüyor ama üst katman kontrolü yok

### 5. RTDSClient run_forever() circuit breaker yok
- **Risk:** Polymarket saatlerce kapalıysa 30s arayla sonsuza kadar dener
- **Çözüm:** Escalation politikası (WARNING → CRITICAL → UI bildirim)
- **Aciliyet:** DÜŞÜK — sistem çalışmaya devam eder, sadece gereksiz retry

### 6. Pipeline/PTB/Bridge cleanup otomatik değil
- **Risk:** Biten event'lerin verileri bellekte kalır
- **Çözüm:** Orchestrator event bitişinde cleanup çağıracak
- **Aciliyet:** ORTA

### 7. Açık pozisyon varken WS kopması
- **Risk:** TP/SL hesaplanamaz (outcome stale)
- **Koruma:** Force sell time çalışır (stale safety override)
- **Aciliyet:** DÜŞÜK — force sell time son çare olarak tasarlandı

### 8. App restart / recovery
- **Risk:** In-memory state kaybolur (positions, settings, registry)
- **Çözüm:** Persistence + recovery (Faz 7)
- **Aciliyet:** YÜKSEK ama scope dışı (Faz 7)

## 7/24 İÇİN UYGUN (mevcut tasarım yeterli)

- PTB retry schedule: event sonuna kadar dener ✅
- Reconnect deadline bazlı: event sonuna kadar ✅
- Stale → WAITING: evaluation doğru davranıyor ✅
- Invalid data filtering: 0, negatif, 1+ engelleniyor ✅
- Force sell time: stale durumda bile çalışır ✅
- FOK: partial fill yok, kör retry yok ✅
