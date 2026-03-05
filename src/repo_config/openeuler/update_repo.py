import os
from repo_config.common.update_repo import common_update_repo_config

def update_repo_config(repo, repo_extra_dic, rootfs_dir):
    repo_file = "openeuler.repo"
    repo_path = os.path.join("etc","yum.repos.d")
    common_update_repo_config(repo_file, repo_path, repo, repo_extra_dic, rootfs_dir)








