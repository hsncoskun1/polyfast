"""Rule state enum — kural değerlendirme sonuçları.

Bağlayıcı semantik:
- pass: kural aktifti ve sağlandı
- fail: kural aktifti ve sağlanmadı
- waiting: kural aktif ama veri eksik / henüz değerlendirilemiyor
- disabled: kullanıcı bu kuralı kapattı, evaluation'a alınmadı

Disabled overall sonucu bozmaz ama "sağlandı" gibi de sayılmaz.
Disabled = PASS DEĞİL.
"""

from enum import Enum


class RuleState(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WAITING = "waiting"
    DISABLED = "disabled"


class OverallDecision(str, Enum):
    """Overall evaluation sonucu."""
    ENTRY = "entry"       # tüm enabled kurallar pass
    NO_ENTRY = "no_entry" # en az bir enabled kural fail
    WAITING = "waiting"   # fail yok ama en az bir kural waiting
    NO_RULES = "no_rules" # hiç enabled kural yok
