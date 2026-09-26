"""Real MCP discovery, protocol errors and a complete stdio CAD revision."""
import json
import shutil
import sys
import pytest
pytest.importorskip('mcp')
import anyio
from mcp import Client, StdioServerParameters
from fluxkernel.agent_server import create_server
from fluxkernel.agent_workspace import AgentWorkspace
from fluxkernel.agent_smoke import exercise


def test_stdio_complete_revision(tmp_path):
    async def run():
        report = await exercise(tmp_path, require_proof=bool(shutil.which('lake')))
        assert report['accepted'], report
        assert report['model_calls'] == 0
    anyio.run(run)


def test_protocol_errors_and_readonly_mode(tmp_path):
    async def run():
        server = create_server(AgentWorkspace(tmp_path, read_only=True))
        async with Client(server) as client:
            assert len((await client.list_tools()).tools) == 6
            for name, args, code in [
                ('create_task', {'task':'enclosure'}, 'MCP_UNKNOWN_TOOL'),
                ('inspect_run', {'run_id':'../outside'}, 'MCP_INVALID_ARGUMENT'),
                ('list_runs', {'limit':101}, 'MCP_INVALID_ARGUMENT'),
                ('list_runs', {'output':'/tmp/elsewhere'}, 'MCP_INVALID_ARGUMENT'),
                ('inspect_run', {'run_id':'0'*16}, 'MCP_RUN_NOT_FOUND'),
                ('read_report', {'run_id':'0'*16,'report':'worker.log'}, 'MCP_INVALID_ARGUMENT'),
            ]:
                result = await client.call_tool(name, args)
                assert result.is_error
                assert result.structured_content['code'] == code
            capabilities = await client.read_resource('fluxkernel://capabilities')
            assert json.loads(capabilities.contents[0].text)['read_only']
    anyio.run(run)


def test_legacy_stdio_client_discovery(tmp_path):
    async def run():
        params = StdioServerParameters(command=sys.executable,
            args=['-m','fluxkernel.agent_server','--workspace',str(tmp_path),'--read-only'])
        async with Client(params, mode='legacy') as client:
            assert len((await client.list_tools()).tools) == 6
            result = await client.call_tool('list_tasks')
            assert not result.is_error and len(result.structured_content['tasks']) == 3
    anyio.run(run)
