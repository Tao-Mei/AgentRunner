"""Generate Windows resources from the runtime's version constants."""
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agentrunner import DISPLAY_VERSION, WINDOWS_VERSION, __version__


def main():
    config = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    if config['project']['version'] != __version__:
        raise ValueError('Package and runtime versions differ')
    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    keys = {'CompanyName': 'Tao Mei', 'FileDescription': 'AgentRunner', 'FileVersion': '.'.join(map(str, WINDOWS_VERSION)), 'ProductName': 'AgentRunner', 'ProductVersion': DISPLAY_VERSION, 'LegalCopyright': 'Tao Mei'}
    strings = ',\n'.join(f'StringStruct({key!r}, {value!r})' for key, value in keys.items())
    content = f"VSVersionInfo(ffi=FixedFileInfo(filevers={WINDOWS_VERSION!r}, prodvers={WINDOWS_VERSION!r}, mask=0x3f, flags=0x2, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)), kids=[StringFileInfo([StringTable('040904B0', [{strings}])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])"
    target.write_text(content, encoding='utf-8')
    print(json.dumps({'display': DISPLAY_VERSION, 'windows': keys['FileVersion'], 'package': __version__}))

if __name__ == '__main__':
    main()
