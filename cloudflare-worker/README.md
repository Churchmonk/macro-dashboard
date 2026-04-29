# 1-click Refresh Worker — 배포 가이드

대시보드의 "⚡ 즉시 실행" 버튼이 GitHub Actions를 트리거하는 데 사용됩니다.
Cloudflare Worker가 Clerk JWT를 검증하고 GitHub Actions API를 호출합니다.

**무료 티어**: 일 100,000 요청 (개인 사용엔 충분)
**셋업 시간**: 약 15~20분

---

## 1. GitHub Personal Access Token (PAT) 발급

Worker가 GitHub Actions를 트리거하려면 PAT이 필요합니다.

1. https://github.com/settings/personal-access-tokens/new 이동 (fine-grained 발급 페이지)
2. **Token name**: `macro-dashboard-worker`
3. **Expiration**: 1 year (또는 원하는 기간 — 만료 시 갱신 필요)
4. **Repository access**: **"Only select repositories"** → `Churchmonk/macro-dashboard` 선택
5. **Permissions** → **Repository permissions**:
   - **Actions**: Read and Write ← 필수
   - 나머지: No access
6. 페이지 하단 **"Generate token"** 클릭
7. 생성된 토큰 (`github_pat_11...`) 복사 — **이 페이지를 떠나면 다시 못 봅니다.**

---

## 2. Cloudflare 계정 + Worker 생성

### 2-1. 계정 가입
https://dash.cloudflare.com/sign-up — 이메일 + 비밀번호로 무료 가입.

### 2-2. Worker 생성
1. 로그인 후 좌측 사이드바 **Workers & Pages** 클릭
2. **"Create application"** → **"Create Worker"**
3. 이름 입력 (예: `macro-refresh`) — 이 이름이 URL이 됨: `macro-refresh.<your-subdomain>.workers.dev`
4. **"Deploy"** 클릭 (기본 Hello World 코드로 일단 배포)
5. 배포 후 **"Edit code"** 클릭

### 2-3. worker.js 코드 붙여넣기
1. 편집기 좌측의 `worker.js` 파일 내용을 모두 삭제
2. 이 폴더의 [worker.js](./worker.js) 파일 내용 전체를 복사 → 붙여넣기
3. 우상단 **"Save and Deploy"** 클릭

---

## 3. 환경변수 (Secrets) 설정

Worker 페이지에서 **Settings → Variables and Secrets** 메뉴 (또는 `Settings → Environment Variables`).

다음 4개를 **"Encrypt"** (Secret) 으로 추가:

| Variable name | Value | 설명 |
|---|---|---|
| `GITHUB_PAT` | `github_pat_11...` (1단계에서 발급한 토큰) | Encrypted 필수 |
| `CLERK_JWKS_URL` | `https://settling-albacore-3.clerk.accounts.dev/.well-known/jwks.json` | 일반 변수 OK |
| `ALLOWED_ORIGIN` | `https://churchmonk.github.io` | 일반 변수 OK |
| `ADMIN_EMAIL` | `aktmdgus9608@gmail.com` | (선택) 빈 값이면 모든 인증 사용자 허용 |

각 항목 입력 후 **"Save"** 또는 **"Save and Deploy"**.

> **주의**: `GITHUB_PAT`은 반드시 **"Encrypt"** 옵션 켜기. Plain variable로 두면 Cloudflare 대시보드에서 평문 노출됨.

---

## 4. Worker URL 확인 + 헬스체크

배포 후 Worker 화면 상단에 URL이 표시됩니다:
```
https://macro-refresh.<your-subdomain>.workers.dev
```

브라우저에서 그 URL에 GET 접속해보면:
```json
{"service":"macro-dashboard-refresh","status":"ok","allowed_modes":["daily","weekly","monthly"]}
```
이렇게 떠야 합니다.

---

## 5. 대시보드에 Worker URL 등록

URL을 알려주시면 [index.html](../index.html)의 `window.WORKER_URL` 변수에 박고 push합니다.

```javascript
// 현재 (아직 비어있음)
window.WORKER_URL = "";

// 배포 후 교체
window.WORKER_URL = "https://macro-refresh.<your-subdomain>.workers.dev";
```

---

## 6. 검증

대시보드 로그인 → 헤더 **"🔄 강제 갱신 ▾"** 드롭다운 → 상단 파란 박스 **"⚡ 즉시 실행 (1-click)"** 영역의 **Daily** 버튼 클릭.

기대 동작:
- "⟳ daily 트리거 중..." → "✓ daily 워크플로 실행됨 (1~3분 후 자동 반영)"
- 1~3분 후 데이터 자동 갱신 + history 탭에 새 entry 추가됨

실패 시:
- `⚠ 로그인 필요`: Clerk 세션 만료 — 재로그인
- `✗ 401 Invalid token`: Clerk JWKS URL 오타 또는 Clerk 도메인 변경
- `✗ 403 Forbidden`: ADMIN_EMAIL 화이트리스트와 로그인 이메일 불일치
- `✗ 502 GitHub API failed`: PAT 권한 부족 또는 만료

---

## PAT 갱신 (1년 후)

1. https://github.com/settings/personal-access-tokens 이동
2. 만료된 토큰의 **"Regenerate"** 또는 새로 발급
3. Cloudflare Worker → Variables → `GITHUB_PAT` 값 교체 → Save
