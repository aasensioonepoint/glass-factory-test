"""
CtagsIndexer: Extracts AST symbols (functions, classes, methods) from source code.
Aliments symbol maps for LSP resolution and tool scope-slicing.
"""

import re
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Union


class CtagsIndexer:
    """Extracts symbols using ctags CLI with fallback regex parsing."""

    def __init__(self, ctags_bin: str = "ctags"):
        self.ctags_bin = ctags_bin
        self.has_ctags = shutil.which(ctags_bin) is not None

    def extract_symbols(self, file_path: Union[str, Path]) -> List[str]:
        """Extracts symbol definitions from a source code file."""
        path_obj = Path(file_path)
        if not path_obj.exists():
            return []

        if self.has_ctags:
            try:
                cmd = [self.ctags_bin, "-f", "-", "--output-format=json", str(path_obj)]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if res.returncode == 0 and res.stdout.strip():
                    symbols = []
                    for line in res.stdout.splitlines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            symbols.append(f"{data.get('kind', 'symbol')}:{data.get('name')}")
                        except Exception:
                            pass
                    if symbols:
                        return symbols
            except Exception:
                pass

        # Fallback regex symbol extractor for Python, JS/TS
        content = path_obj.read_text(encoding="utf-8", errors="ignore")
        symbols: List[str] = []

        # Functions & Classes (Python)
        py_matches = re.findall(r'^\s*(def|class)\s+([A-Za-z0-9_]+)', content, re.MULTILINE)
        for kind, name in py_matches:
            symbols.append(f"{kind}:{name}")

        # JS/TS Functions & Classes
        js_matches = re.findall(r'^\s*(export\s+)?(function|class|const|let|var)\s+([A-Za-z0-9_]+)', content, re.MULTILINE)
        for _, kind, name in js_matches:
            symbols.append(f"{kind}:{name}")

        return sorted(list(set(symbols)))
