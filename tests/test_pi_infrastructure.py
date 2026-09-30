import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import Mock
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    spec = importlib.util.spec_from_file_location(Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def verifier():
    return load('pi/verify.py')


def test_wait_requires_all_checks_in_same_attempt(verifier, monkeypatch):
    samples = [
        {'service': True, 'p1': False, 'p2': False, 'ping': False},
        {'service': True, 'p1': True, 'p2': False, 'ping': True},
        {'service': False, 'p1': True, 'p2': True, 'ping': True},
        dict.fromkeys(['service', 'p1', 'p2', 'ping'], True),
    ]
    probe = Mock(side_effect=samples)
    monkeypatch.setattr(verifier, 'runtime_checks', probe)
    monkeypatch.setattr(verifier.time, 'sleep', Mock())
    assert all(verifier.wait_for_runtime().values())
    assert probe.call_count == 4


def test_timeout_preserves_failed_checks(verifier, monkeypatch):
    monkeypatch.setattr(verifier, 'runtime_checks', lambda: {'ping': False})
    monkeypatch.setattr(verifier.time, 'monotonic', Mock(side_effect=[0, 31]))
    assert verifier.wait_for_runtime(30) == {'ping': False}


def test_zero_timeout_checks_once(verifier, monkeypatch):
    probe = Mock(return_value={'ping': False})
    monkeypatch.setattr(verifier, 'runtime_checks', probe)
    assert verifier.wait_for_runtime(0) == {'ping': False}
    probe.assert_called_once()


@pytest.mark.parametrize('payload, expected', [
    ({'ok': True, 'service': 'ai-arcade-controller-broker', 'players': [1, 2]}, True),
    ({'ok': True}, False),
    ({'ok': True, 'service': 'ai-arcade-controller-broker', 'players': [1]}, False),
    ([], False),
])
def test_ping_validates_broker_identity(verifier, monkeypatch, payload, expected):
    sock = Mock()
    data = json.dumps(payload).encode() + b'\n'
    sock.recv.side_effect = [data[:3], data[3:]]
    monkeypatch.setattr(verifier.socket, 'create_connection', Mock(return_value=sock))
    assert verifier.broker_ping() is expected
    sock.close.assert_called_once()


def test_ping_connection_failure(verifier, monkeypatch):
    monkeypatch.setattr(verifier.socket, 'create_connection', Mock(side_effect=OSError('refused')))
    assert not verifier.broker_ping()


def test_diagnostics_attempt_journal_even_if_status_fails(verifier, monkeypatch):
    run = Mock(side_effect=[OSError('status unavailable'), Mock(returncode=0), Mock(returncode=0)])
    monkeypatch.setattr(verifier.subprocess, 'run', run)
    verifier.diagnostics()
    assert run.call_args_list[1].args[0][0] == 'journalctl'


def test_failed_verification_reports_diagnostics(verifier, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['verify.py', '--timeout', '0'])
    monkeypatch.setattr(verifier, 'wait_for_runtime', lambda timeout: {'ping': False})
    monkeypatch.setattr(verifier, 'systemctl_ok', lambda operation: True)
    monkeypatch.setattr(verifier, 'ES_CFG', tmp_path / 'missing.xml')
    monkeypatch.setattr(verifier, 'RA_DIR', tmp_path)
    diagnostics = Mock()
    monkeypatch.setattr(verifier, 'diagnostics', diagnostics)
    assert verifier.main() == 1
    diagnostics.assert_called_once()


def test_mapping_install_is_idempotent(monkeypatch, tmp_path):
    patcher = load('pi/patch_es_input.py')
    path = tmp_path / 'es_input.cfg'
    path.write_text('<inputList><inputConfig deviceName="Existing" /></inputList>')
    monkeypatch.setattr(sys, 'argv', ['patch_es_input.py', str(path)])
    patcher.main()
    first = path.read_bytes()
    patcher.main()
    assert path.read_bytes() == first
    assert len(ET.parse(path).getroot().findall('inputConfig')) == 3


def test_installer_repeats_safely_and_verifies_after_restart(monkeypatch, tmp_path):
    installer = load('pi/install.py')
    es = tmp_path / 'es_input.cfg'
    es.write_text('<inputList/>')
    ra = tmp_path / 'autoconfig'
    ra.mkdir()
    install_dir = tmp_path / 'installed'
    for name, value in {
        'ES_CFG': es, 'RA_DIR': ra, 'INSTALL_DIR': install_dir,
        'SERVICE_DST': tmp_path / 'broker.service',
        'MODULES_FILE': tmp_path / 'modules.conf',
    }.items():
        monkeypatch.setattr(installer, name, value)
    for name in ('require_root', 'ensure_evdev', 'stop_legacy_brokers'):
        monkeypatch.setattr(installer, name, Mock())
    original_exists = Path.exists
    monkeypatch.setattr(Path, 'exists', lambda path: True if path == Path('/dev/uinput') else original_exists(path))
    commands = Mock()
    monkeypatch.setattr(installer, 'run', commands)
    monkeypatch.setattr(sys, 'argv', ['install.py', '--source', str(ROOT / 'pi'), '--timeout', '60'])
    installer.main()
    installer.main()
    assert installer.MODULES_FILE.read_text() == 'uinput\n'
    assert len(list((install_dir / 'backups').iterdir())) == 2
    calls = [call.args for call in commands.call_args_list]
    verify = (sys.executable, str(install_dir / 'verify.py'), '--timeout', '60.0')
    assert calls.count(verify) == 2
    for index, command in enumerate(calls):
        if command == verify:
            assert calls[index - 1] == ('systemctl', 'restart', installer.SERVICE_NAME)


def test_deployment_failure_collects_diagnostics_and_closes_ssh(monkeypatch):
    deploy = load('tools/install_pi.py')
    ssh = Mock()
    monkeypatch.setattr(deploy.paramiko, 'SSHClient', lambda: ssh)
    monkeypatch.setattr(sys, 'argv', ['install_pi.py'])
    remote = Mock(side_effect=[RuntimeError('install failed'), 3, 0, 0])
    monkeypatch.setattr(deploy, 'run', remote)
    with pytest.raises(RuntimeError, match='install failed'):
        deploy.main()
    assert '--timeout 30' in remote.call_args_list[0].args[1]
    assert 'systemctl status' in remote.call_args_list[1].args[1]
    assert 'journalctl' in remote.call_args_list[2].args[1]
    ssh.close.assert_called_once()


def test_remote_run_streams_merged_binary_output(capsys):
    deploy = load('tools/install_pi.py')
    ssh = Mock()
    channel = ssh.get_transport.return_value.open_session.return_value
    stream = Mock()
    stream.__iter__ = Mock(return_value=iter([b'compile progress\n', b'complete\n']))
    channel.makefile.return_value = stream
    channel.recv_exit_status.return_value = 0
    assert deploy.run(ssh, 'build') == 0
    channel.set_combine_stderr.assert_called_once_with(True)
    channel.makefile.assert_called_once_with('rb')
    assert 'compile progress' in capsys.readouterr().out
    channel.close.assert_called_once()


@pytest.mark.parametrize('enabled, code, expected', [(False, 1, None), (True, 0, True), (True, 1, False)])
def test_optional_es_state_verification(verifier, monkeypatch, tmp_path, enabled, code, expected):
    monkeypatch.setattr(verifier, 'ES_STATE_ROOT', tmp_path)
    if enabled:
        (tmp_path / 'enabled').touch()
    monkeypatch.setattr(verifier, 'systemctl_ok', lambda op: True)
    monkeypatch.setattr(verifier, 'broker_ping', lambda: True)
    monkeypatch.setattr(verifier.subprocess, 'run', Mock(return_value=Mock(returncode=code)))
    assert verifier.runtime_checks().get('EmulationStation live state') is expected
