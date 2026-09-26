"""First-run contracts, executable with only the kernel and pytest installed."""
import json
import os
import subprocess
import sys
from pathlib import Path

from fluxkernel.interface.onboarding import diagnose
from fluxkernel.runtime import assets_root, data_dir, copy_proof_project
from fluxkernel.store.objstore import Store


def cli(tmp_path, *args):
    return subprocess.run([sys.executable, '-m', 'fluxkernel.interface.cli', *args],
                          cwd=tmp_path, capture_output=True, text=True)


def test_first_workspace_has_distinct_parameter_identities(tmp_path):
    for args in [('example',), ('init',), ('run', 'hello.fcad'), ('verify',)]:
        result = cli(tmp_path, *args)
        assert result.returncode == 0, result.stdout + result.stderr
    store = Store(tmp_path / '.fk')
    one, two = store.resolve('housing-v1'), store.resolve('housing-v2')
    assert one != two
    assert store.get_object(two)['payload']['params']['depth_mm'] == 14


def test_example_refuses_to_overwrite(tmp_path):
    path = tmp_path / 'hello.fcad'; path.write_text('my own design')
    result = cli(tmp_path, 'example')
    assert result.returncode == 1
    assert path.read_text() == 'my own design'


def test_doctor_json_is_machine_readable_and_does_not_initialize_workspace(tmp_path):
    result = cli(tmp_path, 'doctor', '--json')
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['ok'] and report['profile'] == 'core'
    assert list(tmp_path.iterdir()) == []


def test_bad_private_configuration_is_redacted(tmp_path, monkeypatch):
    private = tmp_path / 'model.json'
    private.write_text('{"api_key": "secret-not-for-output", malformed')
    monkeypatch.setenv('FK_MODEL_CONFIG', str(private))
    report = diagnose('live')
    assert not report['ok']
    assert 'secret-not-for-output' not in json.dumps(report)


def test_explicit_data_path_never_writes_during_resolution(tmp_path, monkeypatch):
    destination = tmp_path / 'my-runs'
    monkeypatch.setenv('FK_DEMO_DATA', str(destination))
    assert data_dir() == destination
    assert not destination.exists()


def test_proof_project_can_be_copied_outside_installation(tmp_path):
    copy_proof_project(tmp_path)
    for relative in ['formal/FluxKernel/Closure.lean', 'formal/FluxKernel.lean',
                     'lakefile.toml', 'lean-toolchain']:
        assert (tmp_path / relative).read_bytes() == (assets_root() / relative).read_bytes()


def test_headless_api_rejects_invalid_inputs_without_side_effects(tmp_path):
    import pytest
    from fluxkernel.studio import generate_reference
    with pytest.raises(ValueError): generate_reference('unknown', output_dir=tmp_path)
    with pytest.raises(ValueError): generate_reference('phone', output_dir=tmp_path, equipment_depth=True)
    assert list(tmp_path.iterdir()) == []


def test_optional_plugin_failures_remain_visible_across_engines(tmp_path):
    code = '''
import sys
from pathlib import Path
class WithoutNumerics:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('numpy', 'scipy', 'OCP'):
            raise ModuleNotFoundError('optional backend unavailable')
sys.meta_path.insert(0, WithoutNumerics())
from fluxkernel.semantics.operators import Engine
from fluxkernel.store.objstore import Store
first = Engine(Store(Path('one')))
second = Engine(Store(Path('two')))
assert any('sketch2d' in failure for failure in first.plugin_failures)
assert first.plugin_failures == second.plugin_failures
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
