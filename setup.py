#!/usr/bin/env python3
"""
环境设置脚本
使用uv来安装和管理依赖
"""

import subprocess
import sys
import os
from pathlib import Path


def check_uv():
    """检查uv是否已安装"""
    try:
        result = subprocess.run(['uv', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ uv已安装: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    
    print("✗ uv未安装")
    return False


def install_uv():
    """安装uv"""
    print("正在安装uv...")
    try:
        # 使用官方安装脚本
        subprocess.run([
            'curl', '-LsSf', 'https://astral.sh/uv/install.sh', '|', 'sh'
        ], shell=True, check=True)
        print("✓ uv安装完成")
        return True
    except Exception as e:
        print(f"✗ uv安装失败: {e}")
        print("请手动安装uv: https://github.com/astral-sh/uv")
        return False


def is_openeuler():
    """检测当前系统是否为openEuler"""
    try:
        with open('/etc/os-release', 'r') as f:
            content = f.read()
        import re
        # 检查ID或NAME字段是否包含openeuler（不区分大小写）
        if re.search(r'ID\s*=\s*["\']?openeuler["\']?', content, re.IGNORECASE):
            return True
        if re.search(r'NAME\s*=\s*["\']?openEuler["\']?', content, re.IGNORECASE):
            return True
    except FileNotFoundError:
        pass
    return False


def check_system_dependencies():
    """检查系统依赖"""
    dependencies = {
        'virt-install': 'libvirt',
        'qemu-nbd': 'qemu-utils',
        'virsh': 'libvirt',
        'cpio': 'cpio',
        'gzip': 'gzip',
        'mount': 'util-linux',
    }
    
    # 如果是openEuler，调整包名
    if is_openeuler():
        dependencies['qemu-nbd'] = 'qemu'  # openEuler中qemu-nbd在qemu包中
        extra_packages = ['edk2','virt-install']  # 额外需要edk2包
    else:
        extra_packages = []
    
    missing = []
    for cmd, package in dependencies.items():
        try:
            subprocess.run(['which', cmd], capture_output=True, check=True)
            print(f"✓ {cmd} 已安装")
        except subprocess.CalledProcessError:
            print(f"✗ {cmd} 未安装 (需要安装 {package})")
            missing.append((cmd, package))
    
    # 检查额外包（仅openEuler）
    if is_openeuler():
        for pkg in extra_packages:
            # 使用rpm检查包是否安装
            try:
                subprocess.run(['rpm', '-q', pkg], capture_output=True, check=True)
                print(f"✓ 包 {pkg} 已安装")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print(f"✗ 包 {pkg} 未安装 (需要安装 {pkg})")
                missing.append((pkg, pkg))  # 包名作为命令占位
    
    return missing


def setup_uv_environment():
    """设置uv虚拟环境"""
    project_root = Path(__file__).parent
    
    print("\n设置uv虚拟环境...")
    try:
        # 初始化uv项目（如果还没有）
        if not (project_root / '.python-version').exists():
            subprocess.run(['uv', 'python', 'install', '3.11'], check=True)
        
        # 同步依赖
        if (project_root / 'pyproject.toml').exists():
            subprocess.run(['uv', 'sync'], check=True)
            print("✓ 依赖已同步")
        else:
            print("⚠ pyproject.toml不存在，跳过依赖同步")
        
        return True
    except Exception as e:
        print(f"✗ 设置失败: {e}")
        return False


def main():
    print("=" * 60)
    print("RootFS生成工具 - 环境设置")
    print("=" * 60)
    
    # 检查uv
    if not check_uv():
        if input("\n是否安装uv? (y/N): ").lower() == 'y':
            if not install_uv():
                sys.exit(1)
        else:
            print("请先安装uv: https://github.com/astral-sh/uv")
            sys.exit(1)
    
    # 检查系统依赖
    print("\n检查系统依赖...")
    missing = check_system_dependencies()
    if missing:
        print("\n缺少以下系统依赖:")
        for cmd, package in missing:
            print(f"  - {cmd} (安装: {package})")
        print("\n请使用系统包管理器安装这些依赖")
        print("例如: sudo apt-get install libvirt qemu-utils cpio gzip")
    
    # 设置uv环境
    print("\n" + "=" * 60)
    setup_uv_environment()
    
    print("\n" + "=" * 60)
    print("环境设置完成!")
    print("=" * 60)
    print("\n使用以下命令激活环境:")
    print("  source .venv/bin/activate  # Linux/macOS")
    print("  或")
    print("  uv run <command>  # 使用uv运行命令")


if __name__ == "__main__":
    main()

