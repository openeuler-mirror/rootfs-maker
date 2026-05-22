#!/usr/bin/env python3
# -*- encoding=utf-8 -*-
"""
# **********************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
# [rootfs-maker] is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#          http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# Author:
# Create: 2026-03-05
# Description: Docker转rootfs工具
# 从Docker镜像中提取rootfs，分离kernel，并将rootfs打包为cgz格式
# **********************************************************************************
"""

import argparse
import logging.config
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 添加lib目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from lib.cgz_utils import compress_cgz

if not logging.getLogger().hasHandlers():
    log_dir = Path(__file__).resolve().parent.parent / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    logger_config = os.path.join(str(Path(__file__).parent.parent), 'config', 'logger.conf')
    logging.config.fileConfig(logger_config, encoding="utf-8")

logger = logging.getLogger("common")

def extract_docker_image(image_name, output_dir):
    """
    从Docker镜像中提取文件系统
    
    Args:
        image_name: Docker镜像名称（可以是tag或ID）
        output_dir: 输出目录
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    rootfs_dir = output_dir / 'rootfs'
    rootfs_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建临时容器
    temp_container = f"docker2rootfs_{os.getpid()}"
    
    try:
        # 检查镜像是否存在
        result = subprocess.run(
            ['docker', 'inspect', image_name],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Docker镜像不存在: {image_name}")
        
        # 创建临时容器（不启动）
        logger.info(f"创建临时容器: {temp_container}")
        subprocess.run(
            ['docker', 'create', '--name', temp_container, image_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 导出容器文件系统
        logger.info("导出容器文件系统...")
        export_process = subprocess.Popen(
            ['docker', 'export', temp_container],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 使用tar解压到rootfs目录
        extract_process = subprocess.Popen(
            ['tar', '-xf', '-', '-C', str(rootfs_dir)],
            stdin=export_process.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        export_process.stdout.close()
        export_process.wait()
        extract_process.wait()
        
        if export_process.returncode != 0:
            raise RuntimeError(f"导出失败: {export_process.stderr.read().decode()}")
        
        if extract_process.returncode != 0:
            stderr = extract_process.stderr.read().decode('utf-8', errors='ignore')
            raise RuntimeError(f"解压失败: {stderr}")
        
        logger.info(f"文件系统已导出到: {rootfs_dir}")
        
        return rootfs_dir
    
    finally:
        # 清理临时容器
        try:
            subprocess.run(
                ['docker', 'rm', temp_container],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except Exception:
            pass


def find_kernel_in_rootfs(rootfs_dir):
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


def docker2rootfs(image_name, output_dir, kernel_output=None, create_cgz=True):
    """
    将Docker镜像转换为rootfs（提取kernel，打包为cgz）
    
    Args:
        image_name: Docker镜像名称
        output_dir: 输出目录
        kernel_output: kernel输出路径（如果为None，则放在output_dir中）
        create_cgz: 是否创建cgz压缩包
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if kernel_output is None:
        kernel_output = output_dir / 'kernel'
    else:
        kernel_output = Path(kernel_output)
        kernel_output.parent.mkdir(parents=True, exist_ok=True)
    
    rootfs_dir = output_dir / 'rootfs'
    cgz_output = output_dir / 'rootfs.cgz'
    
    # 提取Docker镜像文件系统
    logger.info("=" * 60)
    logger.info("步骤1: 从Docker镜像提取文件系统")
    logger.info("=" * 60)
    extracted_rootfs = extract_docker_image(image_name, output_dir)
    
    # 查找并提取kernel
    logger.info("\n" + "=" * 60)
    logger.info("步骤2: 查找和提取kernel")
    logger.info("=" * 60)
    kernels = find_kernel_in_rootfs(str(extracted_rootfs))
    
    if kernels:
        # 使用第一个找到的kernel（通常是最新的）
        main_kernel = sorted(kernels, key=lambda x: x.stat().st_mtime, reverse=True)[0]
        logger.info(f"找到kernel: {main_kernel}")
        logger.info(f"提取到: {kernel_output}")
        shutil.copy2(main_kernel, kernel_output)
        
        # 从rootfs中删除kernel
        try:
            rel_path = main_kernel.relative_to(extracted_rootfs)
            kernel_in_rootfs = extracted_rootfs / rel_path
            if kernel_in_rootfs.exists():
                kernel_in_rootfs.unlink()
                # 如果父目录为空，也删除
                parent = kernel_in_rootfs.parent
                if parent != extracted_rootfs and not any(parent.iterdir()):
                    try:
                        parent.rmdir()
                    except Exception:
                        pass
        except ValueError:
            pass
    else:
        logger.warning("警告: 未找到kernel文件（Docker镜像通常不包含kernel）")
        # 创建一个空文件或占位符
        kernel_output.touch()
    
    # 打包为cgz
    if create_cgz:
        logger.info("\n" + "=" * 60)
        logger.info("步骤3: 打包rootfs为cgz")
        logger.info("=" * 60)
        logger.info(f"打包rootfs为cgz: {cgz_output}")
        compress_cgz(str(extracted_rootfs), str(cgz_output))
        logger.info(f"Rootfs已打包为: {cgz_output}")
    
    logger.info("\n" + "=" * 60)
    logger.info("转换完成!")
    logger.info("=" * 60)
    
    return {
        'kernel': kernel_output,
        'rootfs_dir': extracted_rootfs,
        'rootfs_cgz': cgz_output if create_cgz else None
    }


def main():
    parser = argparse.ArgumentParser(
        description='Docker转rootfs工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从Docker镜像提取rootfs
  %(prog)s -i ubuntu:20.04 -o ./output
  
  # 指定kernel输出路径
  %(prog)s -i centos:7 -o ./output --kernel ./kernel
  
  # 不创建cgz压缩包
  %(prog)s -i alpine:latest -o ./output --no-cgz
  
注意:
  - Docker镜像通常不包含kernel，kernel文件可能为空
  - 需要Docker守护进程运行
        """
    )
    
    parser.add_argument('-i', '--image', required=True, help='Docker镜像名称（tag或ID）')
    parser.add_argument('-o', '--output', required=True, help='输出目录')
    parser.add_argument('--kernel', help='Kernel输出路径（默认: output_dir/kernel）')
    parser.add_argument('--no-cgz', action='store_true', help='不创建cgz压缩包')
    
    args = parser.parse_args()
    
    # 检查Docker是否可用
    try:
        subprocess.run(
            ['docker', '--version'],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("错误: Docker未安装或不可用")
        sys.exit(1)
    
    try:
        result = docker2rootfs(
            args.image,
            args.output,
            kernel_output=args.kernel,
            create_cgz=not args.no_cgz
        )
        
        logger.info(f"\n输出目录: {args.output}")
        logger.info(f"Kernel: {result['kernel']}")
        logger.info(f"Rootfs目录: {result['rootfs_dir']}")
        if result['rootfs_cgz']:
            logger.info(f"Rootfs压缩包: {result['rootfs_cgz']}")
    
    except KeyboardInterrupt:
        logger.error("\n\n用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

