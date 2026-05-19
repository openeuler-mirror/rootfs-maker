from pathlib import Path
from unittest.mock import patch

import pytest

from docker2rootfs import find_kernel_in_rootfs, main


class TestFindKernelInRootfs:
    """测试 find_kernel_in_rootfs 函数"""

    def test_find_vmlinuz_in_boot(self, tmp_path):
        """在 boot/ 目录下找到 vmlinuz 文件"""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir(parents=True)
        vmlinuz = boot_dir / "vmlinuz-6.1.0"
        vmlinuz.write_text("fake kernel")

        kernels = find_kernel_in_rootfs(str(tmp_path))
        assert len(kernels) == 1
        assert vmlinuz in kernels

    def test_find_vmlinux_in_boot(self, tmp_path):
        """在 boot/ 目录下找到 vmlinux 文件"""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir(parents=True)
        vmlinux = boot_dir / "vmlinux-6.1.0"
        vmlinux.write_text("fake kernel")

        kernels = find_kernel_in_rootfs(str(tmp_path))
        assert len(kernels) == 1
        assert vmlinux in kernels

    def test_find_kernel_in_root(self, tmp_path):
        """在 rootfs 根目录下找到 kernel 文件"""
        kernel = tmp_path / "vmlinuz"
        kernel.write_text("fake kernel")

        kernels = find_kernel_in_rootfs(str(tmp_path))
        assert len(kernels) == 1
        assert kernel in kernels

    def test_no_kernel_found(self, tmp_path):
        """没有 kernel 文件时应返回空列表"""
        (tmp_path / "usr").mkdir()
        (tmp_path / "usr" / "bin").mkdir()
        etc_dir = tmp_path / "etc"
        etc_dir.mkdir()
        (etc_dir / "fstab").write_text("...")

        kernels = find_kernel_in_rootfs(str(tmp_path))
        assert len(kernels) == 0

    def test_multiple_kernels(self, tmp_path):
        """多个 kernel 文件时都应返回"""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir(parents=True)
        vmlinuz1 = boot_dir / "vmlinuz-6.1.0"
        vmlinuz1.write_text("kernel1")
        vmlinuz2 = boot_dir / "vmlinuz-5.10.0"
        vmlinuz2.write_text("kernel2")

        kernels = find_kernel_in_rootfs(str(tmp_path))
        assert len(kernels) == 2

    def test_kernel_in_boot_dir_only(self, tmp_path):
        """boot/ 目录下的 kernel 相关文件即使不在 glob 模式中也应被迭代检测"""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir(parents=True)
        # glob 会匹配 vmlinuz*
        vmlinuz = boot_dir / "vmlinuz"
        vmlinuz.write_text("fake")

        # boot 迭代也会额外检查，但不应重复
        kernels = find_kernel_in_rootfs(str(tmp_path))
        assert len(kernels) == 1

    def test_non_kernel_files_in_boot(self, tmp_path):
        """boot/ 目录下的非 kernel 文件不应被返回"""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir(parents=True)
        (boot_dir / "initrd.img-6.1.0").write_text("initrd")
        (boot_dir / "config-6.1.0").write_text("config")
        (boot_dir / "System.map-6.1.0").write_text("map")

        kernels = find_kernel_in_rootfs(str(tmp_path))
        assert len(kernels) == 0


class TestDocker2RootfsMain:
    """测试 docker2rootfs main 入口"""

    @patch("docker2rootfs.logger.error")
    @patch("docker2rootfs.subprocess.run")
    def test_main_logs_missing_docker_without_unsupported_file_kwarg(
        self, mock_run, mock_error, monkeypatch
    ):
        """Docker 缺失时应直接记录错误并退出，而不是触发 logging TypeError"""
        mock_run.side_effect = FileNotFoundError("docker not found")
        monkeypatch.setattr(
            "sys.argv",
            ["docker2rootfs.py", "-i", "busybox:latest", "-o", "out"],
        )

        with pytest.raises(SystemExit) as exc:
            main()

        assert exc.value.code == 1
        mock_error.assert_called_once_with("错误: Docker未安装或不可用")
