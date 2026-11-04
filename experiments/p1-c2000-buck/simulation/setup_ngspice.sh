#!/bin/sh
# 在 WSL Ubuntu-22.04、实验目录内执行；只解压，不安装到系统。
set -eu
mkdir -p .tools/debs .tools/ngspice
cd .tools/debs
apt-get download ngspice=36+ds-1ubuntu0.1
dpkg-deb -x ngspice_36+ds-1ubuntu0.1_amd64.deb ../ngspice
cd ../..
.tools/ngspice/usr/bin/ngspice --version
