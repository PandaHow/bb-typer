#!/usr/bin/env python3
"""
macOS 打包脚本 - 使用 PyInstaller 创建 .app 应用
Build script for macOS - Creates .app bundle using PyInstaller
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    # 确保在正确的目录
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # 安装 PyInstaller (如果没有)
    print("📦 检查 PyInstaller...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)
    
    # PyInstaller 参数
    app_name = "海外社区运营小助理"
    
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name', app_name,
        '--windowed',  # 不显示终端窗口
        '--onefile',   # 打包成单个文件
        '--noconfirm', # 覆盖之前的构建
        '--clean',     # 清理临时文件
        # 添加数据文件
        '--add-data', 'custom_dict.txt:.',
        # macOS 特定设置
        '--osx-bundle-identifier', 'com.twtyper.app',
        # 隐藏导入
        '--hidden-import', 'pynput.keyboard._darwin',
        '--hidden-import', 'pynput.mouse._darwin',
        '--hidden-import', 'PyQt5.sip',
        # 主程序
        'main.py'
    ]
    
    print(f"🔨 开始构建 {app_name}.app...")
    print(f"命令: {' '.join(cmd)}")
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print(f"\n✅ 构建成功!")
        print(f"📁 应用位置: {script_dir}/dist/{app_name}.app")
        print(f"\n使用方法:")
        print(f"  1. 将 {app_name}.app 拖到 Applications 文件夹")
        print(f"  2. 首次运行需要在 系统偏好设置 → 安全性与隐私 → 辅助功能 中授权")
        print(f"  3. 如果提示无法打开，右键点击 → 打开")
    else:
        print(f"\n❌ 构建失败，错误码: {result.returncode}")
        sys.exit(1)

if __name__ == '__main__':
    main()
