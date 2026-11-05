"""FDE Academy server.

Keep this module import-free: `labctl` and `tools/session_status.py` import
`academy_server.paths` and `academy_server.store` with a bare system Python
(no venv), so nothing here may pull in FastAPI, pydantic or yaml.
"""
__version__ = "0.1.0"
