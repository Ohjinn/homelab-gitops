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
│   ├── chroma.yml
│   ├── hermes.yml
│   ├── investwells.yml
│   ├── litellm.yml
│   ├── openwebui.yml
│   ├── parking.yml
│   └── traefik-config.yml
└── k8s/base/                 # 각 Application 이 가리키는 실제 매니페스트
    ├── argocd/
    ├── chroma/               # 벡터 DB + RAG API + 인덱싱 CronJob
    ├── hermes/
    ├── investwells/
    ├── litellm/
    ├── openwebui/
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
| litellm | `litellm-system` | `litellm.newhojin.com` | `ghcr.io/berriai/litellm` (digest 고정) | Active |
| hermes | `hermes-system` | — | `docker.io/nousresearch/hermes-agent:v2026.8.19` | Active |
| **chroma** | `chroma-system` | `chroma.newhojin.com` · `rag.newhojin.com` | `chromadb/chroma:1.5.9` · `python:3.12-slim` | Active |
| **openwebui** | `openwebui-system` | `chat.newhojin.com` | `ghcr.io/open-webui/open-webui:main` | Active |

**hermes 는 포크를 빌드할 필요가 없었다.** 매니페스트가 한 번도 push 된 적 없는
`ghcr.io/ohjinn/hermes-bot` 을 가리키고 있어서 61 일간 `ImagePullBackOff` 였다.
상류가 Docker Hub 에 공식 이미지를 올리고 있다.

---

## chroma — 홈랩 문서 RAG 스택

레포 7 개와 커밋 이력, 개인 메모를 벡터로 만들어 두고 질문에 답한다.
파이프라인 자체는 [Ohjinn/Local-RAG](https://github.com/Ohjinn/Local-RAG) 에 있고
이 레포는 배치만 갖는다.

한 네임스페이스에 세 가지가 산다.

| | 하는 일 |
|---|---|
| `chroma` | 벡터 DB. PVC 5Gi. 메타데이터는 SQLite, 벡터는 별도 HNSW 세그먼트 |
| `rag-api` | 검색과 생성을 잇는 HTTP API. OpenAI 호환 경로도 낸다 |
| `rag-indexer` | CronJob. 매일 04:30 KST 에 레포를 다시 받아 바뀐 문서만 임베딩 |

**CronJob 이 이 스택을 k3s 로 옮긴 이유다.** 그전에는 손으로만 돌아서 코퍼스가
한 달 전에 멈춰 있었고, 어제 고친 것을 물으면 낡은 답이 나왔다. pve 의
vzdump(04:00)와 겹치지 않게 04:30 으로 뺐다.

임베딩(`bge-m3`)과 생성(`qwen2.5:14b`)은 **맥북 Ollama** 에서 돈다. k3s 노드가
i5-8250U 라 여기서 임베딩하면 몇십 분이 걸린다. 맥북이 없으면 CronJob 은
조용히 `exit 0` 한다 — 들고 나간 날 실패 알림이 쌓이는 것을 막는다.

### rag-api 의 경로가 셋인 이유

필요한 것이 서로 달라서 갈라 뒀다.

| 경로 | 맥북 | 시간 | 찾는 기준 |
|---|---|---|---|
| `/search/text` | 불필요 | 7 ms | 글자가 그대로 든 청크 |
| `/search` | 필요 | 150 ms | 뜻이 가까운 청크 |
| `/ask` | 필요 | 25 s | 청크를 읽고 쓴 답 |

`/ask` 25 초 중 **검색은 0.16 초**고 나머지 전부가 생성이다. 청크만 보고 싶을 때
답 생성을 기다릴 이유가 없다. `/v1/chat/completions` 도 내서 Open WebUI 가
모델처럼 고를 수 있다.

### Chroma 인증은 앞단에서 건다

**Chroma 1.0 부터 내장 인증이 없다.** Rust 로 다시 쓰이면서 `CHROMA_SERVER_AUTHN_*`
가 통째로 무시된다 — 넣어도 오류 없이 아무 일도 일어나지 않고 **틀린 토큰으로도
200 이 온다.** 확인은 "맞는 토큰으로 200" 이 아니라 **"틀린 토큰으로 401"** 로
해야 잡힌다.

그래서 traefik `basicAuth` 미들웨어를 인그레스에 붙인다. 클러스터 안에서는
Service 로 직접 붙어 이 문을 지나지 않으므로 자격증명이 없다.

---

## openwebui — 채팅 화면

`rag-api` 와 `litellm` 을 **모델 드롭다운으로 골라 쓰는** 화면이다.

```
homelab-rag         홈랩 문서를 아는 모델
gemini-chat         순수 Gemini. 긴 답 가능, 폴백 없음
default_assistant   HA 음성용 (30 초 제한, 맥북 폴백)
local-qwen          맥북 qwen2.5:14b
```

같은 화면에서 갈아타며 비교할 수 있다. `rag-api` 에 OpenAI 호환 경로를 낸 것이
이걸 위해서였다 — 클라이언트를 새로 만들지 않고 얹는다.

### 기본값이 다 켜져 있다

Open WebUI 는 선언하지 않은 기능이 전부 활성인 채로 뜬다. 매니페스트만 읽어서는
알 수 없어서 하나씩 껐다.

| 껐는데 왜 | |
|---|---|
| `ENABLE_PERSISTENT_CONFIG` | **환경변수를 첫 기동에만 읽고 그 뒤로는 DB 가 이긴다.** 키를 시크릿으로 바꿔도 반영되지 않아 litellm 모델이 드롭다운에 안 떴다. False 로 두면 매니페스트가 곧 도는 것이 된다 |
| `ENABLE_NOTES` 외 3 개 | "나는 메모를 쓰고 일정을 관리하는 비서다" 를 시스템 프롬프트에 붙인다. Terraform 코드를 짜 달라고 했더니 **모델이 거절했다** |
| `DEFAULT_MODEL_PARAMS` | 내장 도구 17 개가 목록이 비어 있어도 붙는다. qwen 이 도구 호출 JSON 을 본문에 그대로 뱉었다 |

**세 번 다 같은 방법으로 갈랐다 — litellm 에 직접 물어보기.** 같은 모델·같은
프록시인데 답이 다르면 중간이 범인이다.

대가는 화면에서 연결이나 기능을 고쳐도 재시작하면 되돌아간다는 것이다.
설정은 이제 매니페스트에서만 바꾼다.

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
| `litellm-secret` | `litellm-system` | Gemini API 키, `LITELLM_MASTER_KEY` |
| `chroma-basicauth` | `chroma-system` | traefik basicAuth 용 해시. 평문은 안 들어간다 |
| `chroma-client` | `chroma-system` | 클러스터 안에서 쓰는 `CHROMA_URL` |
| `rag-git` | `chroma-system` | 인덱서가 private 레포를 클론할 PAT (읽기 전용) |
| `openwebui-backends` | `openwebui-system` | `OPENAI_API_KEYS` — litellm 마스터 키가 여기 |

private GHCR 패키지는 자격증명 없이 받아올 수 없다. `imagePullSecret` 이 없으면
`ImagePullBackOff` 로 나타난다.

---

## 내부 전용 호스트명

아래 이름들은 **의도적으로 공개 DNS 에 등록하지 않는다.** 내부 DNS 컨테이너
(`dns-01`, [homelab-iac](https://github.com/Ohjinn/homelab-iac) 참고)에서만
해석되므로 집 안에서만 열린다.

| 이름 | 무엇 |
|---|---|
| `argocd.newhojin.com` | ArgoCD UI |
| `litellm.newhojin.com` | LLM 프록시. 뒤에 Gemini 키가 물려 있다 |
| `chroma.newhojin.com` | 벡터 DB |
| `rag.newhojin.com` | RAG API. **여기가 가장 위험한 문이다** — Chroma 는 청크를 주지만 이쪽은 LLM 이 그것을 읽고 요약해 준다 |
| `chat.newhojin.com` | Open WebUI |

### 밖에서 쓰려면 Tailscale Split DNS

관리 콘솔 → DNS → Nameservers → Custom `192.168.0.102`, **"Restrict to domain"
에 `newhojin.com`**. 도메인 제한을 꼭 걸어야 한다 — 안 걸면 그 기기의 모든
질의가 집으로 넘어온다.

**기기별 `Use Tailscale DNS` 토글이 꺼져 있으면 콘솔 설정이 통째로 무시된다.**
회사 노트북에 깔 때 꺼두기 쉬운 항목이라 여기서 한 번 막혔다. 생 IP 로는
안 된다 — traefik 이 Host 헤더로 라우팅해서 `192.168.0.151` 을 그냥 열면 404 다.

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

- **배포판:** k3s, `k3s-master-01` (192.168.0.151), 2 vCPU / 10GB / **디스크 40GB**
- **Ingress:** Traefik (k3s 내장)
- **추론:** 맥북 Mac M3 (192.168.0.44) 의 Ollama. 클러스터 안에서 모델을 올리지 않는다
- **외부 접근:** Cloudflare Tunnel → Traefik → Ingress host 매칭
- **ArgoCD 모드:** insecure (HTTP) — TLS 는 Traefik 또는 Cloudflare 에서 종료

---

## Roadmap

- [x] ~~litellm OOM~~ — 1536Mi 로 올려 해결
- [x] ~~hermes 이미지~~ — 포크가 필요 없었다. 상류 공식 이미지로 교체
- [x] ~~`chroma-secret` 정리~~ — 동작하지 않는 Chroma 내장 인증 때 만든 잔재였다.
      아무 매니페스트도 참조하지 않아 2026-09-03 에 삭제
- [ ] rag-api 이미지를 GHCR 로 굽기 — 지금은 파드가 뜰 때 `git clone` + `uv sync`
      를 한다(40 초). PyPI 나 GitHub 가 죽으면 파드가 안 뜨고 어느 커밋이 도는지
      고정되지 않는다. Local-RAG 용 러너 등록이 먼저다
- [ ] litellm 을 `main-latest` 대신 특정 버전 태그로 고정
- [ ] 클러스터에만 두는 시크릿을 SealedSecrets 또는 External Secrets 로 교체
- [ ] Prometheus + Grafana 스택 추가
- [ ] ArgoCD Rollouts 카나리 배포 전략 구현
