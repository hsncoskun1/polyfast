# Stale Behavior Map — Bağlayıcı Davranış Haritası

## Outcome Stale İse
- PriceRule → WAITING
- SpreadRule → WAITING
- Take Profit → hesaplanamaz (held-side outcome gerekli)
- Stop Loss → hesaplanamaz (held-side outcome gerekli)
- Force Sell PnL → hesaplanamaz (outcome gerekli)
- Force Sell Time → ÇALIŞIR (zamana bakar, outcome gerektirmez)

## Coin USD Stale İse
- DeltaRule → WAITING
- Delta bazlı entry açılamaz
- Diğer outcome bazlı alanlar kendi veri durumlarına göre devam eder

## PTB Yoksa (henüz alınmamış veya lock edilmemiş)
- DeltaRule → WAITING
- PTB alındığında lock olur ve coin canlı fiyat varsa delta hesaplanabilir

## Stale Safety Override
- Eğer outcome stale ise ve force sell PnL seçili olsa bile hesaplanamıyorsa
- Force sell time TEK BAŞINA safety override olarak davranabilir
- Yani stale durumda time force sell çıkışı BLOKE OLMAZ
- Bu advanced/global safety policy olarak ele alınacak

## Genel Kurallar
- Stale veri canlı kabul edilmez
- Stale durumda ilgili kural WAITING'e düşer
- WAITING olan kural PASS veya FAIL demez
- Stale protection kaldırılmıyor
