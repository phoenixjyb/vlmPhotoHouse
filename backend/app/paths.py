import os
from pathlib import Path
DERIVED_PATH = Path(os.getenv('DERIVED_PATH', os.path.join(os.getenv('VLM_DATA_ROOT', r'E:\VLM_DATA'), 'derived')))
