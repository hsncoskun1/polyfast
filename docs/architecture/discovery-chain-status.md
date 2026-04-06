# Discovery -> Trade Pipeline Zinciri -- Mevcut Durum

Son guncelleme: v0.6.5

## Zincir Halkalari

| # | Halka | Durum | Dosya | Aciklama |
|---|-------|-------|-------|----------|
| 1 | Discovery engine | VAR | backend/discovery/engine.py | scan() slug bazli zaman filtresiyle aktif eventleri bulur |
| 2 | Periyodik discovery loop | VAR | backend/orchestrator/discovery_loop.py | Slot-aware bul-ve-bekle modeli, retry schedule |
| 3 | Registry sync | VAR | backend/registry/safe_sync.py | SafeSync.sync() orchestrator tarafindan cagriliyor |
| 4 | Registry expiration | VAR | backend/orchestrator/cleanup.py | Event sure dolunca EXPIRED gecisi |
| 5 | Eligibility gate | VAR | backend/orchestrator/eligibility_gate.py | coin_enabled + is_configured = trade eligible |
| 6 | Subscription orchestrator | VAR | backend/orchestrator/subscription_manager.py | Eligible event icin WS subscribe, diff bazli |
| 7 | Evaluation loop | VAR | backend/orchestrator/evaluation_loop.py | Context olusturup RuleEngine.evaluate() cagirir |
| 8 | Orchestrator wiring | VAR | backend/orchestrator/wiring.py | Tum parcalari birlestiren Orchestrator class |

## Discovery Davranis Modeli (Baglayici Karar)

Discovery PTB mantigiyla calisir -- bul ve bekle:

```
1. Yeni 5dk slot basladi -> discovery tara
2. Event bulundu mu?
   EVET -> discovery DUR
          -> PTB fetch baslat
          -> WS subscribe
          -> evaluation dongusune al
          -> slot bitene kadar TEKRAR TARAMA YOK
          -> slot bittikten sonra -> adim 1'e don (yeni slot)
   HAYIR -> retry schedule: 2s->4s->8s->16s->10s->10s... (event bulunana kadar)
           -> health warning uret
           -> mevcut acik pozisyonlar ETKILENMEZ
```

Kritik kurallar:
- Event bulunduysa tekrar taramaya GEREK YOK
- Bulunmadiysa retry sonsuz -- sistem discovery failure'da DURMAZ
- Gereksiz API cagrisi YOK
- Discovery retry admin/advanced safety altinda, normal kullanici ayari DEGIL
- Mevcut acik pozisyonlar discovery failure yuzunden DURMAZ

## Zincir Tamamlanma Gecmisi

- v0.4.0: RuleEngine omurga
- v0.4.2: DiscoveryLoop + side mode wiring
- v0.4.3: EligibilityGate + SubscriptionManager + EvaluationLoop
- v0.4.4: Cleanup + health + expiration
- v0.4.5: Orchestrator wiring (tum parcalar baglandi)
- v0.4.6: Full chain calisiyor (delta PASS + ENTRY signal dogrulandi)
