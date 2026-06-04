# homelab-gitops

GitOps repository for the home lab k3s cluster, managed by ArgoCD using the App-of-Apps pattern.

---

## Repository Structure

```
homelab-gitops/
├── bootstrap/
│   └── cluster-root.yml      # Root Application — bootstraps all apps in apps/
├── apps/
│   ├── argocd-config.yml     # ArgoCD self-configuration (ingress, params)
│   └── hermes.yml            # Hermes Telegram Bot
└── k8s/
    └── base/
        ├── argocd/
        │   ├── argocd-ingress.yml    # Traefik ingress for ArgoCD UI
        │   └── kustomization.yml     # insecure mode patch
        └── hermes/
            ├── namespace.yml
            ├── configmap.yml         # Ollama endpoint, 모델 설정, 알림 시각
            ├── secret.yml            # Telegram 토큰, Gemini API 키 (REPLACE_ME)
            ├── pvc.yml               # SQLite DB 저장소
            ├── deployment.yml        # Hermes 봇 앱
            └── kustomization.yml
```

---

## GitOps Flow

```
Git push
    │
    ▼
ArgoCD detects change (polling / webhook)
    │
    ├── root-app watches apps/
    │       ├── argocd-config  →  k8s/base/argocd/
    │       └── hermes         →  k8s/base/hermes/
    │
    └── auto sync (prune + selfHeal)
```

---

## Bootstrap

ArgoCD itself is installed manually (once). After that, apply the root Application to hand over control to GitOps:

```bash
kubectl apply -f bootstrap/cluster-root.yml
```

---

## Applications

| App | Namespace | Source Path | Status |
|---|---|---|---|
| argocd-self-config | argocd | `k8s/base/argocd` | Active |
| hermes | hermes-system | `k8s/base/hermes` | WIP |

---

## Hermes Bot Architecture

```
텔레그램 메시지
      ↓
  Hermes Bot (K8s)
      ├── 일반 메시지  → Ollama (Mac, qwen2.5:14b)
      └── /gemini 접두어 → Gemini Flash API

      + 예약 정보 → SQLite (PVC /app/data)
      + 매월 4일 알림 → APScheduler → 텔레그램 메시지 발송
```

### 시작 전 필수 설정

1. [k8s/base/hermes/secret.yml](k8s/base/hermes/secret.yml) 에서 `REPLACE_ME` 값 교체
   - `TELEGRAM_BOT_TOKEN`
   - `GEMINI_API_KEY`

2. [k8s/base/hermes/configmap.yml](k8s/base/hermes/configmap.yml) 에서 Ollama IP 설정
   - `OLLAMA_BASE_URL`: Mac의 실제 IP 주소로 변경

3. Hermes 봇 앱 Docker 이미지 빌드 및 푸시
   - `ghcr.io/ohjinn/hermes-bot:latest`

---

## Cluster Info

- **Distribution:** k3s
- **Ingress:** Traefik (built-in k3s)
- **ArgoCD mode:** insecure (HTTP) — TLS terminated at Traefik or Cloudflare Tunnel

---

## Roadmap

- [ ] Hermes 봇 앱 Python 코드 작성 및 Docker 이미지 빌드
- [ ] Secret을 SealedSecrets 또는 External Secrets로 교체 (git 안전성)
- [ ] Add Prometheus + Grafana stack
- [ ] Implement canary deployment strategy via ArgoCD Rollouts
