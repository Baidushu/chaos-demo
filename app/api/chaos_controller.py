from __future__ import annotations

from flask import jsonify, request


def register_routes(flask_app, runtime) -> None:
    chaos_service = runtime.chaos_control_service

    @flask_app.route("/fault/status", methods=["GET"])
    def fault_status():
        return jsonify(chaos_service.fault_status())

    @flask_app.route("/fault/inject", methods=["POST"])
    def fault_inject():
        payload = request.get_json(silent=True) or {}
        fault_type = payload.get("type", "")
        params = payload.get("params", {})
        ttl_sec = payload.get("ttl_sec")
        if not fault_type:
            return jsonify({"error": "type is required"}), 400
        try:
            record = chaos_service.inject_fault(fault_type, params, ttl_sec)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"status": "injected", "fault": record}), 201

    @flask_app.route("/fault/clear", methods=["POST"])
    def fault_clear():
        payload = request.get_json(silent=True) or {}
        fault_type = payload.get("type", "")
        if not fault_type:
            return jsonify({"error": "type is required"}), 400
        existed = chaos_service.clear_fault(fault_type)
        return jsonify({"status": "cleared", "type": fault_type, "existed": existed})

    @flask_app.route("/fault/clear-all", methods=["POST"])
    def fault_clear_all():
        count = chaos_service.clear_all_faults()
        return jsonify({"status": "all_cleared", "count": count})

    @flask_app.route("/fault/inject/<fault_type>", methods=["DELETE"])
    def fault_delete(fault_type):
        existed = chaos_service.clear_fault(fault_type)
        return jsonify({"status": "cleared", "type": fault_type, "existed": existed})

    @flask_app.route("/chaos/experiments", methods=["GET"])
    def chaos_experiments():
        experiments = [exp.to_dict() for exp in chaos_service.list_experiments()]
        return jsonify({"experiments": experiments, "count": len(experiments)})

    @flask_app.route("/chaos/experiments", methods=["POST"])
    def chaos_create_experiment():
        payload = request.get_json(silent=True) or {}
        name = payload.get("name", "")
        hypothesis = payload.get("hypothesis", "")
        target = payload.get("target", {})
        fault_type = payload.get("fault_type", "")
        params = payload.get("params", {})
        duration = payload.get("duration", 0)
        if not name or not fault_type or int(duration or 0) <= 0:
            return jsonify({"error": "name, fault_type, duration are required"}), 400
        try:
            experiment = chaos_service.create_experiment(
                name=name,
                hypothesis=hypothesis,
                target=target,
                fault_type=fault_type,
                params=params,
                duration=int(duration),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"experiment": experiment.to_dict()}), 201

    @flask_app.route("/chaos/experiments/<experiment_id>", methods=["GET"])
    def chaos_get_experiment(experiment_id):
        experiment = chaos_service.get_experiment(experiment_id)
        if experiment is None:
            return jsonify({"error": "experiment not found"}), 404
        report = chaos_service.get_report(experiment_id)
        return jsonify({"experiment": experiment.to_dict(), "report": report}), 200

    @flask_app.route("/chaos/experiments/<experiment_id>/stop", methods=["POST"])
    def chaos_stop_experiment(experiment_id):
        stopped = chaos_service.stop_experiment(experiment_id)
        if not stopped:
            return jsonify({"error": "experiment not found"}), 404
        return jsonify({"status": "stopped", "experiment_id": experiment_id}), 200
