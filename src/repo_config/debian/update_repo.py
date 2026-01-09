import os
from repo_config.common.update_repo import common_update_repo_config

def update_repo_config(repo, repo_extra_dic, rootfs_dir):
    repo_file = "sources.list"
    repo_path = os.path.join("etc", "apt")
    common_update_repo_config(repo_file, repo_path, repo, repo_extra_dic, rootfs_dir)








