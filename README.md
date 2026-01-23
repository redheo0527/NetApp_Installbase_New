# NetApp Installbase Management System

NetApp 장비 설치 기반 관리 시스템입니다. 장비 정보, 이슈, RMA, 케이스 등을 관리할 수 있는 Django 기반 웹 애플리케이션입니다.

## 주요 기능

- **장비 관리**: 설치 기반 장비 정보 등록 및 관리
- **이슈 관리**: 이슈 등록, 수정, 추적
- **RMA 관리**: RMA 등록 및 배송/반납 상태 관리
- **케이스 관리**: 케이스 번호 기반 이슈 추적
- **스위치 관리**: 클러스터 스위치 정보 관리
- **대시보드**: 장비 현황 및 통계 정보 제공

## 기술 스택

- **Backend**: Django 4.2.27
- **Database**: PostgreSQL
- **Frontend**: HTML, CSS (Tailwind CSS), JavaScript
- **기타**: openpyxl (엑셀 다운로드), requests (API 호출)

## 설치 방법

### 1. 저장소 클론

```bash
git clone https://github.com/redheo0527/NetApp_Installbase_New.git
cd NetApp_Installbase_New
```

### 2. 가상 환경 생성 및 활성화

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate  # Windows
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 데이터베이스 설정

`config/settings.py` 파일에서 데이터베이스 설정을 수정하세요:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "your_database_name",
        "USER": "your_database_user",
        "PASSWORD": "your_database_password",
        "HOST": "127.0.0.1",
        "PORT": "5432",
    }
}
```

### 5. 마이그레이션 실행

```bash
python manage.py migrate
```

### 6. 슈퍼유저 생성 (선택사항)

```bash
python manage.py createsuperuser
```

### 7. 개발 서버 실행

```bash
python manage.py runserver
```

브라우저에서 `http://127.0.0.1:8000` 접속

## 프로젝트 구조

```
NetApp_Installbase_New/
├── config/                 # Django 프로젝트 설정
│   ├── settings.py         # 설정 파일
│   ├── urls.py            # URL 라우팅
│   └── wsgi.py            # WSGI 설정
├── installbase/           # 메인 앱
│   ├── models.py          # 데이터 모델
│   ├── views.py           # 뷰 로직
│   ├── forms.py           # 폼 정의
│   ├── templates/         # HTML 템플릿
│   └── migrations/        # 데이터베이스 마이그레이션
├── manage.py              # Django 관리 스크립트
├── requirements.txt       # Python 패키지 의존성
└── README.md             # 프로젝트 설명서
```

## 환경 변수

프로덕션 환경에서는 `SECRET_KEY`와 데이터베이스 비밀번호를 환경 변수로 관리하는 것을 권장합니다.

## 라이선스

이 프로젝트는 내부 사용을 위한 것입니다.

## 문의

프로젝트 관련 문의사항이 있으시면 이슈를 등록해주세요.
