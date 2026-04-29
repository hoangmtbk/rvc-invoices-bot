import sys
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_file_storage_reload():
    """Monkey-patch importlib.reload for file_storage to preserve patches."""
    import importlib
    original_reload = importlib.reload

    def patched_reload(module):
        """Reload module while preserving any patches to it."""
        if module.__name__ == 'file_storage':
            # For file_storage, we'll skip the actual reload if it's already been imported
            # This allows patches to persist
            return module
        return original_reload(module)

    with patch('importlib.reload', side_effect=patched_reload):
        yield
