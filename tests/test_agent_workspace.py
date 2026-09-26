"""Transport boundary checks that need neither MCP nor a CAD engine."""
import json
from pathlib import Path
import pytest
from fluxkernel.agent_workspace import AgentWorkspace, WorkspaceError
from fluxkernel.agent_server import tool_specs
from fluxkernel.revision import revision_schema


@pytest.mark.parametrize('run_id', ['../escape', '/tmp/outside', 'A'*16, 'a'*17, '', 'a'*15+'/', 'a'*16+'/..'])
def test_run_ids_cannot_address_paths(tmp_path, run_id):
    workspace = AgentWorkspace(tmp_path)
    with pytest.raises(WorkspaceError, match='16-character'):
        workspace.run_path(run_id)


def test_symlink_run_is_not_exposed(tmp_path):
    root = tmp_path/'runs'; root.mkdir()
    outside = tmp_path/'outside'; outside.mkdir()
    try:
        (root/('a'*16)).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Symlinks are unavailable')
    workspace = AgentWorkspace(root)
    assert workspace.list_runs()['runs'] == []
    with pytest.raises(WorkspaceError): workspace.inspect('a'*16)


def test_listing_paginates_and_marks_unreadable_status(tmp_path):
    for i in range(5):
        run = tmp_path/f'{i:016x}'; run.mkdir()
        (run/'status.json').write_text(json.dumps({'state':'complete','stage':'complete'}))
    (tmp_path/'0000000000000003'/'status.json').write_text('not-json')
    workspace = AgentWorkspace(tmp_path)
    one = workspace.list_runs(limit=2)
    two = workspace.list_runs(limit=2, after=one['next_cursor'])
    three = workspace.list_runs(limit=2, after=two['next_cursor'])
    assert len(one['runs']+two['runs']+three['runs']) == 5
    assert two['runs'][1]['state'] == 'unreadable'
    assert three['next_cursor'] is None
    assert all(r['integrity'] == 'not-checked' for r in one['runs'])


def test_readonly_does_not_create_directory_or_allow_writes(tmp_path):
    missing = tmp_path/'missing'
    with pytest.raises(ValueError): AgentWorkspace(missing, read_only=True)
    assert not missing.exists()
    workspace = AgentWorkspace(tmp_path, read_only=True)
    with pytest.raises(WorkspaceError, match='read-only'): workspace.create('enclosure')
    names = {s['name'] for s in tool_specs(True)}
    assert 'apply_revision' not in names and 'create_task' not in names


def test_busy_writer_does_not_queue_another_generation(tmp_path):
    workspace = AgentWorkspace(tmp_path)
    with workspace._writer:
        with pytest.raises(WorkspaceError) as caught: workspace.create('enclosure')
    assert caught.value.code == 'MCP_BUSY'
    assert list(tmp_path.iterdir()) == []


def test_agent_schema_uses_canonical_request():
    for spec in tool_specs():
        if spec['name'] in ('preview_revision','apply_revision'):
            assert spec['inputSchema']['properties']['request'] == revision_schema()
    assert all(not s['annotations']['openWorldHint'] for s in tool_specs())


def test_report_allowlist_checked_before_filesystem(tmp_path):
    with pytest.raises(WorkspaceError) as caught:
        AgentWorkspace(tmp_path).read_report('a'*16, '../model.json')
    assert caught.value.code == 'MCP_REPORT_NOT_ALLOWED'
