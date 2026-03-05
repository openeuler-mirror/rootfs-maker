# CentOS Kickstart configuration
# Minimal automated installation configuration for CentOS

# System language
lang en_US.UTF-8
keyboard us
timezone UTC

# Root password
rootpw --plaintext root

# Authentication
auth --enableshadow --passalgo=sha512

# Security
selinux --disabled
firewall --disabled

# Network
network --bootproto=dhcp --onboot=yes

# Reboot after installation
reboot

# Partitioning
clearpart --all --initlabel
autopart --type=lvm

# Package selection
%packages
@core
openssh-server
%end

# Post-installation
%post
# Enable root SSH login
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/PermitRootLogin no/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/#PermitRootLogin yes/PermitRootLogin yes/' /etc/ssh/sshd_config

# Restart SSH service
systemctl restart sshd || service sshd restart || /etc/init.d/sshd restart

# Clean package cache
yum clean all || dnf clean all
%end

