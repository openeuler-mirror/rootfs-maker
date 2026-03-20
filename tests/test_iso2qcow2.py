import os
import tempfile
from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path

import pytest

from iso2qcow2 import (
    detect_distribution,
    is_dvd_iso,
    detect_iso_type,
    load_template_config,
    generate_from_template,
    modify_ks_file,
)


class TestDetectDistribution:
    """测试 detect_distribution 函数"""

    def test_detect_debian(self):
        """ISO 文件名包含 debian 时应返回 'debian'"""
        assert detect_distribution("/path/to/debian-12.0.0-amd64.iso") == "debian"

    def test_detect_ubuntu(self):
        """ISO 文件名包含 ubuntu 时应返回 'ubuntu'"""
        assert detect_distribution("/path/to/ubuntu-22.04.1-live-server-amd64.iso") == "ubuntu"

    def test_detect_openeuler(self):
        """ISO 文件名包含 openeuler 时应返回 'openeuler'"""
        assert detect_distribution("/path/to/openEuler-22.03-LTS-x86_64.iso") == "openeuler"

    def test_detect_centos(self):
        """ISO 文件名包含 centos 时应返回 'centos'"""
        assert detect_distribution("/path/to/CentOS-7-x86_64-DVD-2009.iso") == "centos"

    def test_detect_rhel(self):
        """ISO 文件名包含 rhel 时应返回 'rhel'"""
        assert detect_distribution("/path/to/rhel-9.0-x86_64-dvd.iso") == "rhel"

    def test_detect_fedora(self):
        """ISO 文件名包含 fedora 时应返回 'fedora'"""
        assert detect_distribution("/path/to/Fedora-38-1.6-x86_64.iso") == "fedora"

    def test_detect_unknown(self):
        """无法识别的文件名应返回 None"""
        assert detect_distribution("/path/to/unknown.iso") is None

    def test_detect_case_insensitive(self):
        """文件名检测应不区分大小写"""
        assert detect_distribution("/path/to/DEBIAN-12.iso") == "debian"
        assert detect_distribution("/path/to/Ubuntu-22.iso") == "ubuntu"
        assert detect_distribution("/path/to/FEDORA-38.iso") == "fedora"

    def test_detect_redhat_variant(self):
        """redhat 和 red-hat 也应识别为 rhel"""
        assert detect_distribution("/path/to/RedHat-8.iso") == "rhel"
        assert detect_distribution("/path/to/red-hat-8.iso") == "rhel"

    def test_detect_open_euler_with_hyphen(self):
        """open-euler（带连字符）也应识别为 openeuler"""
        assert detect_distribution("/path/to/open-euler-22.03.iso") == "openeuler"


class TestIsDvdIso:
    """测试 is_dvd_iso 函数"""

    @patch("iso2qcow2.subprocess.run")
    def test_debian_dvd(self, mock_run, tmp_path):
        """Debian DVD ISO（有 dists 但无 install.netboot）应返回 True"""
        iso_path = tmp_path / "debian-dvd.iso"
        iso_path.write_text("fake")

        # 模拟挂载成功
        mock_mount = MagicMock()
        mock_mount.returncode = 0
        mock_run.return_value = mock_mount

        with patch("iso2qcow2.tempfile.mkdtemp", return_value=str(tmp_path / "mnt")):
            mount_dir = tmp_path / "mnt"
            mount_dir.mkdir()

            # 创建模拟的 DVD 结构：有 dists，无 install.netboot
            (mount_dir / "dists").mkdir()
            (mount_dir / "pool").mkdir()

            dvd = is_dvd_iso(str(iso_path))
            assert dvd is True

    @patch("iso2qcow2.subprocess.run")
    def test_debian_netinst(self, mock_run, tmp_path):
        """Debian netinst ISO（有 install.netboot）应返回 False"""
        iso_path = tmp_path / "debian-netinst.iso"
        iso_path.write_text("fake")

        mock_run.return_value = MagicMock(returncode=0)

        with patch("iso2qcow2.tempfile.mkdtemp", return_value=str(tmp_path / "mnt")):
            mount_dir = tmp_path / "mnt"
            mount_dir.mkdir()
            (mount_dir / "dists").mkdir()
            (mount_dir / "install.netboot").mkdir()

            dvd = is_dvd_iso(str(iso_path))
            assert dvd is False

    @patch("iso2qcow2.subprocess.run")
    def test_rpm_dvd(self, mock_run, tmp_path):
        """RPM DVD ISO（有 Packages 目录）应返回 True"""
        iso_path = tmp_path / "centos-dvd.iso"
        iso_path.write_text("fake")

        mock_run.return_value = MagicMock(returncode=0)

        with patch("iso2qcow2.tempfile.mkdtemp", return_value=str(tmp_path / "mnt")):
            mount_dir = tmp_path / "mnt"
            mount_dir.mkdir()
            (mount_dir / "Packages").mkdir()

            dvd = is_dvd_iso(str(iso_path))
            assert dvd is True

    @patch("iso2qcow2.subprocess.run")
    def test_dvd_by_filename(self, mock_run, tmp_path):
        """文件名包含 DVD 字样但挂载失败时应返回 False（异常路径优先级高）"""
        iso_path = tmp_path / "my-dvd-image.iso"
        iso_path.write_text("fake")

        # 挂载失败
        mock_run.side_effect = Exception("mount failed")

        dvd = is_dvd_iso(str(iso_path))
        assert dvd is False

    @patch("iso2qcow2.subprocess.run")
    def test_netinst_with_fallback(self, mock_run, tmp_path):
        """挂载失败且文件名无 DVD 字样时应返回 False"""
        iso_path = tmp_path / "debian-netinst.iso"
        iso_path.write_text("fake")

        mock_run.side_effect = Exception("mount failed")

        dvd = is_dvd_iso(str(iso_path))
        assert dvd is False


class TestDetectIsoType:
    """测试 detect_iso_type 函数"""

    @patch("iso2qcow2.subprocess.run")
    def test_detect_deb(self, mock_run, tmp_path):
        """Debian ISO 特征存在时应返回 'deb'"""
        iso_path = tmp_path / "test.iso"
        iso_path.write_text("fake")

        mock_run.return_value = MagicMock(returncode=0)

        with patch("iso2qcow2.tempfile.mkdtemp", return_value=str(tmp_path / "mnt")):
            mount_dir = tmp_path / "mnt"
            mount_dir.mkdir()
            (mount_dir / "dists").mkdir()

            result = detect_iso_type(str(iso_path))
            assert result == "deb"

    @patch("iso2qcow2.subprocess.run")
    def test_detect_rpm(self, mock_run, tmp_path):
        """RPM ISO 特征存在时应返回 'rpm'"""
        iso_path = tmp_path / "test.iso"
        iso_path.write_text("fake")

        mock_run.return_value = MagicMock(returncode=0)

        with patch("iso2qcow2.tempfile.mkdtemp", return_value=str(tmp_path / "mnt")):
            mount_dir = tmp_path / "mnt"
            mount_dir.mkdir()
            (mount_dir / "Packages").mkdir()

            result = detect_iso_type(str(iso_path))
            assert result == "rpm"

    @patch("iso2qcow2.subprocess.run")
    def test_detect_unknown(self, mock_run, tmp_path):
        """无任何特征时应返回 None"""
        iso_path = tmp_path / "test.iso"
        iso_path.write_text("fake")

        mock_run.return_value = MagicMock(returncode=0)

        with patch("iso2qcow2.tempfile.mkdtemp", return_value=str(tmp_path / "mnt")):
            mount_dir = tmp_path / "mnt"
            mount_dir.mkdir()
            # 不创建任何特征目录

            result = detect_iso_type(str(iso_path))
            assert result is None


class TestLoadTemplateConfig:
    """测试 load_template_config 函数"""

    def test_load_debian_preseed(self, tmp_path):
        """加载 debian 的 preseed 模板应返回正确内容"""
        templates_dir = tmp_path / "templates"
        debian_dir = templates_dir / "debian"
        debian_dir.mkdir(parents=True)
        preseed_file = debian_dir / "preseed.cfg"
        preseed_file.write_text("d-i debian-installer/locale string en_US\n")

        with patch("iso2qcow2.get_template_dir", return_value=templates_dir):
            content = load_template_config("debian", "deb")
            assert content is not None
            assert "d-i debian-installer/locale" in content

    def test_load_centos_kickstart(self, tmp_path):
        """加载 centos 的 kickstart 模板应返回正确内容"""
        templates_dir = tmp_path / "templates"
        centos_dir = templates_dir / "centos"
        centos_dir.mkdir(parents=True)
        ks_file = centos_dir / "ks.ks"
        ks_file.write_text("rootpw --iscrypted $6$...\n")

        with patch("iso2qcow2.get_template_dir", return_value=templates_dir):
            content = load_template_config("centos", "rpm")
            assert content is not None
            assert "rootpw" in content

    def test_load_nonexistent(self, tmp_path):
        """不存在的模板应返回 None"""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        with patch("iso2qcow2.get_template_dir", return_value=templates_dir):
            content = load_template_config("nonexistent", "deb")
            assert content is None

    def test_default_distribution_deb(self, tmp_path):
        """iso_type='deb' 且 distribution=None 时应使用 'debian' 作为默认值"""
        templates_dir = tmp_path / "templates"
        debian_dir = templates_dir / "debian"
        debian_dir.mkdir(parents=True)
        (debian_dir / "preseed.cfg").write_text("default debian\n")

        with patch("iso2qcow2.get_template_dir", return_value=templates_dir) as mock_get:
            content = load_template_config(None, "deb")
            assert content is not None

    def test_default_distribution_rpm(self, tmp_path):
        """iso_type='rpm' 且 distribution=None 时应使用 'centos' 作为默认值"""
        templates_dir = tmp_path / "templates"
        centos_dir = templates_dir / "centos"
        centos_dir.mkdir(parents=True)
        (centos_dir / "ks.ks").write_text("default centos\n")

        with patch("iso2qcow2.get_template_dir", return_value=templates_dir):
            content = load_template_config(None, "rpm")
            assert content is not None
            assert "centos" in content


class TestGenerateFromTemplate:
    """测试 generate_from_template 函数"""

    def test_generate_success(self, tmp_path):
        """从模板生成配置文件应成功"""
        templates_dir = tmp_path / "templates"
        debian_dir = templates_dir / "debian"
        debian_dir.mkdir(parents=True)
        (debian_dir / "preseed.cfg").write_text(
            "d-i mirror/country string China\n"
            "d-i mirror/http/proxy string\n"
        )

        output = tmp_path / "output.cfg"

        with patch("iso2qcow2.get_template_dir", return_value=templates_dir):
            generate_from_template(str(output), "debian", "deb")

        assert output.exists()
        assert "China" in output.read_text()

    def test_generate_template_not_found(self, tmp_path):
        """模板不存在时应抛出 FileNotFoundError"""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        with patch("iso2qcow2.get_template_dir", return_value=templates_dir):
            with pytest.raises(FileNotFoundError, match="模板文件不存在"):
                generate_from_template(str(tmp_path / "out.cfg"), "unknown", "deb")


class TestModifyKsFile:
    """测试 modify_ks_file 函数"""

    def test_modify_simple(self, tmp_path):
        """应正确替换 ${KEY} 格式的变量"""
        ks_file = tmp_path / "ks.ks"
        ks_file.write_text("rootpw ${ROOT_PW}\nurl --url=${REPO_URL}\n")

        modify_ks_file(str(ks_file), {"ROOT_PW": "test123", "REPO_URL": "http://mirror.example.com"})

        content = ks_file.read_text()
        assert "test123" in content
        assert "http://mirror.example.com" in content
        assert "${ROOT_PW}" not in content

    def test_modify_no_vars(self, tmp_path):
        """没有变量的文件应保持不变"""
        ks_file = tmp_path / "ks.ks"
        original = "rootpw --iscrypted $6$abc\n"
        ks_file.write_text(original)

        modify_ks_file(str(ks_file), {"NONEXIST": "value"})

        assert ks_file.read_text() == original

    def test_modify_multiple_occurrences(self, tmp_path):
        """同一变量出现多次时应全部替换"""
        ks_file = tmp_path / "ks.ks"
        ks_file.write_text("url --mirrorlist=${MIRROR}\nrepo --name=updates --mirrorlist=${MIRROR}\n")

        modify_ks_file(str(ks_file), {"MIRROR": "http://mirror.example.com"})

        content = ks_file.read_text()
        assert content.count("http://mirror.example.com") == 2
        assert "${MIRROR}" not in content
