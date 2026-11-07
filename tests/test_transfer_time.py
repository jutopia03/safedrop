"""감사 로그 시각은 서버 시간대(UTC)와 관계없이 한국 시간으로 기록한다."""
from datetime import datetime, timedelta, timezone

from backend.app import transfer


def test_now_kst_is_korea_time():
    got = datetime.strptime(transfer.now_kst(), "%Y-%m-%d %H:%M:%S")
    expect = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=9)
    assert abs((got - expect).total_seconds()) < 5
