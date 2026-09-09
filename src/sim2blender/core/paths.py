"""Project defaults independent of adapter/module nesting."""
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = _ROOT if (_ROOT / 'pyproject.toml').is_file() else Path.cwd()
DEFAULT_INPUT = PROJECT_ROOT / 'examples' / 'models' / 'ENCC100323640.amodel'
