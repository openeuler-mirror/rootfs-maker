#!/usr/bin/env python3
"""
ISO转rootfs工具
通过调用iso2qcow2和qcow2rootfs实现ISO到rootfs的转换
"""

import os
import sys
import argparse
import tempfile
import shutil
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from iso2qcow2 import iso2qcow2
from qcow2rootfs import qcow2rootfs


def iso2rootfs(iso_path, output_dir, preseed_file=None, ks_file=None,
               disk_size='20G', memory=2048, vcpus=2, timeout=3600,
               kernel_output=None, create_cgz=True, keep_qcow2=False,
               distribution=None, http_port=8080):
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
    """
    iso_path = Path(iso_path).resolve()
    if not iso_path.exists():
        raise FileNotFoundError(f"ISO文件不存在: {iso_path}")
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建临时QCOW2文件
    temp_qcow2 = output_dir / f"{iso_path.stem}_temp.qcow2"
    
    try:
        # 步骤1: ISO转QCOW2
        print("=" * 60)
        print("步骤1: ISO转QCOW2")
        print("=" * 60)
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
        print("\n" + "=" * 60)
        print("步骤2: QCOW2转rootfs")
        print("=" * 60)
        result = qcow2rootfs(
            str(temp_qcow2),
            str(output_dir),
            kernel_output=kernel_output,
            create_cgz=create_cgz
        )
        
        # 清理临时QCOW2文件（如果不需要保留）
        if not keep_qcow2 and temp_qcow2.exists():
            print(f"\n清理临时QCOW2文件: {temp_qcow2}")
            temp_qcow2.unlink()
        elif keep_qcow2:
            print(f"\n保留QCOW2文件: {temp_qcow2}")
        
        print("\n" + "=" * 60)
        print("转换完成!")
        print("=" * 60)
        print(f"输出目录: {output_dir}")
        print(f"Kernel: {result['kernel']}")
        print(f"Rootfs目录: {result['rootfs_dir']}")
        if result['rootfs_cgz']:
            print(f"Rootfs压缩包: {result['rootfs_cgz']}")
        
        return result
    
    except Exception as e:
        # 发生错误时，根据keep_qcow2决定是否清理
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
    parser.add_argument('--http-port', type=int, default=8080, help='HTTP服务器端口（默认: 8080）')
    
    args = parser.parse_args()
    
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
            http_port=args.http_port
        )
    except KeyboardInterrupt:
        print("\n\n用户中断", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

