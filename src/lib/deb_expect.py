#!/usr/bin/env python3
"""
Debian/Ubuntu系统自动化安装脚本
用于通过virsh console连接虚拟机并自动配置preseed安装
"""

import pexpect
import sys
import time
import logging

logger=logging.getLogger("common")

def auto_install_grub(vm_name, preseed_url):
    """
    自动配置GRUB启动参数以使用preseed文件进行自动化安装
    
    Args:
        vm_name: 虚拟机名称
        preseed_url: preseed文件的HTTP URL
    """
    cmd = f"virsh console {vm_name}"
    logger.info(f"正在连接虚拟机: {cmd}")

    # spawn 启动进程
    child = pexpect.spawn(cmd)

    # [关键] 将所有输出实时打印到屏幕，方便调试 ANSI 乱码或状态
    child.logfile = sys.stdout.buffer

    # 设置较长的超时时间，防止启动慢导致脚本退出
    child.timeout = 30

    try:
        # ==========================================
        # 阶段 1: 等待 GRUB 菜单出现
        # 匹配特征文本: "Use the ^ and v keys to select"
        # ==========================================
        logger.info("\n\n[状态] 等待 GRUB 菜单...")
        index = child.expect([
            r"Use the \^ and v keys to select",  # 匹配成功
            r"Press 'e' to edit",  # 另一种GRUB菜单格式
            r"Install",  # 直接显示Install选项
            pexpect.TIMEOUT,                     # 超时
            pexpect.EOF                          # 连接断开
        ])

        if index >= 3:  # TIMEOUT or EOF
            logger.warning("\n[警告] 未检测到 GRUB 菜单，尝试继续执行...")

        # 稍微缓冲一下，确保输入能被接收
        time.sleep(1)
        logger.info("\n[动作] 检测到菜单，发送 'e' 进入编辑模式...")
        child.send('e')

        # ==========================================
        # 阶段 2: 等待编辑界面加载
        # 匹配特征文本: "Minimum Emacs-like screen editing is supported"
        # ==========================================
        logger.info("\n[状态] 等待进入编辑模式...")
        index = child.expect([
            r"Minimum Emacs-like screen editing",
            r"linux",  # 直接看到linux行
            pexpect.TIMEOUT
        ])

        if index == 2:
            logger.error("\n[错误] 未能进入编辑模式")
            return False
            
        logger.info("\n[动作] 已进入编辑模式，开始导航...")
        time.sleep(1)

        # ==========================================
        # 阶段 3: 导航到 linux 行并追加参数
        # 使用 Emacs 快捷键比 ANSI 转义序列更可靠
        # ==========================================

        # 1. 向下移动找到 linux 行
        # 根据实际菜单位置，可能需要调整循环次数
        for i in range(3):
            child.sendcontrol('n')  # 发送 Ctrl+N (Next line)
            time.sleep(0.2)         # 给一点屏幕刷新时间

        # 2. 移动到行尾 (Ctrl+E)
        child.sendcontrol('e')      # 发送 Ctrl+E (End of line)
        time.sleep(0.5)

        # 3. 输入 Preseed 参数
        # 注意最前面的空格，防止和已有参数粘连
        params = f" auto=true priority=critical preseed/url={preseed_url} console=ttyS0"
        logger.info(f"\n[动作] 输入参数: {params}")
        child.send(params)
        time.sleep(0.5)

        # ==========================================
        # 阶段 4: 启动 (Ctrl+X)
        # ==========================================
        logger.info("\n[动作] 发送 Ctrl+X 启动系统...")
        child.sendcontrol('x') # 发送 Ctrl+X

        # ==========================================
        # 阶段 5: 等待安装开始
        # ==========================================
        logger.info("\n[完成] GRUB配置完成，等待安装开始...")
        # 不调用interact()，让函数返回，主程序可以继续监控安装过程
        time.sleep(2)
        return True

    except Exception as e:
        logger.error(f"\n[异常] 发生错误: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Debian/Ubuntu系统自动化安装脚本')
    parser.add_argument('vm_name', help='虚拟机名称')
    parser.add_argument('--preseed-url', required=True, help='Preseed文件的HTTP URL')
    
    args = parser.parse_args()
    auto_install_grub(args.vm_name, args.preseed_url)