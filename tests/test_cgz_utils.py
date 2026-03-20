import os
import subprocess
from unittest.mock import patch, MagicMock, call
from pathlib import Path

import pytest

from lib.cgz_utils import compress_cgz, extract_cgz


class TestCompressCgz:
    """测试 compress_cgz 函数"""

    def test_source_not_exists(self):
        """源目录不存在时应抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError, match="源目录不存在"):
            compress_cgz("/nonexistent/path", "/tmp/output.cgz")

    def test_source_not_a_directory(self, tmp_path):
        """源路径不是目录时应抛出 ValueError"""
        source_file = tmp_path / "afile.txt"
        source_file.write_text("hello")
        with pytest.raises(ValueError, match="路径不是目录"):
            compress_cgz(str(source_file), str(tmp_path / "output.cgz"))

    def test_output_dir_created(self, tmp_path):
        """输出文件的父目录不存在时应自动创建"""
        source_dir = tmp_path / "sourcedir"
        source_dir.mkdir()
        (source_dir / "test.txt").write_text("hello")

        output_dir = tmp_path / "nested" / "deep"
        output_file = output_dir / "out.cgz"

        with patch("lib.cgz_utils.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stderr.read.return_value = b""
            mock_popen.return_value = mock_process

            compress_cgz(str(source_dir), str(output_file))

        # 验证输出目录已创建
        assert output_dir.exists()
        args_seq = [c[0][0] for c in mock_popen.call_args_list]
        assert any("cpio" in str(a) for a in args_seq)
        assert any("gzip" in str(a) for a in args_seq)

    def test_cpio_failure(self, tmp_path):
        """cpio 命令失败时应抛出 CalledProcessError"""
        source_dir = tmp_path / "sourcedir"
        source_dir.mkdir()
        (source_dir / "test.txt").write_text("hello")

        with patch("lib.cgz_utils.subprocess.Popen") as mock_popen:
            mock_cpio = MagicMock()
            mock_cpio.returncode = 1
            mock_cpio.stderr.read.return_value = b"cpio error"

            mock_find = MagicMock()
            mock_find.returncode = 0
            mock_find.stdout.close = MagicMock()

            # 第一个 Popen 是 find，第二个是 cpio，第三个是 gzip
            mock_popen.side_effect = [mock_find, mock_cpio]

            with pytest.raises(subprocess.CalledProcessError, match="cpio"):
                compress_cgz(str(source_dir), str(tmp_path / "out.cgz"))

    def test_gzip_failure(self, tmp_path):
        """gzip 命令失败时应抛出 CalledProcessError"""
        source_dir = tmp_path / "sourcedir"
        source_dir.mkdir()
        (source_dir / "test.txt").write_text("hello")

        with patch("lib.cgz_utils.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stderr.read.return_value = b""

            mock_gzip = MagicMock()
            mock_gzip.returncode = 1
            mock_gzip.stderr.read.return_value = b"gzip error"

            mock_popen.side_effect = [mock_process, mock_process, mock_gzip]

            with pytest.raises(subprocess.CalledProcessError, match="gzip"):
                compress_cgz(str(source_dir), str(tmp_path / "out.cgz"))

    def test_missing_cpio_tool(self, tmp_path):
        """缺少 cpio/gzip 工具时应抛出 RuntimeError"""
        source_dir = tmp_path / "sourcedir"
        source_dir.mkdir()

        with patch("lib.cgz_utils.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = FileNotFoundError("cpio: not found")

            with pytest.raises(RuntimeError, match="缺少必要的工具"):
                compress_cgz(str(source_dir), str(tmp_path / "out.cgz"))

    def test_compress_success(self, tmp_path):
        """正常压缩流程应成功"""
        source_dir = tmp_path / "sourcedir"
        source_dir.mkdir()
        (source_dir / "hello.txt").write_text("world")

        with patch("lib.cgz_utils.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stderr.read.return_value = b""
            mock_process.stdout.close = MagicMock()
            mock_popen.return_value = mock_process

            compress_cgz(str(source_dir), str(tmp_path / "out.cgz"))

        # find, cpio, gzip 都应被调用
        assert mock_popen.call_count >= 3


class TestExtractCgz:
    """测试 extract_cgz 函数"""

    def test_file_not_exists(self):
        """cgz 文件不存在时应抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError, match="cgz文件不存在"):
            extract_cgz("/nonexistent/file.cgz", "/tmp/output")

    def test_gunzip_failure(self, tmp_path):
        """gunzip 失败时应抛出 CalledProcessError"""
        cgz_file = tmp_path / "test.cgz"
        cgz_file.write_text("fake content")

        with patch("lib.cgz_utils.subprocess.Popen") as mock_popen:
            mock_gunzip = MagicMock()
            mock_gunzip.returncode = 1
            mock_gunzip.stderr.read.return_value = b"gunzip error"
            mock_gunzip.stdout.close = MagicMock()

            mock_popen.return_value = mock_gunzip

            with pytest.raises(subprocess.CalledProcessError, match="gunzip"):
                extract_cgz(str(cgz_file), str(tmp_path / "output"))

    def test_cpio_failure_with_empty_output(self, tmp_path):
        """cpio 失败且输出目录为空时应抛出 CalledProcessError"""
        cgz_file = tmp_path / "test.cgz"
        cgz_file.write_text("fake content")

        with patch("lib.cgz_utils.subprocess.Popen") as mock_popen:
            mock_gunzip = MagicMock()
            mock_gunzip.returncode = 0
            mock_gunzip.stderr.read.return_value = b""
            mock_gunzip.stdout.close = MagicMock()

            mock_cpio = MagicMock()
            mock_cpio.returncode = 1
            mock_cpio.stderr.read.return_value = b"cpio: some error"
            mock_cpio.stdout.close = MagicMock()

            mock_popen.side_effect = [mock_gunzip, mock_cpio]

            output_dir = tmp_path / "output"
            output_dir.mkdir()
            with pytest.raises(subprocess.CalledProcessError, match="cpio"):
                extract_cgz(str(cgz_file), str(output_dir))

    def test_cpio_failure_with_content(self, tmp_path):
        """cpio 返回非零但输出目录有内容时不应抛出异常"""
        cgz_file = tmp_path / "test.cgz"
        cgz_file.write_text("fake content")

        with patch("lib.cgz_utils.subprocess.Popen") as mock_popen:
            mock_gunzip = MagicMock()
            mock_gunzip.returncode = 0
            mock_gunzip.stderr.read.return_value = b""
            mock_gunzip.stdout.close = MagicMock()

            mock_cpio = MagicMock()
            mock_cpio.returncode = 1
            mock_cpio.stderr.read.return_value = b"cpio: warning: some non-fatal"
            mock_cpio.stdout.close = MagicMock()

            mock_popen.side_effect = [mock_gunzip, mock_cpio]

            output_dir = tmp_path / "output"
            output_dir.mkdir()
            # 预先创建一些内容，模拟 cpio 实际提取了文件
            (output_dir / "somefile.txt").write_text("content")

            # 不应抛出异常
            extract_cgz(str(cgz_file), str(output_dir))

    def test_missing_gunzip_tool(self, tmp_path):
        """缺少 gunzip/cpio 工具时应抛出 RuntimeError"""
        cgz_file = tmp_path / "test.cgz"
        cgz_file.write_text("fake")

        with patch("lib.cgz_utils.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = FileNotFoundError("gunzip: not found")

            with pytest.raises(RuntimeError, match="缺少必要的工具"):
                extract_cgz(str(cgz_file), str(tmp_path / "output"))

    def test_extract_success(self, tmp_path):
        """正常解压流程应成功"""
        cgz_file = tmp_path / "test.cgz"
        cgz_file.write_text("fake content")
        output_dir = tmp_path / "output"

        with patch("lib.cgz_utils.subprocess.Popen") as mock_popen:
            mock_gunzip = MagicMock()
            mock_gunzip.returncode = 0
            mock_gunzip.stderr.read.return_value = b""
            mock_gunzip.stdout.close = MagicMock()

            mock_cpio = MagicMock()
            mock_cpio.returncode = 0
            mock_cpio.stderr.read.return_value = b""
            mock_cpio.stdout.close = MagicMock()

            mock_popen.side_effect = [mock_gunzip, mock_cpio]

            extract_cgz(str(cgz_file), str(output_dir))

        assert output_dir.exists()
