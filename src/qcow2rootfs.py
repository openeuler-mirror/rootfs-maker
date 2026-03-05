#!/usr/bin/env python3
# -*- encoding=utf-8 -*-
"""
# **********************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2020-2020. All rights reserved.
# [openeuler-jenkins] is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#          http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# Author:
# Create: 2026-03-05
# Description: QCOW2转rootfs工具
# 从QCOW2镜像中提取rootfs，分离kernel，并将rootfs打包为cgz格式
# **********************************************************************************
"""

import argparse
import importlib
import logging.config
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 添加lib目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from lib.cgz_utils import compress_cgz

# 导入pexpect用于guestfish交互
import pexpect

if not logging.getLogger().hasHandlers():
    os.makedirs('logs', exist_ok=True)
    logger_config = os.path.join(str(Path(__file__).parent.parent), 'config', 'logger.conf')
    print(f"logger_config: {logger_config}")
    logging.config.fileConfig(logger_config, encoding="utf-8")

logger = logging.getLogger("common")

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
    
    logger.info(f"使用guestfish导出QCOW2文件系统: {qcow2_path}")
    logger.info(f"输出到: {tar_output}")
    
    # 启动guestfish
    # -i: 自动检测并挂载文件系统
    # --ro: 只读模式
    # -a: 指定磁盘镜像
    cmd = ['guestfish', '-i', '--ro', '-a', str(qcow2_path)]
    
    child = pexpect.spawn(' '.join(cmd), timeout=300)
    child.logfile = sys.stdout.buffer
    
    try:
        # 等待guestfish提示符
        logger.info("等待guestfish就绪...")
        child.expect('><fs>', timeout=300)
        
        # 使用tar-out导出整个文件系统
        # compress:gzip - 使用gzip压缩
        # numericowner:true - 使用数字UID/GID
        # xattrs:true - 保留扩展属性
        # selinux:true - 保留SELinux上下文
        # acls:true - 保留ACL
        tar_cmd = f"tar-out / {tar_output} compress:gzip numericowner:true xattrs:true selinux:true acls:true"
        logger.debug(f"执行: {tar_cmd}")
        
        child.sendline(tar_cmd)
        
        # 等待命令完成（tar-out可能需要较长时间）
        logger.info("正在导出文件系统，请稍候...")
        child.expect('><fs>', timeout=1800)
        
        # 退出guestfish
        child.sendline('exit')
        child.expect(pexpect.EOF, timeout=30)
        
        if not tar_output.exists():
            raise RuntimeError(f"tar输出文件不存在: {tar_output}")
        
        logger.info(f"✓ 文件系统已导出到: {tar_output}")
        return True
        
    except pexpect.TIMEOUT:
        logger.error("错误: guestfish操作超时")
        child.kill(9)
        child.close(force=True)
        return False
    except Exception as e:
        logger.error(f"错误: {e}")
        child.kill(9)
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
        retry_times = 0
        max_retries = 2
        while retry_times <= max_retries:
            if extract_qcow2_with_guestfish(qcow2_path, temp_tar):
                logger.debug("guestfish导出成功")
                break
            retry_times += 1
            logger.debug(f"第{retry_times}次进行guestfish导出重试")
        if retry_times > max_retries:
            logger.debug(f"guestfish导出重试{retry_times}次失败")
            raise RuntimeError("guestfish导出失败")
        
        # 解压tar文件到临时目录
        logger.info("解压tar文件...")
        temp_extract = tempfile.mkdtemp(prefix='qcow2_extract_')
        try:
            subprocess.run(
                ['tar', '-xzf', str(temp_tar), '-C', temp_extract],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 查找kernel
            logger.info("查找kernel文件...")
            extract_path = Path(temp_extract)
            kernels = find_kernel(str(extract_path))
            logger.info(f"找到kernel文件: {[str(k) for k in kernels]}")
            
            # 复制rootfs内容（排除kernel和虚拟文件系统）
            logger.info("复制rootfs内容...")
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
            
            # 注释掉fstab中未注释的行（防止启动时挂载）
            fstab_path = rootfs_output / 'etc' / 'fstab'
            if fstab_path.exists():
                logger.info(f"注释fstab: {fstab_path}")
                try:
                    subprocess.run(
                        ['sed', '-i', r's/^\([^#]\)/# \1/g', str(fstab_path)],
                        cwd=str(rootfs_output),
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    logger.info("✓ fstab已注释")
                except subprocess.CalledProcessError as e:
                    logger.warning(f"警告: 注释fstab失败: {e}")
            else:
                logger.info(f"提示: fstab文件不存在: {fstab_path}")
            # 提取kernel文件
            if kernels:
                main_kernel = sorted(kernels, key=lambda x: x.stat().st_mtime, reverse=True)[0]
                logger.info(f"提取kernel: {main_kernel} -> {kernel_output}")
                shutil.copy2(main_kernel, kernel_output)
            else:
                logger.warning("警告: 未找到kernel文件")
            
        finally:
            # 清理临时解压目录
            if os.path.exists(temp_extract):
                shutil.rmtree(temp_extract, ignore_errors=True)
        
        logger.info(f"Rootfs已提取到: {rootfs_output}")
        logger.info(f"Kernel已提取到: {kernel_output}")
        
    finally:
        # 清理临时tar文件
        if temp_tar.exists():
            temp_tar.unlink()

def update_repo(repo, repo_extra, rootfs_dir):
    logger.debug(f"repo模板: {repo}, repo模板参数：{repo_extra}")
    try:
        repo_extra_dic = {}
        if repo_extra:
            for extra in repo_extra.split(","):
                repo_extra_dic[extra.split("=")[0]] = extra.split("=")[1]
        # 导入repo_config中以repo变量命名的update_repo模块
        module_path = f"repo_config.{repo}.update_repo"
        logger.debug(f"import module {module_path}")
        update_repo_module = importlib.import_module(module_path)
        # 更新repo_config中并拷贝到rootfs目录中
        update_repo_module.update_repo_config(repo, repo_extra_dic, rootfs_dir)
    except Exception as e:
        logger.warning(f"警告: 更新仓库配置失败: {e}")

def qcow2rootfs(qcow2_path, output_dir, kernel_output=None, create_cgz=True, modules_output=None, repo=None, repo_extra=None):
    """
    将QCOW2转换为rootfs（提取kernel，打包为cgz）
    
    Args:
        qcow2_path: QCOW2镜像路径
        output_dir: 输出目录
        kernel_output: kernel输出路径
        create_cgz: 是否创建cgz压缩包
        modules_output: 内核模块输出文件路径（可选）
        repo: 仓库镜像配置模板名
        repo_extra: 仓库镜像配置模板中要替换的变量和对应的值
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    rootfs_dir = output_dir / 'rootfs'
    cgz_output = output_dir / 'rootfs.cgz'
    
    # 提取kernel和rootfs
    extract_kernel_and_rootfs(qcow2_path, output_dir, kernel_output)
    
    # 更新仓库配置并复制到rootfs（如果提供了链接）
    repo_updated = False
    if repo:
        update_repo(repo, repo_extra, rootfs_dir)
        repo_updated = True
    
    # 打包为cgz
    if create_cgz:
        logger.info(f"打包rootfs为cgz: {cgz_output}")
        compress_cgz(str(rootfs_dir), str(cgz_output))
        logger.info(f"Rootfs已打包为: {cgz_output}")
    
    # 打包内核模块
    modules_cgz = None
    if modules_output is not None:
        logger.info(f"打包内核模块到: {modules_output}")
        # 查找lib/modules目录
        modules_dir = rootfs_dir / 'lib' / 'modules'
        if not modules_dir.exists():
            raise FileNotFoundError(f"模块目录不存在: {modules_dir}")
        # 获取所有子目录（内核版本）
        subdirs = [d for d in modules_dir.iterdir() if d.is_dir()]
        if not subdirs:
            raise FileNotFoundError(f"模块目录下未找到内核版本子目录: {modules_dir}")
        # 选择最新的子目录（按名称降序排序）
        selected = sorted(subdirs, key=lambda d: d.name, reverse=True)[0]
        logger.info(f"选择内核模块版本: {selected.name}")
        # 使用compress_cgz压缩
        compress_cgz(str(selected), modules_output)
        modules_cgz = modules_output
    
    return {
        'kernel': kernel_output or (output_dir / 'kernel'),
        'rootfs_dir': rootfs_dir,
        'rootfs_cgz': cgz_output if create_cgz else None,
        'modules_cgz': modules_cgz,
        'repo_updated': repo_updated
    }


def main():
    parser = argparse.ArgumentParser(description='QCOW2转rootfs工具')
    parser.add_argument('-i', '--input', required=True, help='输入QCOW2文件路径')
    parser.add_argument('-o', '--output', required=True, help='输出目录')
    parser.add_argument('-k', '--kernel', help='Kernel输出路径（默认: output_dir/kernel）')
    parser.add_argument('--no-cgz', action='store_true', help='不创建cgz压缩包')
    parser.add_argument('--modules', help='内核模块输出文件路径（可选）')
    parser.add_argument('--repo', help='repo模板, 比如openeuler,bytedance')
    parser.add_argument('-d', '--distribution',
                        choices=['debian', 'ubuntu', 'openeuler', 'centos', 'rhel', 'fedora'],
                        help='指定发行版名称（用于确定使用哪个配置文件和目标路径）')
    parser.add_argument('--repo-extra', help='repo源中要替换的变量,以键值对方式提供，多个键值对用逗号分隔')

    args = parser.parse_args()

    # 处理仓库镜像链接（如果提供了）
    repo = args.repo
    repo_extra = args.repo_extra
    distribution = args.distribution

    try:
        result = qcow2rootfs(
            args.input,
            args.output,
            kernel_output=args.kernel,
            create_cgz=not args.no_cgz,
            modules_output=args.modules,
            repo=repo,
            repo_extra=repo_extra
        )

        logger.info("\n转换完成!")
        logger.info(f"Kernel: {result['kernel']}")
        logger.info(f"Rootfs目录: {result['rootfs_dir']}")
        if result['rootfs_cgz']:
            logger.info(f"Rootfs压缩包: {result['rootfs_cgz']}")
        if result['modules_cgz']:
            logger.info(f"内核模块压缩包: {result['modules_cgz']}")
        if result['repo_updated']:
            logger.info(f"✓ 仓库镜像已更新 (发行版: {distribution or 'debian'})")

    except Exception as e:
        logger.error(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()




