from pathlib import Path
import shutil
root = Path(__file__).resolve().parents[1]
if (root / 'dist').exists():
    shutil.rmtree(root / 'dist')
shutil.copytree(root / 'public', root / 'dist')
