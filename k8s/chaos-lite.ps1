# ============================================================
# Lightweight K8s Chaos Experiment Script
# Prerequisites: Docker Desktop with Kubernetes enabled, kubectl available
# ============================================================

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("setup", "fault1", "fault2-on", "fault2-off", "fault3-on", "fault3-off", "status", "health")]
    [string]$Action
)

function Show-Status {
    Write-Host "`n=== Pods ===" -ForegroundColor Cyan
    kubectl get pods -o wide
    Write-Host "`n=== Services ===" -ForegroundColor Cyan
    kubectl get svc
    Write-Host "`n=== Network Policies ===" -ForegroundColor Cyan
    kubectl get networkpolicy
}

function Test-Health {
    Write-Host "`n=== Health Check ===" -ForegroundColor Cyan
    kubectl run appcheck --rm -i --restart=Never --image=busybox:1.36 -- sh -c "wget -qO- http://app:5000/healthz || echo FAILED"
}

switch ($Action) {
    # ---- Setup: build image + deploy ----
    # Interview tip: Deployment manages Pod replicas, auto rolling update
    "setup" {
        Write-Host "[setup] building docker image..." -ForegroundColor Yellow
        docker build -t chaos-demo-app:latest ..
        Write-Host "[setup] applying k8s manifests..." -ForegroundColor Yellow
        kubectl apply -f app-redis.yaml
        Write-Host "[setup] waiting for rollout..." -ForegroundColor Yellow
        kubectl rollout status deployment/app --timeout=120s
        kubectl rollout status deployment/redis --timeout=60s
        Show-Status
        Write-Host "`n[setup] done! run 'health' to verify." -ForegroundColor Green
    }

    # ---- fault1: delete Pod, observe self-healing ----
    # Interview tip: Deployment ensures desired replica count, deleted Pod auto-recreated
    "fault1" {
        Write-Host "[fault1] delete one app pod, observe self-healing" -ForegroundColor Yellow
        $pod = kubectl get pods -l app.kubernetes.io/name=app -o jsonpath="{.items[0].metadata.name}"
        if (-not $pod) {
            throw "No app pod found."
        }
        Write-Host "[fault1] deleting pod: $pod"
        kubectl delete pod $pod
        Write-Host "[fault1] waiting for new pod to be ready..." -ForegroundColor Yellow
        kubectl rollout status deployment/app --timeout=120s
        Show-Status
        Write-Host "`n[fault1] pod deleted and replaced. Deployment self-healing works!" -ForegroundColor Green
    }

    # ---- fault2: network isolation of Redis ----
    # Interview tip: NetworkPolicy controls Pod-to-Pod communication, isolation causes degradation
    "fault2-on" {
        Write-Host "[fault2-on] isolate redis via deny-all NetworkPolicy" -ForegroundColor Yellow
        kubectl delete networkpolicy redis-only-allow-app --ignore-not-found
        kubectl apply -f redis-deny-all.yaml
        Write-Host "[fault2-on] checking app health (expect degraded) ..." -ForegroundColor Yellow
        Test-Health
        Show-Status
        Write-Host "`n[fault2-on] redis isolated. app should show redis=false." -ForegroundColor Red
    }

    "fault2-off" {
        Write-Host "[fault2-off] restore redis network policy" -ForegroundColor Yellow
        kubectl delete networkpolicy redis-deny-all --ignore-not-found
        kubectl apply -f redis-networkpolicy.yaml
        Write-Host "[fault2-off] checking app health (expect healthy) ..." -ForegroundColor Yellow
        Test-Health
        Show-Status
        Write-Host "`n[fault2-off] network restored." -ForegroundColor Green
    }

    # ---- fault3: CPU pressure ----
    # Interview tip: resources.limits caps CPU, container gets throttled when exceeded
    "fault3-on" {
        Write-Host "[fault3-on] apply tight CPU limit (100m)" -ForegroundColor Yellow
        kubectl set resources deployment app --requests=cpu=50m --limits=cpu=100m
        kubectl rollout status deployment/app --timeout=120s
        Write-Host "[fault3-on] current resources:" -ForegroundColor Yellow
        kubectl get deployment app -o jsonpath="{.spec.template.spec.containers[0].resources}"
        Write-Host ""
        Show-Status
        Write-Host "`n[fault3-on] CPU limited. expect higher latency under load." -ForegroundColor Red
    }

    "fault3-off" {
        Write-Host "[fault3-off] restore baseline resources" -ForegroundColor Yellow
        kubectl delete deployment app --ignore-not-found
        kubectl apply -f app-redis.yaml
        kubectl rollout status deployment/app --timeout=120s
        Show-Status
        Write-Host "`n[fault3-off] resources restored." -ForegroundColor Green
    }

    # ---- Status ----
    "status" {
        Show-Status
    }

    # ---- Health check ----
    "health" {
        Test-Health
    }
}
