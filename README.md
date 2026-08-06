# homelab-gitops

k3s 클러스터의 GitOps 매니페스트 레포. ArgoCD App-of-Apps 패턴으로 모든 앱을 Git 기반으로 관리한다.

---

## Repository Structure

```
homelab-gitops/
├── bootstrap/
│   └── cluster-root.yml      # 루트 Application — apps/ 를 감시
├── apps/                     # 앱마다 Application 매니페스트 하나
│   ├── argocd-config.yml
│   ├── cert-manager.yml
│   ├── hermes.yml
│   ├── investwells.yml
│   ├── litellm.yml
│   ├── parking.yml
│   └── traefik-config.yml
└── k8s/base/                 # 각 Application 이 가리키는 실제 매니페스트
    ├── argocd/
    ├── hermes/
    ├── investwells/
    ├── litellm/
    ├── parking/
    └── traefik/
```

---

## GitOps Flow

```
Git push
    │
    ▼
ArgoCD 가 변경 감지 (폴링, 약 3분)
    │
    ├── root-app 이 apps/ 를 보고 각 Application 을 생성·갱신
    │
    └── 각 Application 이 자기 k8s/base/<app> 디렉토리를 동기화
        (automated, prune + selfHeal)
```

**ArgoCD 는 레지스트리가 아니라 Git 을 본다.** 새 앱을 붙일 때 이 점이 중요하다.
Deployment 가 `:latest` 같은 가변 태그를 쓰면, 이미지를 새로 올려도 Git 에는
아무 변화가 없어서 ArgoCD 는 배포할 게 없다고 판단한다. 이 상태에서는 UI 에서
Sync 를 눌러도 차이가 없어 아무 일도 일어나지 않는다.

Git 이 "지금 무엇이 배포돼 있는지"를 표현하게 만드는 방법은 두 가지다.

| 방식 | 쓰는 앱 | 원리 |
|---|---|---|
| 이미지 태그 = 커밋 sha | `parking` | 앱 레포의 CI 가 새 태그를 이 레포에 커밋 |
| 소스를 ConfigMap 으로 | `investwells` | `configMapGenerator` 가 소스 해시를 ConfigMap 이름에 붙임 |

---

## Applications

| 앱 | 네임스페이스 | 호스트 | 이미지 | 상태 |
|---|---|---|---|---|
| argocd-self-config | `argocd` | `argocd.newhojin.com` | — | Active |
| cert-manager | `cert-manager` | — | upstream chart | Active |
| parking | `parking-system` | `wizparking.newhojin.com` | `ghcr.io/ohjinn/wizparking:<sha>` | Active |
| investwells | `investwells-system` | `nuri.newhojin.com` | `python:3.12-slim` + ConfigMap 소스 | Active |
| traefik-config | `kube-system` | — | k3s 내장 | Active |
| litellm | `litellm-system` | — | `ghcr.io/berriai/litellm` (digest 고정) | Active |
| hermes | `hermes-system` | — | `ghcr.io/ohjinn/hermes-bot:latest` | 중단 — 이미지가 push 된 적 없음 |

---

## parking — 수원 주차 자동예약

KT 위즈파크 주차 잔여 대수를 감시하다가 취소표가 나오는 순간 예약을 잡고,
결과를 텔레그램으로 알린다.

앱 소스와 이미지 빌드는 [Ohjinn/wizparking](https://github.com/Ohjinn/wizparking) 에 있고,
이 레포는 매니페스트만 갖는다.

```
wizparking push
   → self-hosted 러너가 ghcr.io/ohjinn/wizparking:<sha> 를 빌드해서 push
   → 같은 잡이 그 태그를 여기 k8s/base/parking/deployment.yml 에 커밋
   → ArgoCD 가 그 커밋을 보고 배포
```

**CI 가 이 레포에 커밋하므로, 작업 전에 `git pull` 을 먼저 해야 한다.**
가만히 있어도 로컬이 뒤처지는 구조가 됐다.

롤백은 이미지 태그 커밋을 되돌리면 된다. ArgoCD 가 이전 이미지로 돌아간다.

replica 는 1개이고 전략은 `Recreate` 다. 폴러 스레드와 대기 중인 신청 목록이
프로세스 메모리에 있고, 신청 내역은 `ReadWriteOnce` PVC 에 저장된다.

---

## Secrets

시크릿은 **커밋하지 않는다.** 클러스터에 직접 만들고 매니페스트에서는 이름으로만
참조한다. 그래서 매니페스트가 공개돼 있어도 자격증명은 공개되지 않는다.

| 시크릿 | 네임스페이스 | 내용 |
|---|---|---|
| `parking-secret` | `parking-system` | 텔레그램 토큰·챗 ID, 공유 비밀번호, 쿠키 서명키, 톡방 초대 링크 |
| `ghcr-pull` | `parking-system` | GHCR pull 자격증명 — 이미지 패키지가 private |
| `hermes-secret` | `hermes-system` | 텔레그램 토큰, Gemini API 키 |
| `litellm-secret` | `litellm-system` | 모델 제공자 API 키 |

private GHCR 패키지는 자격증명 없이 받아올 수 없다. `imagePullSecret` 이 없으면
`ImagePullBackOff` 로 나타난다.

---

## 내부 전용 호스트명

`argocd.newhojin.com` 은 의도적으로 공개 DNS 에 등록하지 않는다. 내부 DNS 컨테이너
(`dns-01`, [homelab-iac](https://github.com/Ohjinn/homelab-iac) 참고)에서만 해석되므로
ArgoCD UI 는 집 안에서만 열린다.

ArgoCD Ingress 는 원래 `host` 가 없어서 Traefik 의 catch-all 이었다. 매칭되는
Ingress 가 없는 모든 호스트가 관리 콘솔로 떨어졌다는 뜻이다. 터널에 서브도메인을
추가하면서 Ingress 를 깜빡하면 그대로 ArgoCD 가 인터넷에 열렸을 것이다. 지금은
host 하나만 받고 나머지는 404 를 준다.

**내부 전용 이름은 Cloudflare 에 레코드를 만들면 안 된다.** 그게 곧 인터넷에
공개하는 일이다.

---

## Bootstrap

ArgoCD 자체는 최초 1회 수동 설치한다. 그 다음 루트 Application 을 적용하면
이후로는 GitOps 가 관리한다.

```bash
kubectl apply -f bootstrap/cluster-root.yml
```

---

## Cluster Info

- **배포판:** k3s, `k3s-master-01` (192.168.0.151)
- **Ingress:** Traefik (k3s 내장)
- **외부 접근:** Cloudflare Tunnel → Traefik → Ingress host 매칭
- **ArgoCD 모드:** insecure (HTTP) — TLS 는 Traefik 또는 Cloudflare 에서 종료

---

## Roadmap

- [ ] litellm 재시작 반복 해결 — 512Mi 한도에서 OOM, 1.5Gi 정도 필요
- [ ] hermes 이미지 빌드·push 하거나 앱 정리
- [ ] litellm 을 `main-latest` 대신 특정 버전 태그로 고정
- [ ] 클러스터에만 두는 시크릿을 SealedSecrets 또는 External Secrets 로 교체
- [ ] Prometheus + Grafana 스택 추가
- [ ] ArgoCD Rollouts 카나리 배포 전략 구현
