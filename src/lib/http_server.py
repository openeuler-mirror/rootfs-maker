#!/usr/bin/env python3
"""
HTTP服务器模块
用于提供preseed和kickstart配置文件
"""

import http.server
import socketserver
import threading
import time
import socket


def get_host_ip():
    """获取主机IP地址，用于HTTP服务器"""
    try:
        # 创建一个UDP socket来获取默认路由接口的IP
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
    
    def __init__(self, directory, port=8080):
        """
        初始化HTTP服务器
        
        Args:
            directory: 服务目录路径
            port: 端口号（默认8080）
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
                return os.path.join(self.directory, path)
        
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


def start_http_server(directory, port=8080):
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
            return os.path.join(directory, path)
    
    httpd = socketserver.TCPServer(("", port), CustomHandler)
    
    def serve():
        httpd.serve_forever()
    
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    time.sleep(1)  # 等待服务器启动
    return httpd, thread

