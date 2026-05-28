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
│   └── openclaw.yml          # openclaw application
└── k8s/
    └── base/
        ├── argocd/
        │   ├── argocd-ingress.yml    # Traefik ingress for ArgoCD UI
        │   └── kustomization.yml     # insecure mode patch
        └── openclaw/
            ├── namespace.yml
            ├── test-app.yml          # nginx placeholder (WIP)
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
    │       └── openclaw       →  k8s/base/openclaw/
    │
    └── auto sync (prune + selfHeal)
```

All applications use `automated` sync policy with `prune: true` and `selfHeal: true` — the cluster state always converges to what is in this repository.

---

## Bootstrap

ArgoCD itself is installed manually (once). After that, apply the root Application to hand over control to GitOps:

```bash
kubectl apply -f bootstrap/cluster-root.yml
```

From this point, all changes are made via Git — not `kubectl apply`.

---

## Applications

| App | Namespace | Source Path | Status |
|---|---|---|---|
| argocd-self-config | argocd | `k8s/base/argocd` | Active |
| openclaw | openclaw-system | `k8s/base/openclaw` | WIP (nginx placeholder) |

---

## Cluster Info

- **Distribution:** k3s
- **Ingress:** Traefik (built-in k3s)
- **ArgoCD mode:** insecure (HTTP) — TLS terminated at Traefik or Cloudflare Tunnel

---

## Roadmap

- [ ] Replace nginx placeholder with actual openclaw application
- [ ] Add Prometheus + Grafana stack
- [ ] Implement canary deployment strategy via ArgoCD Rollouts
- [ ] Add k3s worker node and configure NodeAffinity for heavy workloads
