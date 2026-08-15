from __future__ import annotations

from chaos_service import fault_injection


class ChaosControlService:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def ensure_enabled(self) -> None:
        if not self._runtime.CHAOS_ENABLED:
            raise PermissionError("chaos control disabled")

    def fault_status(self) -> dict:
        self.ensure_enabled()
        faults = fault_injection.list_faults(self._runtime.redis_client)
        return fault_injection.build_fault_api_response(faults)

    def inject_fault(self, fault_type: str, params: dict, ttl_sec: int | None = None) -> dict:
        self.ensure_enabled()
        return fault_injection.inject_fault(self._runtime.redis_client, fault_type, params, ttl_sec)

    def clear_fault(self, fault_type: str) -> bool:
        self.ensure_enabled()
        return fault_injection.clear_fault(self._runtime.redis_client, fault_type)

    def clear_all_faults(self) -> int:
        self.ensure_enabled()
        return fault_injection.clear_all_faults(self._runtime.redis_client)

    def list_experiments(self):
        self.ensure_enabled()
        return fault_injection.list_experiments(self._runtime)

    def create_experiment(
        self,
        *,
        name: str,
        hypothesis: str,
        target: dict,
        fault_type: str,
        params: dict,
        duration: int,
    ):
        self.ensure_enabled()
        return fault_injection.create_experiment(
            self._runtime,
            name=name,
            hypothesis=hypothesis,
            target=target,
            fault_type=fault_type,
            params=params,
            duration=duration,
        )

    def get_experiment(self, experiment_id: str):
        self.ensure_enabled()
        return fault_injection.get_experiment(self._runtime, experiment_id)

    def get_report(self, experiment_id: str):
        self.ensure_enabled()
        return fault_injection.get_report(self._runtime, experiment_id)

    def stop_experiment(self, experiment_id: str) -> bool:
        self.ensure_enabled()
        return fault_injection.stop_experiment(self._runtime, experiment_id)
