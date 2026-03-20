import os
import random
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from repo_config.common.update_repo import (
    copy_repo_file_to_tmp,
    modify_tmp_repo_file_with_extra_param,
    copy_repo_config_to_rootfs,
    clean_tmp_repo_file,
    common_update_repo_config,
)


class TestCopyRepoFileToTmp:
    """测试 copy_repo_file_to_tmp 函数"""

    def test_copy_success(self, tmp_path):
        """正常复制文件到临时目录"""
        repo_name = "debian"
        repo_file = "sources.list"

        # 创建模拟的源文件
        src_dir = tmp_path / "src" / repo_name
        src_dir.mkdir(parents=True)
        src_file = src_dir / repo_file
        src_file.write_text("deb http://deb.debian.org/debian bookworm main\n")

        # 修补 Path(__file__).parent.parent 使其指向我们的模拟目录
        with patch("repo_config.common.update_repo.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.parent.parent = tmp_path / "src"
            mock_path.return_value = mock_path_instance

            # 修补 random.randint 让其返回固定值
            with patch("repo_config.common.update_repo.random.randint", return_value=1234):
                tmp_repo_path = copy_repo_file_to_tmp(repo_name, repo_file)

        # 验证临时文件被创建
        assert os.path.exists(tmp_repo_path)
        assert repo_file in tmp_repo_path
        assert "1234" in tmp_repo_path

        # 验证内容相同
        with open(tmp_repo_path, 'r') as f:
            content = f.read()
        assert content == "deb http://deb.debian.org/debian bookworm main\n"


class TestModifyTmpRepoFileWithExtraParam:
    """测试 modify_tmp_repo_file_with_extra_param 函数"""

    def test_modify_with_extra_param(self, tmp_path):
        """应正确替换文件中的内容"""
        repo_file = tmp_path / "sources.list"
        repo_file.write_text(
            "deb ${MIRROR} bookworm main\n"
            "deb-src ${MIRROR} bookworm main\n"
        )

        extra_param = {"${MIRROR}": "http://mirrors.ustc.edu.cn/debian"}
        modify_tmp_repo_file_with_extra_param(str(repo_file), extra_param)

        content = repo_file.read_text()
        assert "http://mirrors.ustc.edu.cn/debian" in content
        assert "${MIRROR}" not in content

    def test_modify_no_extra(self, tmp_path):
        """没有 extra_param 时文件应保持不变"""
        repo_file = tmp_path / "sources.list"
        original = "deb http://deb.debian.org/debian bookworm main\n"
        repo_file.write_text(original)

        modify_tmp_repo_file_with_extra_param(str(repo_file), {})

        assert repo_file.read_text() == original

    def test_modify_none_param(self, tmp_path):
        """None 参数应不做替换"""
        repo_file = tmp_path / "sources.list"
        original = "deb http://deb.debian.org/debian bookworm main\n"
        repo_file.write_text(original)

        modify_tmp_repo_file_with_extra_param(str(repo_file), None)

        assert repo_file.read_text() == original

    def test_modify_multiple_params(self, tmp_path):
        """应支持多个键值对替换"""
        repo_file = tmp_path / "openeuler.repo"
        repo_file.write_text(
            "[repo]\n"
            "name=${NAME}\n"
            "baseurl=${BASEURL}\n"
        )

        extra_param = {
            "${NAME}": "openEuler 22.03",
            "${BASEURL}": "http://repo.openeuler.org",
        }
        modify_tmp_repo_file_with_extra_param(str(repo_file), extra_param)

        content = repo_file.read_text()
        assert "openEuler 22.03" in content
        assert "http://repo.openeuler.org" in content
        assert "${NAME}" not in content

    def test_modify_no_matching_key(self, tmp_path):
        """没有匹配的 key 时文件应保持不变"""
        repo_file = tmp_path / "sources.list"
        original = "deb http://deb.debian.org/debian bookworm main\n"
        repo_file.write_text(original)

        extra_param = {"${NONEXISTENT}": "value"}
        modify_tmp_repo_file_with_extra_param(str(repo_file), extra_param)

        assert repo_file.read_text() == original


class TestCopyRepoConfigToRootfs:
    """测试 copy_repo_config_to_rootfs 函数"""

    def test_copy_to_rootfs(self, tmp_path):
        """应正确复制 repo 文件到 rootfs 目标路径"""
        tmp_repo_file = tmp_path / "sources.list.1234"
        tmp_repo_file.write_text("deb http://mirror.example.com/debian main\n")

        rootfs_dir = tmp_path / "rootfs"
        repo_path = "etc/apt"
        repo_file = "sources.list"

        copy_repo_config_to_rootfs(str(tmp_repo_file), repo_file, repo_path, str(rootfs_dir))

        target_file = rootfs_dir / "etc" / "apt" / "sources.list"
        assert target_file.exists()
        assert target_file.read_text() == "deb http://mirror.example.com/debian main\n"

    def test_copy_nested_dirs(self, tmp_path):
        """目标目录不存在时应自动创建"""
        tmp_repo_file = tmp_path / "test.repo.5678"
        tmp_repo_file.write_text("test content")

        rootfs_dir = tmp_path / "deep" / "nested" / "rootfs"
        repo_path = "etc/yum.repos.d"
        repo_file = "test.repo"

        copy_repo_config_to_rootfs(str(tmp_repo_file), repo_file, repo_path, str(rootfs_dir))

        target = rootfs_dir / "etc" / "yum.repos.d" / "test.repo"
        assert target.exists()


class TestCleanTmpRepoFile:
    """测试 clean_tmp_repo_file 函数"""

    def test_clean_existing(self, tmp_path):
        """存在的临时文件应被删除"""
        tmp_file = tmp_path / "sources.list.1234"
        tmp_file.write_text("content")
        assert tmp_file.exists()

        clean_tmp_repo_file(str(tmp_file))
        assert not tmp_file.exists()

    def test_clean_not_existing(self):
        """不存在的文件不应报错"""
        clean_tmp_repo_file("/nonexistent/path")  # 不应抛出异常


class TestCommonUpdateRepoConfig:
    """测试 common_update_repo_config 函数"""

    def test_full_flow(self, tmp_path):
        """完整的更新流程应正确执行"""
        rootfs_dir = tmp_path / "rootfs"
        template_file = tmp_path / "sources.list"
        template_file.write_text("deb ${MIRROR} bookworm main\n")

        with patch("repo_config.common.update_repo.copy_repo_file_to_tmp",
                   return_value=str(template_file)):
            common_update_repo_config(
                repo_file="sources.list",
                repo_path="etc/apt",
                repo_name="debian",
                repo_extra_dic={"${MIRROR}": "http://mirror.example.com/debian"},
                rootfs_dir=str(rootfs_dir),
            )

        # 验证最终文件存在
        target = rootfs_dir / "etc" / "apt" / "sources.list"
        assert target.exists()
        content = target.read_text()
        assert "http://mirror.example.com/debian" in content
        assert "${MIRROR}" not in content

    def test_full_flow_no_extra(self, tmp_path):
        """无 extra 参数时也应正常工作"""
        rootfs_dir = tmp_path / "rootfs"

        common_update_repo_config(
            repo_file="sources.list",
            repo_path="etc/apt",
            repo_name="debian",
            repo_extra_dic={},
            rootfs_dir=str(rootfs_dir),
        )

        target = rootfs_dir / "etc" / "apt" / "sources.list"
        assert target.exists()


class TestDebianUpdateRepo:
    """测试 Debian/Ubuntu/Mirror 的 update_repo 包装函数"""

    def test_debian_update_repo_config(self, tmp_path):
        """debian.update_repo_config 应调用 common 函数并传入正确参数"""
        from repo_config.debian.update_repo import update_repo_config

        rootfs_dir = tmp_path / "rootfs"
        repo = "debian"
        repo_extra_dic = {"${MIRROR}": "http://mirror.example.com/debian"}

        with patch("repo_config.debian.update_repo.common_update_repo_config") as mock_common:
            update_repo_config(repo, repo_extra_dic, str(rootfs_dir))

            mock_common.assert_called_once_with(
                "sources.list",
                os.path.join("etc", "apt"),
                "debian",
                repo_extra_dic,
                str(rootfs_dir),
            )

    def test_openeuler_update_repo_config(self, tmp_path):
        """openeuler.update_repo_config 应调用 common 函数并传入正确参数"""
        from repo_config.openeuler.update_repo import update_repo_config

        with patch("repo_config.openeuler.update_repo.common_update_repo_config") as mock_common:
            update_repo_config("openeuler", {}, str(tmp_path / "rootfs"))

            mock_common.assert_called_once_with(
                "openeuler.repo",
                os.path.join("etc", "yum.repos.d"),
                "openeuler",
                {},
                str(tmp_path / "rootfs"),
            )

    def test_bytedance_update_repo_config(self, tmp_path):
        """bytedance.update_repo_config 应调用 common 函数并传入正确参数"""
        from repo_config.bytedance.update_repo import update_repo_config

        with patch("repo_config.bytedance.update_repo.common_update_repo_config") as mock_common:
            update_repo_config("bytedance", {}, str(tmp_path / "rootfs"))

            mock_common.assert_called_once_with(
                "sources.list",
                os.path.join("etc", "apt"),
                "bytedance",
                {},
                str(tmp_path / "rootfs"),
            )
