# homelab-gitops 아키텍처

## 전체 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                          인터넷                                   │
│                                                                   │
│      개발자 브라우저           GitHub Actions                     │
│            │                        │                            │
│            └───────────┬────────────┘                            │
│                        ↓                                         │
│              ┌──────────────────┐                                │
│              │  Cloudflare Edge │  ← DNS: registry.newhojin.com │
│              │  (TLS 종료)      │    Cloudflare 인증서 처리      │
│              └────────┬─────────┘                                │
│                       │ Cloudflare Tunnel (아웃바운드 연결)       │
└───────────────────────│──────────────────────────────────────────┘
                        │
┌───────────────────────│──────────────────────────────────────────┐
│  k3s 클러스터         ↓                                           │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  cloudflared (Deployment) — k3s 전용 터널                │   │
│  └─────────────────────┬────────────────────────────────────┘   │
│                         ↓                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Traefik Ingress                                          │   │
│  │  registry.newhojin.com → Harbor                          │   │
│  └───────────────┬──────────────────────────────────────────┘   │
│                  │                                                │
│         ┌────────┴────────┐                                      │
│         ↓                 ↓                                      │
│   ┌───────────┐   ┌────────────────────────────────────────┐   │
│   │  Harbor   │   │  cert-manager                          │   │
│   │  레지스트리│   │  ClusterIssuer → Certificate 발급      │   │
│   │           │   │  → Secret에 저장 → Traefik에서 사용    │   │
│   └─────┬─────┘   └────────────────────────────────────────┘   │
│         │ pull                                                    │
│         ↓                                                         │
│   ┌─────────────────────────────────────────────────────┐       │
│   │  Hermes Bot (Deployment)                            │       │
│   │  image: registry.newhojin.com/hermes/hermes-bot     │       │
│   │    ↓                                                │       │
│   │  LiteLLM → Ollama(맥북 로컬) / Gemini(폴백)         │       │
│   └─────────────────────────────────────────────────────┘       │
│                                                                   │
│   ┌─────────────────────────────────────────────────────┐       │
│   │  ArgoCD — homelab-gitops repo 감시                  │       │
│   │  변경 감지 시 자동 배포 (prune + selfHeal)           │       │
│   └─────────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  GitHub (hermes-bot repo)                                        │
│                                                                   │
│  코드 push                                                        │
│    → GitHub Actions 트리거                                        │
│    → Docker 이미지 빌드                                           │
│    → registry.newhojin.com 로그인 (Robot Account 토큰)           │
│    → Harbor에 이미지 push                                         │
│    → ArgoCD가 감지 → Hermes 자동 재배포                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## TLS 인증서 흐름

> Cloudflare 인증서는 **사용자 ↔ Cloudflare 구간**만 커버한다.  
> Docker/k3s가 Harbor에 직접 연결할 때는 **Harbor 서버 자체의 인증서**가 필요하다.  
> 이걸 자동으로 발급/갱신해주는 게 cert-manager + Let's Encrypt.

```
cert-manager          Cloudflare DNS API        Let's Encrypt
    │                        │                       │
    │── TXT 레코드 생성 ───→ │                       │
    │                        │ ←── DNS 조회 ──────── │
    │                        │ ──→ 레코드 확인 ─────→│
    │ ←────────────────────────── 인증서 발급 ─────── │
    │   TXT 레코드 삭제      │                       │
    ↓
Secret에 저장 → Traefik / Harbor에서 사용
(90일마다 자동 갱신)
```

### DNS-01 Challenge를 쓰는 이유

| 방식 | 검증 방법 | 서버 외부 노출 필요 | 와일드카드 발급 |
|------|-----------|---------------------|-----------------|
| HTTP-01 | 서버에 파일 업로드 후 Let's Encrypt가 HTTP 접속 | **필요** | 불가 |
| DNS-01 | DNS TXT 레코드 생성 후 Let's Encrypt가 DNS 조회 | **불필요** | 가능 |

k3s가 내부망에 있어도 Cloudflare API로 DNS만 편집할 수 있으면 공인 인증서를 받을 수 있다.  
`*.newhojin.com` 와일드카드 인증서 한 장으로 모든 서브도메인에 재사용 가능.

---

## ArgoCD 배포 순서 (sync-wave)

의존성이 있어서 순서대로 배포해야 한다.

```
wave 0  cert-manager        CRD 먼저 설치
  ↓
wave 1  cloudflared         외부 접근 경로 확보
        ClusterIssuer       cert-manager CRD 설치 후 생성 가능
  ↓
wave 2  Harbor              인증서 발급 완료 후 배포
  ↓
wave 3  Hermes              Harbor에서 이미지 pull
        LiteLLM
```

---

## 접근 제어 구조

```
외부 → registry.newhojin.com
  1차: Cloudflare Access (웹 UI 접근 시 이메일 인증)
  2차: Harbor 자체 인증 (Robot Account ID/PW)

GitHub Actions → Harbor push
  Harbor Robot Account (push 전용 토큰)
  → Repository Secrets에 저장

k3s → Harbor pull
  Harbor Robot Account (pull 전용 토큰)
  → imagePullSecret으로 등록
```

---

## 컴포넌트별 역할 요약

| 컴포넌트 | 역할 |
|----------|------|
| Cloudflare Tunnel | 포트 오픈 없이 외부 접근 가능하게 하는 터널 |
| Cloudflare 인증서 | 사용자 ↔ Cloudflare 구간 HTTPS |
| cert-manager | k3s 내부 서비스용 Let's Encrypt 인증서 자동 발급/갱신 |
| Traefik | k3s 기본 Ingress 컨트롤러, TLS 종료 |
| Harbor | 프라이빗 컨테이너 레지스트리 |
| ArgoCD | GitOps — repo 변경사항 자동 배포 |
| LiteLLM | LLM 라우터 (Ollama → Gemini 폴백) |
| Hermes Bot | Telegram 봇, LiteLLM 통해 LLM 호출 |
