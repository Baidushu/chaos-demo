param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("fault1", "fault2-on", "fault2-off", "fault3-on", "fault3-off", "status")]
    [string]$Action
)

function Show-Status {
    kubectl get pods -o wide
    kubectl get networkpolicy
}

switch ($Action) {
    "fault1" {
        Write-Host "[fault1] delete one app pod and observe self-healing..."
        $pod = kubectl get pods -l app.kubernetes.io/name=app -o jsonpath="{.items[0].metadata.name}"
        if (-not $pod) {
            throw "No app pod found."
        }
        Write-Host "[fault1] deleting pod: $pod"
        kubectl delete pod $pod
        kubectl rollout status deployment/app --timeout=120s
        Show-Status
    }
    "fault2-on" {
        Write-Host "[fault2-on] isolate redis from all ingress..."
        kubectl delete networkpolicy redis-only-allow-app --ignore-not-found
        kubectl apply -f k8s/redis-deny-all.yaml
        Write-Host "[fault2-on] check app health (expect redis=false or degraded):"
        kubectl run appcheck --rm -i --restart=Never --image=busybox:1.36 -- sh -c "wget -qO- http://app:5000/healthz || true"
        Write-Host ""
        Show-Status
    }
    "fault2-off" {
        Write-Host "[fault2-off] restore app->redis network policy..."
        kubectl delete networkpolicy redis-deny-all --ignore-not-found
        kubectl apply -f k8s/redis-networkpolicy.yaml
        kubectl run appcheck --rm -i --restart=Never --image=busybox:1.36 -- sh -c "wget -qO- http://app:5000/healthz || true"
        Write-Host ""
        Show-Status
    }
    "fault3-on" {
        Write-Host "[fault3-on] apply low cpu limit to app..."
        kubectl set resources deployment app --requests=cpu=50m --limits=cpu=100m
        kubectl rollout status deployment/app --timeout=120s
        kubectl get deployment app -o jsonpath="{.spec.template.spec.containers[0].resources}" | Write-Host
        Show-Status
    }
    "fault3-off" {
        Write-Host "[fault3-off] recreate app deployment from baseline yaml..."
        kubectl delete deployment app --ignore-not-found
        kubectl apply -f k8s/app-redis.yaml
        kubectl rollout status deployment/app --timeout=120s
        Show-Status
    }
    "status" {
        Show-Status
    }
}
