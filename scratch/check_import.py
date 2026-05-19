import sys
from pathlib import Path

# Add workspace root to path
workspace_path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace_path))

try:
    from services.backend.main import app
    print("FastAPI App imported successfully!")
except Exception as e:
    import traceback
    print("Import Failed!")
    traceback.print_exc()
