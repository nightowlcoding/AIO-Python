import importlib.util
import sys
import os
from unittest.mock import MagicMock

# Add current directory to sys.path
sys.path.append(os.getcwd())

# Path to the module
module_path = os.path.join(os.getcwd(), 'Dexter Assistant', 'dexter_assistant.py')
spec = importlib.util.spec_from_file_location("dexter_assistant", module_path)
dexter_assistant = importlib.util.module_from_spec(spec)
sys.modules["dexter_assistant"] = dexter_assistant

# Mock MANAGER before it's used if possible, or patch it
# In the provided script, MANAGER is likely instantiated at module level
# We need to execute the spec first
spec.loader.exec_module(dexter_assistant)

# Replace MANAGER.start_all with a stub
if hasattr(dexter_assistant, 'MANAGER'):
    dexter_assistant.MANAGER.start_all = MagicMock()
    stub = dexter_assistant.MANAGER.start_all
else:
    # Fallback if MANAGER is not directly in dexter_assistant but inside app or similar
    # Given the prompt, it expects it on dexter_assistant
    print("MANAGER not found in dexter_assistant")
    sys.exit(1)

# Get the app for testing
app = dexter_assistant.app
app.testing = True

with app.test_client() as client:
    response = client.post('/auth/login', data={
        'username': 'arnoldrjr@gmail.com',
        'password': 'Passramirez4!'
    }, follow_redirects=True)
    
    print(f"Stub called: {stub.called}")
    print(f"Status code: {response.status_code}")
