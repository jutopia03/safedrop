# SafeDrop 배포용 이미지 (Render 무료 웹 서비스 기준, 다른 Docker 호스팅에도 그대로 사용 가능)
FROM python:3.12-slim
WORKDIR /app
# OCR 엔진(Tesseract)과 한국어 학습 데이터 — 인터넷·GPU 없이 CPU로 동작 (폐쇄망 서버에도 같은 방식으로 설치)
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-kor \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# 호스팅 서비스가 PORT 환경변수로 포트를 알려준다 (없으면 8000)
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
