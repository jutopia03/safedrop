"""배포용 비밀값 생성: 서명 키(PERMIT_SIGNING_KEY)와 세션 키(SESSION_SECRET).

출력값을 배포 환경(Render Environment, 사내 서버 .env)에 넣는다. 저장소에는 절대 커밋하지 않는다.
실행: python scripts/gen_secrets.py
"""
import base64
import secrets

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
print("PERMIT_SIGNING_KEY=" + base64.b64encode(pem).decode())
print("SESSION_SECRET=" + secrets.token_hex(32))
