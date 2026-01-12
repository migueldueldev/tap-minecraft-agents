import pytest
import asyncio
import sys
import os

# Ensure the framework modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests for individual components")
    config.addinivalue_line("markers", "integration: Integration tests for cross-component interactions")

def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location."""
    for item in items:
        # Mark tests in integration folder as integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        else:
            # Mark all other tests as unit tests
            item.add_marker(pytest.mark.unit)

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
def reset_workflow_singleton():
    """Reset the Workflow singleton before and after each test for isolation."""
    from Workflow import Workflow
    Workflow._instance = None
    yield
    Workflow._instance = None
