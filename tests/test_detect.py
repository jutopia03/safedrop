"""정규식 + 검증 탐지 (v0 → v0.1 문맥 보강)."""
from backend.app.detect import detect


def types(text):
    return [(e.type, e.text) for e in detect(text)]


def test_rrn_and_foreigner_number():
    assert types("주민 900101-1234567") == [("RRN", "900101-1234567")]
    assert types("외국인 010203-5123456") == [("FRN", "010203-5123456")]
    assert types("주민번호 900101 - 1234567")[0][0] == "RRN"


def test_rrn_without_context_needs_checksum():
    assert types("번호 900101-1234568") == [("RRN", "900101-1234568")]   # 검증식 통과
    assert types("번호 900101-1234567") == []                           # 문맥도 검증식도 없음


def test_rrn_like_serial_and_barcode_are_not_rrn():
    table = "자산번호 | 품목 | 제조번호(LOT)\nDV-NB-0031 | 노트북 | 241105-1000234\n※ 바코드(EAN-13): 8801234500311"
    assert types(table) == []


def test_rrn_in_table_with_header_keyword():
    assert types("성명 | 주민등록번호\n도윤슬 | 950312-2345678") == [("RRN", "950312-2345678")]


def test_rrn_invalid_date_is_ignored():
    assert types("991399-1234567") == []          # 13월 99일은 없는 날짜


def test_phone_variants_and_landline_excluded():
    got = types("010-1234-5678 / 010 1234 5678 / 01012345678 / 대표 042-123-4567")
    assert [t for t, _ in got] == ["PHONE", "PHONE", "PHONE"]   # 유선(대표번호)은 개인 연락처 아님


def test_card_luhn_or_card_keyword():
    assert types("결제 4111-1111-1111-1111") == [("CARD", "4111-1111-1111-1111")]     # Luhn 통과
    assert types("결제 1234-5678-9012-3456") == []                                   # Luhn 실패 + 키워드 없음
    assert types("사용 카드: 4890123456781234") == [("CARD", "4890123456781234")]      # '카드' 문맥
    assert types("유류비 결제 법인카드 4518-0210-7733-9064") == []                       # 회사 카드


def test_passport_requires_nearby_keyword():
    got = types("여권번호: M12345678, 제품코드 M87654321")
    assert got == [("PASSPORT", "M12345678")]


def test_account_requires_bank_keyword_and_date_not_account():
    assert types("신한 110-234-567890") == [("ACCOUNT", "110-234-567890")]
    assert types("주문번호 110-234-567890") == []
    assert types("발령일 2026-11-15") == []


def test_email_and_driver():
    got = types("메일 a.b@ex.co.kr 면허 11-12-345678-90")
    assert ("EMAIL", "a.b@ex.co.kr") in got and ("DRIVER", "11-12-345678-90") in got


def test_role_mailbox_is_not_personal_email():
    got = types("문의: hr@codev.example / pay-ops@codev.example / 공용 메일 team.kim@codev.example / minho.seo@codev.example")
    assert got == [("EMAIL", "minho.seo@codev.example")]


def test_request_id_and_timestamp_are_not_account():
    assert types("재지급 완료 (이체 요청ID 20261029160012)") == []
    assert types("이체 일시 20261102143840") == []


def test_phone_bracket_and_international():
    got = types("연락처 (010)8842-3165, +82-10-5527-1093")
    assert got == [("PHONE", "(010)8842-3165"), ("PHONE", "+82-10-5527-1093")]


def test_old_passport_format():
    assert types("여권번호: C4829175") == [("PASSPORT", "C4829175")]
