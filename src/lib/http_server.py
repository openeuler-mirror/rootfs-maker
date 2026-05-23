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
# Description: HTTP服务器模块, 用于提供preseed和kickstart配置文件
# **********************************************************************************
"""

import http.server
import socketserver
import threading
import time
import socket
import logging

logger = logging.getLogger("common")


def _safe_translate_path(base_dir, path):
    """Map request paths into the served directory without allowing escapes."""
    import os

    request_path = path.split('?', 1)[0]
    request_path = request_path.split('#', 1)[0]
    request_path = request_path.lstrip('/')
    joined = os.path.abspath(os.path.join(base_dir, request_path))
    base_abs = os.path.abspath(base_dir)
    if os.path.commonpath([base_abs, joined]) != base_abs:
        return base_abs
    return joined

def get_host_ip():
    """获取主机IP地址，用于HTTP服务器"""
    try:
        # 方法1: 尝试获取libvirt默认网络的网关IP
        try:
            import subprocess
            result = subprocess.run(
                ['virsh', 'net-info', 'default'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Bridge:' in line:
                        bridge = line.split(':')[1].strip()
                        # 获取桥接接口的IP
                        result = subprocess.run(
                            ['ip', 'addr', 'show', bridge],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            import re
                            match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
                            if match:
                                return match.group(1)
        except Exception:
            pass
        
        # 方法2: 创建一个UDP socket来获取默认路由接口的IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # 回退方案
        return "192.168.122.1"  # libvirt默认网络网关


class ConfigHTTPServer:
    """配置文件HTTP服务器"""
    
    def __init__(self, directory, port=0):
        """
        初始化HTTP服务器
        
        Args:
            directory: 服务目录路径
            port: 端口号（默认0,随机端口）
        """
        self.directory = str(directory)
        self.port = port
        self.httpd = None
        self.thread = None
    
    def start(self):
        """启动HTTP服务器"""
        import os
        
        class CustomHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
            
            def translate_path(self, path):
                # 将请求路径转换为文件系统路径
                # 移除查询字符串和片段
                path = path.split('?', 1)[0]
                path = path.split('#', 1)[0]
                # 移除前导斜杠
                path = path.lstrip('/')
                # 构建完整路径
                return _safe_translate_path(self.directory, path)
        
        CustomHandler.directory = self.directory
        
        self.httpd = socketserver.TCPServer(("", self.port), CustomHandler)
        
        def serve():
            self.httpd.serve_forever()
        
        self.thread = threading.Thread(target=serve, daemon=True)
        self.thread.start()
        time.sleep(1)  # 等待服务器启动
        return self
    
    def stop(self):
        """停止HTTP服务器"""
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
    
    def get_url(self, filename):
        """
        获取文件的HTTP URL
        
        Args:
            filename: 文件名
        
        Returns:
            完整的HTTP URL
        """
        return f"http://{get_host_ip()}:{self.port}/{filename}"


def start_http_server(directory, port=0):
    """
    启动HTTP服务器提供preseed/ks文件（兼容函数）

    Args:
        directory: 服务目录路径
        port: 端口号

    Returns:
        (httpd, thread) 元组，用于后续清理
    """
    import os
    
    class CustomHandler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            # 将请求路径转换为文件系统路径
            # 移除查询字符串和片段
            path = path.split('?', 1)[0]
            path = path.split('#', 1)[0]
            # 移除前导斜杠
            path = path.lstrip('/')
            # 构建完整路径
            return _safe_translate_path(directory, path)
    
    httpd = socketserver.TCPServer(("", port), CustomHandler)
    actual_port = httpd.server_address[1]

    def serve():
        httpd.serve_forever()
    
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    
    # 等待服务器启动并验证
    max_retries = 5
    for i in range(max_retries):
        try:
            # 测试服务器是否可访问
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(2)
            result = test_socket.connect_ex(('127.0.0.1', actual_port))
            test_socket.close()
            if result == 0:
                logger.info(f"HTTP服务器在端口 {actual_port} 上成功启动")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        logger.warning(f"警告: HTTP服务器可能未在端口 {actual_port} 上正确启动")
    
    return httpd, thread, actual_port


def check_http_server_accessible(ip, port, filename, timeout=10):
    """
    检查HTTP服务器是否可以从指定IP访问
    
    Args:
        ip: 要检查的IP地址
        port: 端口号
        filename: 要检查的文件名
        timeout: 超时时间（秒）
    
    Returns:
        bool: 是否可访问
    """
    import urllib.request
    import urllib.error
    
    url = f"http://{ip}:{port}/{filename}"
    
    try:
        response = urllib.request.urlopen(url, timeout=timeout)
        if response.getcode() == 200:
            logger.info(f"HTTP服务器可访问: {url}")
            return True
    except Exception as e:
        logger.error(f"HTTP服务器不可访问: {url}, 错误: {e}")
    
    return False


def check_firewall_status(port=8080):
    """
    检查防火墙状态并尝试开放端口
    
    Args:
        port: 要检查的端口号
    """
    import subprocess
    
    logger.info(f"检查防火墙状态，端口 {port}...")
    
    # 检查firewalld
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'firewalld'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and 'active' in result.stdout:
            logger.info("检测到firewalld正在运行")
            # 检查端口是否开放
            result = subprocess.run(
                ['firewall-cmd', '--list-ports'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                ports = result.stdout.strip().split()
                if f"{port}/tcp" not in ports:
                    logger.info(f"端口 {port}/tcp 未在firewalld中开放")
                    logger.info(f"建议运行: sudo firewall-cmd --add-port={port}/tcp --permanent && sudo firewall-cmd --reload")
                    return False
                else:
                    logger.info(f"端口 {port}/tcp 已在firewalld中开放")
                    return True
    except Exception:
        pass
    
    # 检查ufw
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'ufw'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and 'active' in result.stdout:
            logger.info("检测到ufw正在运行")
            result = subprocess.run(
                ['ufw', 'status'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and f"{port}/tcp" not in result.stdout:
                logger.info(f"端口 {port}/tcp 未在ufw中开放")
                logger.info(f"建议运行: sudo ufw allow {port}/tcp")
                return False
            else:
                logger.info(f"端口 {port}/tcp 已在ufw中开放")
                return True
    except Exception:
        pass
    
    logger.info("未检测到活跃的防火墙或端口已开放")
    return True
