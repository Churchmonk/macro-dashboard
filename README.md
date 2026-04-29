# DS Macro Jungle

매크로 투자 프레임워크 — Fed 유동성·금리·변동성·크레딧·인플레이션·경기사이클 11개 지표군을 한 화면에 통합한 정적 대시보드.

**Live**: https://churchmonk.github.io/macro-dashboard/ (로그인 필요)

---

## 시스템 구조

```
┌─────────────────────────────────────────────────────────────┐
│ 데이터 소스                                                  │
│   EODHD API · FRED API · Scrapling(TradingEconomics)        │
│   CFETS(중국 LPR) · Google News RSS(ISM PMI fallback)       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 수집 (3가지 트리거)                                          │
│   1. GitHub Actions cron (자동, 메인)                       │
│   2. Cloudflare Worker (1-click 즉시, admin 전용)           │
│   3. 로컬 .bat (PC 켜져있을 때)                             │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 산출물 (git에 commit/push)                                   │
│   data.json (현재값 + 24개월 시계열)                         │
│   history.json (최근 100건 갱신 로그)                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 표시                                                          │
│   GitHub Pages 정적 호스팅 + Clerk 로그인 게이트             │
└─────────────────────────────────────────────────────────────┘
```

---

## 파일 구조

```
macro_dashboard/
├── fetch_data.py              # 데이터 수집 메인 (--full/--daily/--weekly/--monthly)
├── data.json                  # 현재 데이터 (git에 commit, GitHub Pages가 fetch)
├── history.json               # 갱신 기록 100건 (자동 누적)
├── index.html                 # 단일 SPA 대시보드 (Chart.js + Clerk)
├── requirements.txt           # Python 의존성
│
├── .env.local                 # API 키 (gitignored, 로컬 전용)
├── .env.example               # 키 템플릿 (commit)
│
├── update_full.bat            # 로컬 수동 갱신 (전체)
├── update_daily.bat           # 로컬 수동 갱신 (일별)
├── update_weekly.bat          # 로컬 수동 갱신 (주간)
├── update_monthly.bat         # 로컬 수동 갱신 (월간)
├── update.bat                 # 인터랙티브 풀 갱신 + push
├── start_server.bat           # 로컬 미리보기 서버
├── register_tasks.bat         # Windows 작업 스케줄러 등록 (선택)
├── unregister_tasks.bat       # 등록 해제
│
├── .github/workflows/         # GitHub Actions 자동화
│   ├── daily.yml              # KST 08:10 매일
│   ├── weekly.yml             # KST 금 06:30 매주
│   └── monthly.yml            # KST 매달 2일 09:00 + 21일 11:00
│
└── cloudflare-worker/         # 1-click 즉시 갱신용
    ├── worker.js              # Clerk JWT 검증 + GitHub API 트리거
    └── README.md              # 배포 가이드
```

---

## 데이터 모드

`fetch_data.py`는 4가지 모드. 각 모드는 자기 카테고리 키만 갱신하고 나머지는 기존 값 보존.

| 모드 | 갱신 키 | 발표 주기 |
|---|---|---|
| **`--daily`** | vix · move · skew · hyg · us2y/3m/5y/10y/30y · spread_10y2y · jp10y · us_jp_spread_bp · rrp · ig_oas · hy_oas · bei_10y · real_rate_10y · spx · usdjpy · dxy · gold · wti_uso | 영업일 |
| **`--weekly`** | fed_balance · tga · bank_reserves · rmp · net_liq_series · wres_series · net_liq_spx · jobless_claims | Fed H.4.1 매주 목 16:30 ET |
| **`--monthly`** | fed_funds · unemployment · nfp · jolts · cpi_annual · ism_pmi · china_lpr | NFP/CPI/ISM/JOLTS = 매달 / 중국 LPR = 매달 20일 |
| **`--full`** | 위 셋을 한 번에 | 전체 |

---

## 셋업 (새 PC에서 처음 시작)

### 1. 의존성

```bash
pip install -r requirements.txt
scrapling install     # ISM PMI 크롤링용 Camoufox 브라우저 다운로드 (~200MB)
```

### 2. API 키 입력

`.env.example` → `.env.local`로 복사 후 키 입력:

```bash
cp .env.example .env.local
# .env.local 파일 편집해서 EODHD_API_TOKEN, FRED_API_KEY 입력
```

발급:
- **EODHD**: https://eodhd.com/financial-apis/  (가입 → API Token)
- **FRED**: https://fred.stlouisfed.org/docs/api/api_key.html  (무료, 즉시)

### 3. 동작 확인

```bash
python -X utf8 fetch_data.py --daily
```

성공 시 `data.json` + `history.json` 갱신, 콘솔에 22개 키 갱신 메시지.

### 4. 로컬 미리보기

```bash
start_server.bat    # 또는 python -m http.server 8000
```
→ http://localhost:8000

---

## 갱신 메커니즘

### A. 자동 (GitHub Actions cron) — 메인

| 워크플로 | 실행 시각 (KST) | UTC cron |
|---|---|---|
| daily.yml | 매일 08:10 | `'10 23 * * *'` |
| weekly.yml | 매주 금 06:30 | `'30 21 * * 4'` |
| monthly.yml | 매달 2일 09:00 + 21일 11:00 | `'0 0 2 * *'`, `'0 2 21 * *'` |

각 워크플로:
1. checkout + Python 환경
2. `python -X utf8 fetch_data.py --<mode>` 실행
3. data.json + history.json 변경분 commit & push
4. 실패 시 GitHub Issue 자동 생성 (`auto-failed` 라벨)

**race-safe**: `concurrency: macro-data-update` group + 3회 재시도 (충돌 시 reset hard origin/main 후 재실행).

### B. 1-click 즉시 갱신 (admin only)

대시보드 우상단 **🔄 강제 갱신 ▾** 드롭다운 → ⚡ 즉시 실행 영역 → Daily/Weekly/Monthly 클릭.

흐름:
```
대시보드 (admin 로그인 상태)
  ↓ Clerk session JWT 발급
Cloudflare Worker (https://noisy-scene-bdc8.aktmdgus9608.workers.dev)
  ↓ JWT 검증 (RS256, JWKS) + admin email allowlist
GitHub Actions API (workflow_dispatch with PAT)
  ↓
같은 cron 워크플로 즉시 실행
```

**Worker 환경변수** (Cloudflare Dashboard에서 설정):
- `GITHUB_PAT` (Encrypt) — fine-grained PAT, repo `Churchmonk/macro-dashboard`, Actions: Read+Write
- `CLERK_JWKS_URL` — `https://settling-albacore-3.clerk.accounts.dev/.well-known/jwks.json`
- `ALLOWED_ORIGIN` — `https://churchmonk.github.io`
- `ADMIN_EMAIL` — `aktmdgus9608@gmail.com` (선택, 비우면 모든 인증 사용자 허용)

자세한 배포: [cloudflare-worker/README.md](./cloudflare-worker/README.md)

### C. 수동 (4-click, GitHub UI)

대시보드 강제 갱신 드롭다운 하단 → GitHub Actions 페이지로 이동 → "Run workflow" 두 번 클릭.

### D. 로컬 수동 (`update_*.bat`, PC 켜져있을 때)

```bash
update_full.bat       # 전체 갱신 + git push
update_daily.bat      # 일별만
update_weekly.bat     # 주간만
update_monthly.bat    # 월간만
```

각 .bat은 `logs/<mode>.log`에 출력 기록.

---

## 인증 (Clerk)

**Clerk Dashboard**: https://dashboard.clerk.com/last-active

**구성**:
- Restricted mode ON → admin이 초대한 사용자만 가입 가능
- 이메일 + 비밀번호 + (선택) Google/GitHub OAuth
- Publishable key는 [index.html](./index.html)에 hardcode (`pk_test_...` 안전)
- Secret key는 절대 commit 금지

**Admin** (`aktmdgus9608@gmail.com`) 만 보이는 메뉴:
- 헤더 우상단 "🔄 강제 갱신 ▾" 드롭다운 자체
- 그 안 ⚙️ Admin 섹션 (사용자 관리, 가입 제한 설정)

### 새 사용자 발급

1. Clerk Dashboard: https://dashboard.clerk.com/last-active?path=users
2. **"Create user"** 또는 **"Invite"** 클릭
3. 이메일 입력 → 초대 메일 자동 발송
4. 초대받은 사람이 메일 링크 클릭 → 비밀번호 설정 → 로그인 가능

### Restricted mode 끄기/켜기
https://dashboard.clerk.com/last-active?path=user-authentication/restrictions

---

## 알림 (실패 감지)

GitHub Actions가 실패하면 다음 흐름:

1. 워크플로 yml의 `Notify on failure` step이 동작
2. 같은 모드의 open issue가 있으면 **코멘트만 추가** (spam 방지)
3. 없으면 **새 issue 생성** (라벨: `auto-failed`, `<mode>`)
4. GitHub의 watch 설정에 따라 **메일 자동 발송**

→ 메일 알림 받으려면 https://github.com/Churchmonk/macro-dashboard/subscription 에서 "All Activity" 또는 "Custom → Issues" 체크.

이슈 해결 후 close하면, 다음 실패 시 새 issue로 다시 알림.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `[ERROR] EODHD_API_TOKEN ... 없습니다` | 환경변수 누락 | `.env.local` 파일 확인, GitHub Actions라면 Secrets 확인 |
| 워크플로 push 실패 (rejected non-fast-forward) | 다른 워크플로가 먼저 push (race) | 자동으로 3회 재시도. 그래도 실패면 수동으로 다시 돌림 |
| ISM PMI가 RSS 값으로 잡힘 | TradingEconomics 차단 | GitHub Actions의 datacenter IP가 막힌 경우. 다음 cron에서 자동 재시도 |
| 1-click 즉시 갱신 "401 Invalid token" | Clerk session 만료 또는 JWKS URL 오타 | 재로그인 + Worker `CLERK_JWKS_URL` 확인 |
| 1-click 즉시 갱신 "403 Forbidden" | admin email allowlist 불일치 | Worker `ADMIN_EMAIL` 확인 또는 비움 |
| 1-click 즉시 갱신 "502 GitHub API" | PAT 권한 부족 또는 만료 | PAT 재발급 + Worker `GITHUB_PAT` 갱신 |
| 대시보드가 옛 데이터 표시 | 브라우저 캐시 | `Ctrl+Shift+R` |
| 로그인 후 GitHub Pages 404 | Clerk redirect URL이 root로 감 | `index.html`의 mountSignIn `afterSignInUrl` 옵션 확인 |

---

## 운영 체크리스트

### 정기 점검
- [ ] **연 1회**: GitHub PAT 만료 확인 (https://github.com/settings/personal-access-tokens) → Cloudflare Worker `GITHUB_PAT` 갱신
- [ ] **반기 1회**: EODHD/FRED 키 정상 동작 확인
- [ ] **월 1회**: `auto-failed` 라벨 issue 확인 (지속 실패하는 패턴 있는지)

### 모니터링 포인트
- GitHub Actions 페이지: https://github.com/Churchmonk/macro-dashboard/actions
- Cloudflare Worker logs: Dashboard → Worker → Observability → Logs
- 대시보드 갱신 기록 탭 (📜 갱신 기록): 최근 100건 자동 표시

### Anti-패턴
- ❌ Secret Key (`sk_test_...`)를 채팅/repo/메일에 노출 금지
- ❌ `fetch_data.py`를 직접 commit (`.gitignore` 안 넣기) → 환경변수 시스템 사용
- ❌ `--no-verify`로 hook 우회 — 신호가 의미 있어서 그렇게 동작하는 것
- ❌ data.json을 사람이 직접 수정 — 다음 cron이 덮어씀

---

## 확장 가능한 방향

- **임계값 알림**: VIX 25 돌파 시 메일 (Supabase + cron 추가)
- **사용자별 즐겨찾기/노트**: Supabase Auth + Postgres
- **모바일 반응형**: 현재 데스크톱 기준
- **데이터 본격 비공개**: GitHub Pro ($4/월 private Pages) 또는 Cloudflare Pages 이전
- **추가 지표**: 한국 KOSPI · 변동성 · 외인 매매, 원자재 (구리/은), 부동산 (REITs) 등

---

## License & 면책

내부 투자 참고용. 본 자료는 투자 결정의 근거가 아니며, 모든 투자 책임은 본인에게 있습니다.

---

**Last updated**: 2026-04-29
