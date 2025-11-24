#!/usr/bin/env python3
"""
QCOW2转rootfs工具
从QCOW2镜像中提取rootfs，分离kernel，并将rootfs打包为cgz格式
"""

import os
import sys
import subprocess
import tempfile
import shutil
import argparse
from pathlib import Path

# 添加lib目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from lib.cgz_utils import compress_cgz

# 导入pexpect用于guestfish交互
import pexpect


def check_guestfish():
    """检查guestfish是否可用"""
    try:
        result = subprocess.run(
            ['guestfish', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def extract_qcow2_with_guestfish(qcow2_path, tar_output):
    """
    使用guestfish的tar-out命令直接导出QCOW2文件系统
    
    Args:
        qcow2_path: QCOW2镜像路径
        tar_output: 输出的tar.gz文件路径
    
    Returns:
        True if successful
    """
    qcow2_path = Path(qcow2_path).resolve()
    tar_output = Path(tar_output)
    tar_output.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"使用guestfish导出QCOW2文件系统: {qcow2_path}")
    print(f"输出到: {tar_output}")
    
    # 启动guestfish
    # -i: 自动检测并挂载文件系统
    # --ro: 只读模式
    # -a: 指定磁盘镜像
    cmd = ['guestfish', '-i', '--ro', '-a', str(qcow2_path)]
    
    child = pexpect.spawn(' '.join(cmd), timeout=300)
    child.logfile = sys.stdout.buffer
    
    try:
        # 等待guestfish提示符
        print("等待guestfish就绪...")
        child.expect('><fs>', timeout=300)
        
        # 使用tar-out导出整个文件系统
        # compress:gzip - 使用gzip压缩
        # numericowner:true - 使用数字UID/GID
        # xattrs:true - 保留扩展属性
        # selinux:true - 保留SELinux上下文
        # acls:true - 保留ACL
        tar_cmd = f"tar-out / {tar_output} compress:gzip numericowner:true xattrs:true selinux:true acls:true"
        print(f"执行: {tar_cmd}")
        
        child.sendline(tar_cmd)
        
        # 等待命令完成（tar-out可能需要较长时间）
        print("正在导出文件系统，请稍候...")
        child.expect('><fs>', timeout=1800)
        
        # 退出guestfish
        child.sendline('exit')
        child.expect(pexpect.EOF, timeout=30)
        
        if not tar_output.exists():
            raise RuntimeError(f"tar输出文件不存在: {tar_output}")
        
        print(f"✓ 文件系统已导出到: {tar_output}")
        return True
        
    except pexpect.TIMEOUT:
        print("错误: guestfish操作超时")
        child.close(force=True)
        return False
    except Exception as e:
        print(f"错误: {e}")
        child.close(force=True)
        return False


def find_kernel(rootfs_dir):
    """
    在rootfs中查找kernel文件
    
    Returns:
        kernel文件路径列表
    """
    kernel_paths = []
    rootfs_path = Path(rootfs_dir)
    
    # 常见的kernel位置
    kernel_locations = [
        'boot/vmlinuz*',
        'boot/vmlinux*',
        'boot/kernel*',
        'vmlinuz*',
        'vmlinux*',
    ]
    
    for pattern in kernel_locations:
        for kernel in rootfs_path.glob(pattern):
            if kernel.is_file():
                kernel_paths.append(kernel)
    
    # 也检查/boot/目录下的所有文件
    boot_dir = rootfs_path / 'boot'
    if boot_dir.exists():
        for item in boot_dir.iterdir():
            if item.is_file() and ('vmlinuz' in item.name.lower() or 
                                   'vmlinux' in item.name.lower() or
                                   'kernel' in item.name.lower()):
                if item not in kernel_paths:
                    kernel_paths.append(item)
    
    return kernel_paths


def extract_kernel_and_rootfs(qcow2_path, output_dir, kernel_output=None):
    """
    从QCOW2镜像中提取kernel和rootfs（使用guestfish tar-out）
    
    Args:
        qcow2_path: QCOW2镜像路径
        output_dir: 输出目录
        kernel_output: kernel输出路径（如果为None，则放在output_dir中）
    """
    qcow2_path = Path(qcow2_path).resolve()
    if not qcow2_path.exists():
        raise FileNotFoundError(f"QCOW2文件不存在: {qcow2_path}")
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if kernel_output is None:
        kernel_output = output_dir / 'kernel'
    else:
        kernel_output = Path(kernel_output)
        kernel_output.parent.mkdir(parents=True, exist_ok=True)
    
    rootfs_output = output_dir / 'rootfs'
    rootfs_output.mkdir(parents=True, exist_ok=True)
    
    # 检查guestfish是否可用
    if not check_guestfish():
        raise RuntimeError(
            "guestfish未安装或不可用。\n"
            "请安装libguestfs-tools: sudo apt-get install libguestfs-tools"
        )
    
    # 创建临时tar文件
    temp_tar = output_dir / 'rootfs_temp.tar.gz'
    
    try:
        # 使用guestfish导出文件系统
        if not extract_qcow2_with_guestfish(qcow2_path, temp_tar):
            raise RuntimeError("guestfish导出失败")
        
        # 解压tar文件到临时目录
        print("解压tar文件...")
        temp_extract = tempfile.mkdtemp(prefix='qcow2_extract_')
        try:
            subprocess.run(
                ['tar', '-xzf', str(temp_tar), '-C', temp_extract],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 查找kernel
            print("查找kernel文件...")
            extract_path = Path(temp_extract)
            kernels = find_kernel(str(extract_path))
            print(f"找到kernel文件: {[str(k) for k in kernels]}")
            
            # 复制rootfs内容（排除kernel和虚拟文件系统）
            print("复制rootfs内容...")
            kernel_relative_paths = set()
            for kernel in kernels:
                try:
                    rel_path = kernel.relative_to(extract_path)
                    kernel_relative_paths.add(str(rel_path))
                except ValueError:
                    pass
            
            # 复制文件，排除虚拟文件系统和kernel
            for item in extract_path.iterdir():
                if item.name in ['proc', 'sys', 'dev', 'run', 'tmp']:
                    continue
                
                rel_path = item.relative_to(extract_path)
                if str(rel_path) in kernel_relative_paths:
                    continue
                
                dest = rootfs_output / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, symlinks=True, ignore_dangling_symlinks=True)
                elif item.is_file():
                    shutil.copy2(item, dest)
                elif item.is_symlink():
                    if dest.exists():
                        dest.unlink()
                    try:
                        dest.symlink_to(item.readlink())
                    except Exception:
                        pass
            
            # 提取kernel文件
            if kernels:
                main_kernel = sorted(kernels, key=lambda x: x.stat().st_mtime, reverse=True)[0]
                print(f"提取kernel: {main_kernel} -> {kernel_output}")
                shutil.copy2(main_kernel, kernel_output)
            else:
                print("警告: 未找到kernel文件")
            
        finally:
            # 清理临时解压目录
            if os.path.exists(temp_extract):
                shutil.rmtree(temp_extract, ignore_errors=True)
        
        print(f"Rootfs已提取到: {rootfs_output}")
        print(f"Kernel已提取到: {kernel_output}")
        
    finally:
        # 清理临时tar文件
        if temp_tar.exists():
            temp_tar.unlink()


def qcow2rootfs(qcow2_path, output_dir, kernel_output=None, create_cgz=True):
    """
    将QCOW2转换为rootfs（提取kernel，打包为cgz）
    
    Args:
        qcow2_path: QCOW2镜像路径
        output_dir: 输出目录
        kernel_output: kernel输出路径
        create_cgz: 是否创建cgz压缩包
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    rootfs_dir = output_dir / 'rootfs'
    cgz_output = output_dir / 'rootfs.cgz'
    
    # 提取kernel和rootfs
    extract_kernel_and_rootfs(qcow2_path, output_dir, kernel_output)
    
    # 打包为cgz
    if create_cgz:
        print(f"打包rootfs为cgz: {cgz_output}")
        compress_cgz(str(rootfs_dir), str(cgz_output))
        print(f"Rootfs已打包为: {cgz_output}")
    
    return {
        'kernel': kernel_output or (output_dir / 'kernel'),
        'rootfs_dir': rootfs_dir,
        'rootfs_cgz': cgz_output if create_cgz else None
    }


def main():
    parser = argparse.ArgumentParser(description='QCOW2转rootfs工具')
    parser.add_argument('-i', '--input', required=True, help='输入QCOW2文件路径')
    parser.add_argument('-o', '--output', required=True, help='输出目录')
    parser.add_argument('-k', '--kernel', help='Kernel输出路径（默认: output_dir/kernel）')
    parser.add_argument('--no-cgz', action='store_true', help='不创建cgz压缩包')
    
    args = parser.parse_args()
    
    try:
        result = qcow2rootfs(
            args.input,
            args.output,
            kernel_output=args.kernel,
            create_cgz=not args.no_cgz
        )
        
        print("\n转换完成!")
        print(f"Kernel: {result['kernel']}")
        print(f"Rootfs目录: {result['rootfs_dir']}")
        if result['rootfs_cgz']:
            print(f"Rootfs压缩包: {result['rootfs_cgz']}")
    
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

