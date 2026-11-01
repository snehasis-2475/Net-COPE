import pytest

from data.scenarios import SCENARIO_METADATA, generate_scenario_data
from diagnosis.models import NetworkHealthStatus
from orchestrator.orchestrator import CentralOrchestrator


@pytest.fixture(scope="module")
def orchestrator(tmp_path_factory):
    reports_dir = tmp_path_factory.mktemp("reports")
    return CentralOrchestrator(reports_dir=str(reports_dir))


def test_scenario_normal(orchestrator):
    data = generate_scenario_data("normal")
    report = orchestrator.run_diagnosis(telemetry=data, scenario_name="normal")
    assert report.overall_network_health == NetworkHealthStatus.HEALTHY
    assert "Nominal" in report.probable_root_cause.title
    assert report.confidence_score >= 0.90


def test_scenario_congestion(orchestrator):
    data = generate_scenario_data("congestion")
    report = orchestrator.run_diagnosis(telemetry=data, scenario_name="congestion")
    assert report.overall_network_health in [NetworkHealthStatus.DEGRADED, NetworkHealthStatus.CRITICAL]
    assert "Bandwidth Congestion" in report.probable_root_cause.title
    assert report.confidence_score >= 0.80


def test_scenario_weak_wifi(orchestrator):
    data = generate_scenario_data("weak_wifi")
    report = orchestrator.run_diagnosis(telemetry=data, scenario_name="weak_wifi")
    assert report.overall_network_health in [NetworkHealthStatus.DEGRADED, NetworkHealthStatus.CRITICAL]
    assert "Wireless" in report.probable_root_cause.title or "Wi-Fi" in report.probable_root_cause.title


def test_scenario_interface_failure(orchestrator):
    data = generate_scenario_data("interface_failure")
    report = orchestrator.run_diagnosis(telemetry=data, scenario_name="interface_failure")
    assert report.overall_network_health in [NetworkHealthStatus.DEGRADED, NetworkHealthStatus.CRITICAL]
    assert "Interface" in report.probable_root_cause.title or "Cable" in report.probable_root_cause.title


def test_scenario_dns_failure(orchestrator):
    data = generate_scenario_data("dns_failure")
    report = orchestrator.run_diagnosis(telemetry=data, scenario_name="dns_failure")
    assert report.overall_network_health in [NetworkHealthStatus.DEGRADED, NetworkHealthStatus.CRITICAL]
    assert "DNS" in report.probable_root_cause.title


def test_scenario_dhcp_failure(orchestrator):
    data = generate_scenario_data("dhcp_failure")
    report = orchestrator.run_diagnosis(telemetry=data, scenario_name="dhcp_failure")
    assert report.overall_network_health in [NetworkHealthStatus.DEGRADED, NetworkHealthStatus.CRITICAL]
    assert "DHCP" in report.probable_root_cause.title


def test_scenario_infrastructure_overload(orchestrator):
    data = generate_scenario_data("infrastructure_overload")
    report = orchestrator.run_diagnosis(telemetry=data, scenario_name="infrastructure_overload")
    assert report.overall_network_health in [NetworkHealthStatus.DEGRADED, NetworkHealthStatus.CRITICAL]
    assert "Hardware" in report.probable_root_cause.title or "Overload" in report.probable_root_cause.title


def test_scenario_invalid_telemetry(orchestrator):
    data = generate_scenario_data("invalid_telemetry")
    report = orchestrator.run_diagnosis(telemetry=data, scenario_name="invalid_telemetry")
    # All records were corrupt or missing device_id, so orchestrator handles it safely
    assert report.execution_status in ["COMPLETED", "FAILED", "COMPLETED_WITH_WARNINGS"]
    assert report.confidence_score <= 0.60
