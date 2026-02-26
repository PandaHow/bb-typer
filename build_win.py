#!/usr/bin/env python3
import subprocess
import sys
import os
from pathlib import Path

def main():
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    print("📦 Installing PyInstaller...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)
    
    app_name = "海外社区运营小助理"
    
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name', app_name,
        '--windowed',
        '--onefile',
        '--noconfirm',
        '--clean',
        '--add-data', 'custom_dict.txt;.',
        '--hidden-import', 'pynput.keyboard._win32',
        '--hidden-import', 'pynput.mouse._win32',
        '--hidden-import', 'PyQt5.sip',
        'main.py'
    ]
    
    print(f"🔨 Building {app_name}.exe...")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print(f"\n✅ Build successful!")
        print(f"📁 Location: {script_dir}\\dist\\{app_name}.exe")
        print(f"\nUsage:")
        print(f"  1. Copy {app_name}.exe to desired location")
        print(f"  2. Double-click to run")
        print(f"  3. May need to run as Administrator on first use")
    else:
        print(f"\n❌ Build failed with code: {result.returncode}")
        sys.exit(1)

if __name__ == '__main__':
    main()
