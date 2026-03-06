#!/usr/bin/env python3
# -*- encoding=utf-8 -*-
"""
# **********************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
# [rootfs-maker] is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#          http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# Author:
# Create: 2026-03-05
# Description: update repo config file
# **********************************************************************************
"""

import os
from repo_config.common.update_repo import common_update_repo_config

def update_repo_config(repo, repo_extra_dic, rootfs_dir):
    repo_file = "openeuler.repo"
    repo_path = os.path.join("etc","yum.repos.d")
    common_update_repo_config(repo_file, repo_path, repo, repo_extra_dic, rootfs_dir)








