# DNS Monitor

MX 레코드와 MX 대상 도메인의 A 레코드를 주기적으로 조회하여 변경 이벤트를 감지하고,
SQLite에 이력을 저장하며 웹 화면/API로 조회할 수 있는 모듈입니다.

## 기능

- 도메인별 MX 레코드 조회
- MX 레코드에서 추출한 메일 서버 도메인의 A 레코드 조회
- 이전 성공 스냅샷과 비교한 변경 감지(MX/A 추가/삭제)
- 변경 이벤트 발생 시 이메일 알림(환경변수 기반 SMTP)
- SQLite 기반 영속 저장(외부 DB 미들웨어 불필요)
- FastAPI + Jinja2 기반 웹 대시보드

## 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## SMTP 설정(선택)

환경변수 미설정 시 알림은 `skipped` 로 기록됩니다.

- `SMTP_HOST`
- `SMTP_PORT` (기본 587)
- `SMTP_USER`
- `SMTP_PASSWORD`
- `ALERT_FROM`
- `ALERT_TO`

## 주요 API

- `POST /domains` 도메인 등록
- `GET /domains` 도메인 목록
- `POST /domains/{domain_id}/run` 즉시 점검
- `GET /domains/{domain_id}/events` 변경 이벤트 조회
- `GET /` 웹 대시보드

## 저장 파일

- `dns_monitor.db`: SQLite DB 파일
