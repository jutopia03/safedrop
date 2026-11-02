"""정규식 + 검증 탐지 (v0)."""
from backend.app.detect import detect


def types(text):
    return [(e.type, e.text) for e in detect(text)]


def test_rrn_and_foreigner_number():
    assert types("주민 900101-1234567") == [("RRN", "900101-1234567")]
    assert types("외국인 010203-5123456") == [("FRN", "010203-5123456")]
    assert types("공백 900101 - 1234567")[0][0] == "RRN"


def test_rrn_invalid_date_is_ignored():
    assert types("991399-1234567") == []          # 13월 99일은 없는 날짜


def test_phone_variants_and_landline_excluded():
    got = types("010-1234-5678 / 010 1234 5678 / 01012345678 / 대표 042-123-4567")
    assert [t for t, _ in got] == ["PHONE", "PHONE", "PHONE"]   # 유선(대표번호)은 개인 연락처 아님


def test_card_requires_luhn():
    assert types("카드 4111-1111-1111-1111") == [("CARD", "4111-1111-1111-1111")]
    assert types("카드 1234-5678-9012-3456") == []


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
