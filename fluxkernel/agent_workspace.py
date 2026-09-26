"""Workspace-scoped operations shared by the local agent transport.

No model requests, arbitrary code execution, or caller-selected output paths.
This is a local API boundary, not a sandbox against the filesystem owner.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from .revision import inspect_run, preview_revision, revision_schema, snapshot
from .studio import TASKS, apply_revision, generate_task, load_task

RUN_PATTERN = r'^[a-f0-9]{16}$'
REPORTS = ('design.json', 'constraints.json', 'constraint-checks.json',
           'manufacturing.json', 'proof.json', 'reuse.json', 'geometry-checks.json')
MAX_REPORT_BYTES = 1024 * 1024


class WorkspaceError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class AgentWorkspace:
    def __init__(self, directory, *, read_only=False, timeout=300):
        if not 1 <= timeout <= 900:
            raise ValueError('Worker timeout must be between 1 and 900 seconds')
        self.root = Path(directory).expanduser().resolve()
        if read_only and not self.root.is_dir():
            raise ValueError('Read-only workspace must already exist')
        if not read_only:
            self.root.mkdir(parents=True, exist_ok=True)
        self.read_only = read_only
        self.timeout = timeout
        self._writer = threading.Lock()

    def run_path(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(RUN_PATTERN, run_id):
            raise WorkspaceError('MCP_INVALID_RUN', 'Use a 16-character run ID from this workspace')
        candidate = self.root / run_id
        if candidate.is_symlink() or not candidate.is_dir() or candidate.resolve().parent != self.root:
            raise WorkspaceError('MCP_RUN_NOT_FOUND', 'Run is missing or outside this workspace')
        return candidate

    def capabilities(self):
        return {'schema': 'fk-agent-workspace-v1', 'transport': 'stdio',
                'read_only': self.read_only, 'worker_timeout_s': self.timeout,
                'model_calls': False, 'physical_validation': False,
                'revision_schema': revision_schema(), 'report_names': list(REPORTS),
                'scope': 'Authored tasks and bounded local revisions; no image inference',
                'write_behavior': 'Each call creates a new run; writes are not idempotent',
                'proof_scope': 'Lean checks the manufacturing plan; nominal constraints use Python'}

    def list_tasks(self):
        return {'tasks': [{'id': name, 'title': load_task(name)['design']['title'],
                           'constraints': load_task(name)['constraints']} for name in TASKS],
                'source': 'authored fixtures', 'model_calls': 0}

    def list_runs(self, limit=20, after=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise WorkspaceError('MCP_INVALID_ARGUMENT', 'Limit must be between 1 and 100')
        if after is not None and not re.fullmatch(RUN_PATTERN, after):
            raise WorkspaceError('MCP_INVALID_ARGUMENT', 'Invalid pagination cursor')
        names = sorted(p.name for p in self.root.iterdir()
                       if re.fullmatch(RUN_PATTERN, p.name) and p.is_dir() and not p.is_symlink()
                       and (after is None or p.name > after))
        rows = []
        for name in names[:limit]:
            row = {'id': name, 'state': 'unknown', 'integrity': 'not-checked'}
            try:
                run = self.run_path(name)
                status_path = run/'status.json'
                if status_path.is_symlink() or not status_path.is_file() or status_path.stat().st_size > MAX_REPORT_BYTES:
                    raise ValueError('Invalid status')
                status = json.loads(status_path.read_text(encoding='utf-8'))
                if not isinstance(status, dict):
                    raise ValueError('Invalid status')
                row['state'] = status.get('state', 'unknown')
                row['stage'] = status.get('stage', 'unknown')
            except (OSError, ValueError):
                row['state'] = 'unreadable'
            rows.append(row)
        return {'runs': rows, 'next_cursor': rows[-1]['id'] if len(names) > limit else None,
                'order': 'run-id-ascending', 'integrity': 'not-checked'}

    def inspect(self, run_id):
        return inspect_run(self.run_path(run_id))

    def preview(self, run_id, request):
        return preview_revision(self.run_path(run_id), request)

    def _write(self, operation):
        if self.read_only:
            raise WorkspaceError('MCP_READ_ONLY', 'This workspace was opened read-only')
        if not self._writer.acquire(blocking=False):
            raise WorkspaceError('MCP_BUSY', 'Another generation is running; inspect history before retrying')
        try:
            return operation()
        finally:
            self._writer.release()

    def create(self, task):
        if task not in TASKS:
            raise WorkspaceError('MCP_INVALID_TASK', 'Unknown authored task')
        return self._write(lambda: generate_task(task, output_dir=self.root, timeout=self.timeout).to_dict())

    def apply(self, run_id, request):
        parent = self.run_path(run_id)
        return self._write(lambda: apply_revision(parent, request, output_dir=self.root, timeout=self.timeout))

    def read_report(self, run_id, report):
        if report not in REPORTS:
            raise WorkspaceError('MCP_REPORT_NOT_ALLOWED', 'Choose a report listed in capabilities')
        snap = snapshot(self.run_path(run_id))
        data = snap['files'].get(report)
        if data is None:
            raise WorkspaceError('MCP_REPORT_MISSING', 'This run has no committed report of that name')
        if len(data) > MAX_REPORT_BYTES:
            raise WorkspaceError('MCP_REPORT_TOO_LARGE', 'Report exceeds the 1 MiB response limit')
        return {'run_id': run_id, 'report': report, 'integrity': 'manifest-verified',
                'manifest_sha256': snap['identity'], 'data': json.loads(data)}

    def list_artifacts(self, run_id):
        snap = snapshot(self.run_path(run_id))
        from .revision import sha
        return {'run_id': run_id, 'manifest_sha256': snap['identity'],
                'integrity': 'manifest-verified', 'directory': str(snap['root']),
                'artifacts': [{'name': name, 'bytes': len(data), 'sha256': sha(data)}
                              for name, data in sorted(snap['files'].items())]}
