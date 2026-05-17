from pathlib import Path

from scripts.e2e_validation_smoke import parse_json_output


def test_validation_artifacts_exist() -> None:
    assert Path("datasets/synthetic/validation_matrix.yaml").exists()
    assert Path("scripts/e2e_validation_smoke.py").exists()
    assert Path("docs/runbooks/guide_definition_of_done_matrix.md").exists()


def test_e2e_validation_smoke_covers_required_runtime_steps() -> None:
    script = Path("scripts/e2e_validation_smoke.py").read_text(encoding="utf-8")

    assert '"/health"' in script
    assert '"/ask"' in script
    assert "/trace/{ask['trace_id']}" in script
    assert '"/metrics"' in script
    assert '"/feedback"' in script
    assert '"scripts/run_eval.py"' in script
    assert '"scripts/run_gx_dq_checks.py"' in script
    assert '"scripts/quality_gate.py"' in script
    assert '"/llmops/readiness"' in script
    assert "allowed_exit_codes={0, 1}" in script
    assert "--require-success-ask" in script
    assert 'args.require_success_ask and ask["status"] != "success"' in script


def test_e2e_validation_smoke_parses_json_with_prefix_noise() -> None:
    payload = parse_json_output('log line\n{"status": "passed", "duration_ms": 1}\n')

    assert payload == {"status": "passed", "duration_ms": 1}
