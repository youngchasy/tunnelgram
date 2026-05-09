# Optional helper. Run from project root on Windows after testing from source.
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --noconsole --name TunnelGramDirect --collect-all tunnelgram -m tunnelgram.gui
Write-Host "Built: dist\TunnelGramDirect\TunnelGramDirect.exe"
