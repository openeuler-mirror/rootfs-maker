import subprocess
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from qcow2rootfs import check_guestfish, find_kernel


class TestCheckGuestfish:
    """测试 check_guestfish 函数"""

    @patch("qcow2rootfs.subprocess.run")
    def test_guestfish_available(self, mock_run):
        """guestfish --version 返回 0 时应返回 True"""
        mock_run.return_value = MagicMock(returncode=0)

        assert check_guestfish() is True

    @patch("qcow2rootfs.subprocess.run")
    def test_guestfish_unavailable_command_not_found(self, mock_run):
        """FileNotFoundError 时应返回 False"""
        mock_run.side_effect = FileNotFoundError("guestfish not found")

        assert check_guestfish() is False

    @patch("qcow2rootfs.subprocess.run")
    def test_guestfish_unavailable_nonzero(self, mock_run):
        """返回码非零时应返回 False"""
        mock_run.return_value = MagicMock(returncode=1)

        assert check_guestfish() is False

    @patch("qcow2rootfs.subprocess.run")
    def test_guestfish_timeout(self, mock_run):
        """超时时应返回 False"""
        mock_run.side_effect = subprocess.TimeoutExpired("guestfish", timeout=5)

        assert check_guestfish() is False


class TestFindKernel:
    """测试 find_kernel 函数"""

    def test_find_vmlinuz_in_boot(self, tmp_path):
        """在 boot/ 目录下找到 vmlinuz 文件"""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir(parents=True)
        vmlinuz = boot_dir / "vmlinuz-6.1.0"
        vmlinuz.write_text("fake kernel")

        kernels = find_kernel(str(tmp_path))
        assert len(kernels) == 1
        assert vmlinuz in kernels

    def test_find_vmlinux_in_boot(self, tmp_path):
        """在 boot/ 目录下找到 vmlinux 文件"""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir(parents=True)
        vmlinux = boot_dir / "vmlinux-6.1.0"
        vmlinux.write_text("fake kernel")

        kernels = find_kernel(str(tmp_path))
        assert len(kernels) == 1
        assert vmlinux in kernels

    def test_find_kernel_in_boot(self, tmp_path):
        """在 boot/ 目录下找到 kernel 文件"""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir(parents=True)
        kernel = boot_dir / "kernel-6.1.0"
        kernel.write_text("fake kernel")

        kernels = find_kernel(str(tmp_path))
        assert len(kernels) == 1
        assert kernel in kernels

    def test_find_vmlinuz_in_root(self, tmp_path):
        """在 rootfs 根目录下找到 vmlinuz 文件"""
        vmlinuz = tmp_path / "vmlinuz"
        vmlinuz.write_text("fake kernel")

        kernels = find_kernel(str(tmp_path))
        assert len(kernels) == 1
        assert vmlinuz in kernels

    def test_find_kernel_in_boot_case_insensitive(self, tmp_path):
        """boot/ 目录中的文件应不分大小写匹配"""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir(parents=True)
        vmlinuz = boot_dir / "VMLINUZ"
        vmlinuz.write_text("fake")

        kernels = find_kernel(str(tmp_path))
        assert len(kernels) == 1

    def test_no_kernel_found(self, tmp_path):
        """没有 kernel 文件时应返回空列表"""
        (tmp_path / "README.txt").write_text("not a kernel")
        (tmp_path / "etc").mkdir()
        (tmp_path / "etc" / "fstab").write_text("...")

        kernels = find_kernel(str(tmp_path))
        assert len(kernels) == 0

    def test_boot_dir_kernel_not_in_glob(self, tmp_path):
        """boot/ 目录下的非 kernel 文件不应被检测到（文件名不包含 vmlinuz/vmlinux/kernel）"""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir(parents=True)
        # 不包含 vmlinuz/vmlinux/kernel 子串的文件名
        initrd = boot_dir / "initrd.img-6.1.0"
        initrd.write_text("initrd")
        config = boot_dir / "config-6.1.0"
        config.write_text("config")

        kernels = find_kernel(str(tmp_path))
        assert len(kernels) == 0

    def test_multiple_kernels(self, tmp_path):
        """多个 kernel 文件时都应返回"""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir(parents=True)
        vmlinuz1 = boot_dir / "vmlinuz-6.1.0"
        vmlinuz1.write_text("kernel1")
        vmlinuz2 = boot_dir / "vmlinuz-5.10.0"
        vmlinuz2.write_text("kernel2")

        kernels = find_kernel(str(tmp_path))
        assert len(kernels) == 2
