# ETNS 할일관리 (Flask To-Do App)

Flask + SQLite 기반의 간단한 할일관리 웹앱입니다.

## 기능
- 할 일 추가 / 수정 / 삭제
- 완료 체크 토글
- 전체 / 미완료 / 완료 필터
- 완료된 항목 일괄 삭제

## 실행 방법

```bash
cd ETNS_TODO_APP
python -m venv venv
./venv/Scripts/activate   # Windows PowerShell: venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

브라우저에서 http://127.0.0.1:5000 접속

## 구조
```
ETNS_TODO_APP/
├── app.py               # Flask 앱 & 라우트
├── requirements.txt
├── templates/
│   └── index.html
├── static/
│   └── css/style.css
└── instance/
    └── todo.db          # 실행 시 자동 생성되는 SQLite DB
```
