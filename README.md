# wlmouse battery
Tray icon for windows that displays battery percentage for wlmouse products (working on pulsar too) using [hidapi](https://pypi.org/project/hid/).

## Tested supported devices
* Beast X Mini 
* Beast X Mini Pro

## Build
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
python -m pip install -U pip wheel setuptools
python -m pip install -r requirements.txt
pyinstaller "wlmouse battery.spec"
```
`.exe` file will be in `.\dist`