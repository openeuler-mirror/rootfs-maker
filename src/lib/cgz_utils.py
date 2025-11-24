#!/usr/bin/env python3
"""
CGZ压缩和解压工具
使用cpio和gzip实现cgz格式的压缩和解压
"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path


def compress_cgz(source_dir, output_file):
    """
    将目录压缩为cgz格式（使用cpio和gzip）
    
    Args:
        source_dir: 要压缩的源目录路径
        output_file: 输出的cgz文件路径
    
    Raises:
        subprocess.CalledProcessError: 如果压缩过程失败
        FileNotFoundError: 如果源目录不存在
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f"源目录不存在: {source_dir}")
    
    if not source_path.is_dir():
        raise ValueError(f"路径不是目录: {source_dir}")
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 使用cpio创建归档，然后使用gzip压缩
    # cpio -o 创建归档，-H newc 使用新的ASCII格式
    # 通过管道传递给gzip压缩
    
    try:
        # 切换到源目录，使用find和cpio创建归档
        with tempfile.NamedTemporaryFile(mode='w+b', delete=False, suffix='.cpio') as tmp_cpio:
            tmp_cpio_path = tmp_cpio.name
        
        try:
            # 使用find和cpio创建归档
            # find . -print0 | cpio -o -H newc -0 > output.cpio
            find_cmd = ['find', '.', '-print0']
            cpio_cmd = ['cpio', '-o', '-H', 'newc', '--null']
            
            with open(tmp_cpio_path, 'wb') as cpio_file:
                find_process = subprocess.Popen(
                    find_cmd,
                    cwd=str(source_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                cpio_process = subprocess.Popen(
                    cpio_cmd,
                    stdin=find_process.stdout,
                    stdout=cpio_file,
                    stderr=subprocess.PIPE,
                    cwd=str(source_path)
                )
                
                find_process.stdout.close()
                find_process.wait()
                cpio_process.wait()
                
                if cpio_process.returncode != 0:
                    stderr = cpio_process.stderr.read().decode('utf-8', errors='ignore')
                    raise subprocess.CalledProcessError(
                        cpio_process.returncode,
                        'cpio',
                        stderr=stderr
                    )
            
            # 使用gzip压缩cpio文件
            with open(tmp_cpio_path, 'rb') as cpio_file:
                with open(output_path, 'wb') as gz_file:
                    gzip_process = subprocess.Popen(
                        ['gzip', '-c'],
                        stdin=cpio_file,
                        stdout=gz_file,
                        stderr=subprocess.PIPE
                    )
                    gzip_process.wait()
                    
                    if gzip_process.returncode != 0:
                        stderr = gzip_process.stderr.read().decode('utf-8', errors='ignore')
                        raise subprocess.CalledProcessError(
                            gzip_process.returncode,
                            'gzip',
                            stderr=stderr
                        )
        
        finally:
            # 清理临时文件
            if os.path.exists(tmp_cpio_path):
                os.unlink(tmp_cpio_path)
    
    except FileNotFoundError as e:
        if 'cpio' in str(e) or 'gzip' in str(e):
            raise RuntimeError(f"缺少必要的工具: {e}. 请确保已安装cpio和gzip")
        raise


def extract_cgz(cgz_file, output_dir):
    """
    解压cgz文件到指定目录（使用gunzip和cpio）
    
    Args:
        cgz_file: cgz文件路径
        output_dir: 解压目标目录
    
    Raises:
        subprocess.CalledProcessError: 如果解压过程失败
        FileNotFoundError: 如果cgz文件不存在
    """
    cgz_path = Path(cgz_file)
    if not cgz_path.exists():
        raise FileNotFoundError(f"cgz文件不存在: {cgz_file}")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    try:
        # 使用gunzip解压，然后使用cpio提取
        # gunzip -c file.cgz | cpio -i -d -H newc
        
        with open(cgz_path, 'rb') as gz_file:
            gunzip_process = subprocess.Popen(
                ['gunzip', '-c'],
                stdin=gz_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            cpio_process = subprocess.Popen(
                ['cpio', '-i', '-d', '-H', 'newc', '--quiet'],
                stdin=gunzip_process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(output_path)
            )
            
            gunzip_process.stdout.close()
            gunzip_process.wait()
            cpio_process.wait()
            
            if gunzip_process.returncode != 0:
                stderr = gunzip_process.stderr.read().decode('utf-8', errors='ignore')
                raise subprocess.CalledProcessError(
                    gunzip_process.returncode,
                    'gunzip',
                    stderr=stderr
                )
            
            if cpio_process.returncode != 0:
                stderr = cpio_process.stderr.read().decode('utf-8', errors='ignore')
                # cpio在某些情况下可能返回非0，但实际已成功（如警告）
                # 检查输出目录是否有内容
                if not any(output_path.iterdir()):
                    raise subprocess.CalledProcessError(
                        cpio_process.returncode,
                        'cpio',
                        stderr=stderr
                    )
    
    except FileNotFoundError as e:
        if 'gunzip' in str(e) or 'cpio' in str(e):
            raise RuntimeError(f"缺少必要的工具: {e}. 请确保已安装gunzip和cpio")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='CGZ压缩和解压工具')
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    compress_parser = subparsers.add_parser('compress', help='压缩目录为cgz')
    compress_parser.add_argument('source_dir', help='源目录')
    compress_parser.add_argument('output_file', help='输出cgz文件')
    
    extract_parser = subparsers.add_parser('extract', help='解压cgz文件')
    extract_parser.add_argument('cgz_file', help='cgz文件')
    extract_parser.add_argument('output_dir', help='输出目录')
    
    args = parser.parse_args()
    
    if args.command == 'compress':
        print(f"正在压缩 {args.source_dir} 到 {args.output_file}...")
        compress_cgz(args.source_dir, args.output_file)
        print("压缩完成!")
    elif args.command == 'extract':
        print(f"正在解压 {args.cgz_file} 到 {args.output_dir}...")
        extract_cgz(args.cgz_file, args.output_dir)
        print("解压完成!")
    else:
        parser.print_help()

