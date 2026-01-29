#!/usr/bin/env python3
"""
ISO转rootfs工具
通过调用iso2qcow2和qcow2rootfs实现ISO到rootfs的转换
"""
import sys
import os
import argparse
import random
import logging
import logging.config
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from iso2qcow2 import iso2qcow2
from qcow2rootfs import qcow2rootfs


def init_logger():
    os.makedirs('logs', exist_ok=True)
    logger_config = os.path.join(str(Path(__file__).parent.parent), 'config','logger.conf')
    print(f"logger_config: {logger_config}")
    logging.config.fileConfig(logger_config, encoding="utf-8")
    return logging.getLogger('common')

logger = init_logger()

def iso2rootfs(iso_path, output_dir, preseed_file=None, ks_file=None,
               disk_size='20G', memory=2048, vcpus=2, timeout=3600,
               kernel_output=None, create_cgz=True, keep_qcow2=False,
               distribution=None, http_port=8080, modules_output=None,
               repo=None, repo_extra=None):
    """
    将ISO转换为rootfs
    
    Args:
        iso_path: ISO文件路径
        output_dir: 输出目录
        preseed_file: Preseed文件路径（Debian/Ubuntu）
        ks_file: Kickstart文件路径（RHEL/CentOS/Fedora/OpenEuler）
        disk_size: 磁盘大小
        memory: 内存大小（MB）
        vcpus: CPU核心数
        timeout: 安装超时时间（秒）
        kernel_output: kernel输出路径
        create_cgz: 是否创建cgz压缩包
        keep_qcow2: 是否保留中间QCOW2文件
        distribution: 发行版名称（用于自动选择模板）
        http_port: http服务端口号
        modules_output: 内核模块输出文件路径（可选）
        repo: 仓库镜像配置模板名
        repo_extra: 仓库镜像配置模板中要替换的变量和对应的值


    """
    iso_path = Path(iso_path).resolve()
    if not iso_path.exists():
        raise FileNotFoundError(f"ISO文件不存在: {iso_path}")
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建临时QCOW2文件
    temp_code = ''.join(random.choices('0123456789ABCDEF', k=6))
    temp_qcow2 = output_dir / f"{iso_path.stem}_{temp_code}.qcow2"
    
    try:
        # 步骤1: ISO转QCOW2
        logger.info("=" * 60)
        logger.info("步骤1: ISO转QCOW2")
        logger.info("=" * 60)
        iso2qcow2(
            str(iso_path),
            str(temp_qcow2),
            preseed_file=preseed_file,
            ks_file=ks_file,
            disk_size=disk_size,
            memory=memory,
            vcpus=vcpus,
            timeout=timeout,
            distribution=distribution,
            http_port=http_port
        )
        
        # 步骤2: QCOW2转rootfs
        logger.info("\n" + "=" * 60)
        logger.info("步骤2: QCOW2转rootfs")
        logger.info("=" * 60)
        result = qcow2rootfs(
            str(temp_qcow2),
            str(output_dir),
            kernel_output=kernel_output,
            create_cgz=create_cgz,
            modules_output=modules_output,
            repo=repo,
            repo_extra=repo_extra
        )
        
        # 清理临时QCOW2文件（如果不需要保留）
        if not keep_qcow2 and temp_qcow2.exists():
            logger.info(f"\n清理临时QCOW2文件: {temp_qcow2}")
            temp_qcow2.unlink()
        elif keep_qcow2:
            logger.info(f"\n保留QCOW2文件: {temp_qcow2}")
        
        logger.info("\n" + "=" * 60)
        logger.info("转换完成!")
        logger.info("=" * 60)
        logger.debug(f"输出目录: {output_dir}")
        logger.debug(f"Kernel: {result['kernel']}")
        logger.debug(f"Rootfs目录: {result['rootfs_dir']}")
        if result['rootfs_cgz']:
            logger.info(f"Rootfs压缩包: {result['rootfs_cgz']}")
        if result.get('modules_cgz'):
            logger.info(f"内核模块压缩包: {result['modules_cgz']}")
        if result.get('repo_updated'):
            logger.info(f"✓ 仓库镜像已更新")
        
        return result
    
    except Exception as e:
        logger.error(f"发生错误：{e}，根据keep_qcow2参数：{keep_qcow2}决定是否清理")
        if not keep_qcow2 and temp_qcow2.exists():
            try:
                temp_qcow2.unlink()
            except Exception:
                pass
        raise


def main():
    parser = argparse.ArgumentParser(
        description='ISO转rootfs工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # Debian/Ubuntu ISO转rootfs
  %(prog)s -i debian.iso -o ./output -p preseed.cfg
  
  # RHEL/CentOS ISO转rootfs
  %(prog)s -i centos.iso -o ./output -k ks.ks
  
  # 保留中间QCOW2文件
  %(prog)s -i debian.iso -o ./output -p preseed.cfg --keep-qcow2
        """
    )
    
    parser.add_argument('-i', '--iso', required=True, help='ISO文件路径')
    parser.add_argument('-o', '--output', required=True, help='输出目录')
    parser.add_argument('-p', '--preseed', help='Preseed文件路径（Debian/Ubuntu）')
    parser.add_argument('-k', '--kickstart', help='Kickstart文件路径（RHEL/CentOS/Fedora/OpenEuler）')
    parser.add_argument('-d', '--distribution', 
                        choices=['debian', 'ubuntu', 'openeuler', 'centos', 'rhel', 'fedora'],
                        help='指定发行版名称（用于自动选择模板，如果不指定则从ISO文件名检测）')
    
    # virt-install参数
    parser.add_argument('-s', '--size', default='20G', help='磁盘大小（默认: 20G）')
    parser.add_argument('-m', '--memory', type=int, default=2048, help='内存大小MB（默认: 2048）')
    parser.add_argument('-c', '--vcpus', type=int, default=2, help='CPU核心数（默认: 2）')
    parser.add_argument('-t', '--timeout', type=int, default=3600, help='安装超时时间秒（默认: 3600）')
    
    # rootfs参数
    parser.add_argument('--kernel', help='Kernel输出路径（默认: output_dir/kernel）')
    parser.add_argument('--no-cgz', action='store_true', help='不创建cgz压缩包')
    parser.add_argument('--keep-qcow2', action='store_true', help='保留中间QCOW2文件')
    parser.add_argument('--modules', help='内核模块输出文件路径（可选）')
    parser.add_argument('--http-port', type=int, default=8080, help='HTTP服务器端口（默认: 8080）')
    parser.add_argument('--repo', help='repo模板, 比如openeuler,bytedance')
    parser.add_argument('--repo-extra', help='repo源中要替换的变量,以键值对方式提供，多个键值对用逗号分隔')

    
    args = parser.parse_args()

    retry_times = 0
    max_retry_times = 2
    while retry_times <= max_retry_times:
        try:
            iso2rootfs(
                args.iso,
                args.output,
                preseed_file=args.preseed,
                ks_file=args.kickstart,
                disk_size=args.size,
                memory=args.memory,
                vcpus=args.vcpus,
                timeout=args.timeout,
                kernel_output=args.kernel,
                create_cgz=not args.no_cgz,
                keep_qcow2=args.keep_qcow2,
                distribution=args.distribution,
                http_port=args.http_port,
                modules_output=args.modules,
                repo=args.repo,
                repo_extra=args.repo_extra
            )
            break
        except KeyboardInterrupt:
            logger.error(f"\n\n用户中断")
            sys.exit(1)
        except Exception as e:
            retry_times += 1
            if retry_times > max_retry_times:
                logger.warning(f"发生错误: {e}，已完成{retry_times}次重试，退出...")
                import traceback
                traceback.print_exc()
                sys.exit(1)
            logger.warning(f"发生错误: {e}，进行第{retry_times}次重试")


if __name__ == "__main__":
    main()

