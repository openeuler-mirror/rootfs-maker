import socket
import urllib.request
import urllib.error
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from lib.http_server import (
    get_host_ip,
    start_http_server,
    ConfigHTTPServer,
    check_http_server_accessible,
    check_firewall_status,
)


class TestGetHostIp:
    """测试 get_host_ip 函数"""

    @patch("subprocess.run")
    def test_get_host_ip_via_virsh(self, mock_run):
        """优先通过 virsh 获取桥接网络 IP"""
        mock_virsh = MagicMock()
        mock_virsh.returncode = 0
        mock_virsh.stdout = "Bridge:\tvirbr0\n"

        mock_ip = MagicMock()
        mock_ip.returncode = 0
        mock_ip.stdout = "inet 192.168.122.1/24 brd ...\n"

        mock_run.side_effect = [mock_virsh, mock_ip]

        ip = get_host_ip()
        assert ip == "192.168.122.1"

    @patch("subprocess.run")
    @patch("lib.http_server.socket.socket")
    def test_get_host_ip_fallback_to_udp(self, mock_socket, mock_run):
        """virsh 不可用时回退到 UDP socket 方式"""
        mock_run.side_effect = FileNotFoundError("virsh not found")

        mock_sock = MagicMock()
        mock_sock.getsockname.return_value = ("10.0.0.5", 0)
        mock_socket.return_value = mock_sock

        ip = get_host_ip()
        assert ip == "10.0.0.5"
        mock_sock.connect.assert_called_once_with(("8.8.8.8", 80))

    @patch("subprocess.run")
    @patch("lib.http_server.socket.socket")
    def test_get_host_ip_all_fail(self, mock_socket, mock_run):
        """所有方法都失败时返回默认 IP"""
        mock_run.side_effect = Exception("all fail")

        mock_sock = MagicMock()
        mock_sock.connect.side_effect = Exception("no network")
        mock_socket.return_value = mock_sock

        ip = get_host_ip()
        assert ip == "192.168.122.1"


class TestConfigHTTPServer:
    """测试 ConfigHTTPServer 类"""

    def test_init(self, tmp_path):
        """初始化应设置正确的属性和默认端口"""
        server = ConfigHTTPServer(tmp_path)
        assert server.directory == str(tmp_path)
        assert server.port == 0
        assert server.httpd is None
        assert server.thread is None

    def test_init_with_port(self, tmp_path):
        """初始化应接受自定义端口"""
        server = ConfigHTTPServer(tmp_path, port=8080)
        assert server.port == 8080

    @patch("lib.http_server.socketserver.TCPServer")
    @patch("lib.http_server.get_host_ip")
    def test_start_and_get_url(self, mock_get_host_ip, mock_tcpserver, tmp_path):
        """启动后 get_url 应返回正确的 URL"""
        mock_get_host_ip.return_value = "192.168.1.1"
        mock_httpd = MagicMock()
        mock_httpd.server_address = ("", 4321)
        mock_tcpserver.return_value = mock_httpd

        server = ConfigHTTPServer(tmp_path, port=0)
        server.start()

        assert server.httpd is not None
        assert server.thread is not None
        assert server.port == 4321

        url = server.get_url("preseed.cfg")
        assert url == "http://192.168.1.1:4321/preseed.cfg"

    @patch("lib.http_server.socketserver.TCPServer")
    @patch("lib.http_server.get_host_ip")
    def test_start_and_get_url_with_special_chars(self, mock_get_host_ip, mock_tcpserver, tmp_path):
        """文件名包含空格时应正确进行 URL 编码"""
        mock_get_host_ip.return_value = "192.168.1.1"
        mock_httpd = MagicMock()
        mock_httpd.server_address = ("", 0)
        mock_tcpserver.return_value = mock_httpd

        server = ConfigHTTPServer(tmp_path, port=9999)
        server.start()

        url = server.get_url("dir name/preseed file.cfg")
        assert url == "http://192.168.1.1:9999/dir%20name/preseed%20file.cfg"

    @patch("lib.http_server.socketserver.TCPServer")
    def test_stop(self, mock_tcpserver, tmp_path):
        """stop 方法应调用 shutdown 和 server_close"""
        mock_httpd = MagicMock()
        mock_tcpserver.return_value = mock_httpd

        server = ConfigHTTPServer(tmp_path)
        server.httpd = mock_httpd
        server.stop()

        mock_httpd.shutdown.assert_called_once()
        mock_httpd.server_close.assert_called_once()

    @patch("lib.http_server.socketserver.TCPServer")
    def test_stop_no_httpd(self, tmp_path):
        """httpd 为 None 时 stop 不应报错"""
        server = ConfigHTTPServer(tmp_path)
        server.stop()  # 不应抛出异常


class TestStartHttpServer:
    """测试 start_http_server 函数"""

    @patch("lib.http_server.socketserver.TCPServer")
    def test_start_http_server_success(self, mock_tcpserver, tmp_path):
        """正常启动应返回 (httpd, thread, port) 元组"""
        mock_httpd = MagicMock()
        mock_httpd.server_address = ("", 9999)
        mock_tcpserver.return_value = mock_httpd

        httpd, thread, port = start_http_server(str(tmp_path), port=0)

        assert httpd is mock_httpd
        assert thread is not None
        assert port == 9999


class TestCheckHttpServerAccessible:
    """测试 check_http_server_accessible 函数"""

    @patch("urllib.request.urlopen")
    def test_accessible(self, mock_urlopen):
        """服务器返回 200 时应返回 True"""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_urlopen.return_value = mock_response

        result = check_http_server_accessible("192.168.1.1", 8080, "preseed.cfg")
        assert result is True

    @patch("urllib.request.urlopen")
    def test_accessible_encodes_filename(self, mock_urlopen):
        """带空格的文件名应使用编码后的 URL 访问"""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_urlopen.return_value = mock_response

        result = check_http_server_accessible("192.168.1.1", 8080, "dir name/preseed file.cfg")
        assert result is True
        mock_urlopen.assert_called_once()
        assert "%20" in mock_urlopen.call_args.args[0]

    @patch("urllib.request.urlopen")
    def test_not_accessible(self, mock_urlopen):
        """服务器返回非 200 时应返回 False"""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 404
        mock_urlopen.return_value = mock_response

        result = check_http_server_accessible("192.168.1.1", 8080, "preseed.cfg")
        assert result is False

    @patch("urllib.request.urlopen")
    def test_urlopen_exception(self, mock_urlopen):
        """发生网络异常时应返回 False"""
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")

        result = check_http_server_accessible("192.168.1.1", 8080, "preseed.cfg")
        assert result is False

    @patch("urllib.request.urlopen")
    def test_path_traversal_is_neutralized(self, mock_urlopen):
        """路径穿越请求应被限制在服务目录内"""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_urlopen.return_value = mock_response

        result = check_http_server_accessible("192.168.1.1", 8080, "../secret.cfg")
        assert result is True
        assert ".." not in mock_urlopen.call_args.args[0]


class TestCheckFirewallStatus:
    """测试 check_firewall_status 函数"""

    @patch("subprocess.run")
    def test_firewalld_active_port_open(self, mock_run):
        """firewalld 运行且端口已开放时应返回 True"""
        mock_active = MagicMock()
        mock_active.returncode = 0
        mock_active.stdout = "active\n"

        mock_ports = MagicMock()
        mock_ports.returncode = 0
        mock_ports.stdout = "8080/tcp\n"

        mock_run.side_effect = [mock_active, mock_ports]

        result = check_firewall_status(8080)
        assert result is True

    @patch("subprocess.run")
    def test_firewalld_active_port_closed(self, mock_run):
        """firewalld 运行但端口未开放时应返回 False"""
        mock_active = MagicMock()
        mock_active.returncode = 0
        mock_active.stdout = "active\n"

        mock_ports = MagicMock()
        mock_ports.returncode = 0
        mock_ports.stdout = "80/tcp 443/tcp\n"

        mock_run.side_effect = [mock_active, mock_ports]

        result = check_firewall_status(8080)
        assert result is False

    @patch("subprocess.run")
    def test_no_firewall(self, mock_run):
        """没有活跃防火墙时应返回 True"""
        mock_run.side_effect = FileNotFoundError("systemctl not found")

        result = check_firewall_status(8080)
        assert result is True

    @patch("subprocess.run")
    def test_ufw_active_port_open(self, mock_run):
        """ufw 运行且端口已开放时应返回 True"""
        # 第1次调用 systemctl is-active firewalld: firewalld 未运行
        mock_firewalld_inactive = MagicMock()
        mock_firewalld_inactive.returncode = 0
        # stdout 是 "inactive\n"，但 "active" in "inactive" 为 True，
        # 所以需要让 systemctl 返回非 0 来模拟 firewalld 不可用
        mock_firewalld_inactive.returncode = 3
        mock_firewalld_inactive.stdout = "inactive\n"

        # 第2次: systemctl is-active ufw → active
        mock_ufw_active = MagicMock()
        mock_ufw_active.returncode = 0
        mock_ufw_active.stdout = "active\n"

        # 第3次: ufw status 包含端口
        mock_ufw_status = MagicMock()
        mock_ufw_status.returncode = 0
        mock_ufw_status.stdout = "8080/tcp ALLOW Anywhere\n"

        mock_run.side_effect = [mock_firewalld_inactive, mock_ufw_active, mock_ufw_status]

        result = check_firewall_status(8080)
        assert result is True
