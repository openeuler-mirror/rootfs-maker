import os
import random
import shutil
from pathlib import Path

def copy_repo_file_to_tmp(repo_name, repo_file):
    parent_dir = Path(__file__).parent.parent
    repo_file_path = os.path.join(parent_dir, repo_name, repo_file)
    print(f"repo file is {repo_file_path}")

    # 创建临时目录用于复制source.list并进行修改
    tmp_dir = os.path.join(parent_dir, repo_name, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # 复制sources.list到临时目录，为支持并发，目标文件带随机数
    random_num = random.randint(1000, 9999)
    tmp_repo_file = f"{repo_file}.{random_num}"
    tmp_repo_file_path = os.path.join(tmp_dir, tmp_repo_file)
    print(f"tmp repo file is {tmp_repo_file_path}")
    shutil.copy2(repo_file_path, tmp_repo_file_path)
    return tmp_repo_file_path

def modify_tmp_repo_file_with_extra_param(tmp_repo_file_path, extra_param):
    with open(tmp_repo_file_path, 'r', encoding='utf-8') as f:
        file_content = f.read()
    # 执行替换：把所有匹配到的old_content都替换成new_content
    if extra_param:
        for key, value in extra_param.items():
            file_content = file_content.replace(key, value)
    print(f"file modified content is {file_content}")
    # 重新写入文件
    with open(tmp_repo_file_path, 'w', encoding='utf-8') as f:
        f.write(file_content)

def copy_repo_config_to_rootfs(tmp_repo_file, repo_file, repo_path, rootfs_dir):
    target_path = os.path.join(Path(rootfs_dir), repo_path)
    target_file = os.path.join(target_path, repo_file)
    print(f"copy repo config {tmp_repo_file} to {target_path}")
    os.makedirs(target_path, exist_ok=True)
    shutil.copy2(tmp_repo_file, target_file)

def clean_tmp_repo_file(tmp_repo_file):
    if os.path.exists(tmp_repo_file):
        print(f"remove tmp repo file {tmp_repo_file}")
        os.remove(tmp_repo_file)

def common_update_repo_config(repo_file, repo_path, repo_name, repo_extra_dic, rootfs_dir):
    print(f"update repo with repo extra is {repo_extra_dic}")
    print(f"1 创建临时repo文件")
    tmp_repo_file_path = copy_repo_file_to_tmp(repo_name, repo_file)
    print(f"2 修改临时repo文件")
    modify_tmp_repo_file_with_extra_param(tmp_repo_file_path, repo_extra_dic)
    print(f"3 把修改后临时repo文件拷贝rootfs中")
    copy_repo_config_to_rootfs(tmp_repo_file_path, repo_file, repo_path, rootfs_dir)
    print(f"4 清理临时repo文件")
    clean_tmp_repo_file(tmp_repo_file_path)







