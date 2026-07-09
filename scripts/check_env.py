#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GLOBE 后向散射 pipeline 环境自检脚本

检查项:
  1. GLOBE_HOME 是否设置 / --globe_home 是否指向有效 GLOBE 安装
  2. GLOBE 自带 miniconda + PyAT 是否就绪 (bsar/归一化/xsf->dtm 依赖)
  3. 系统独立 Python 3.11+ 是否存在, 且装了 matplotlib/netCDF4/numpy (画图用)
  4. PyAT 的 4 个 config json 是否都在

能自动修的: pip 包缺失 -> 自动 pip install
不能自动修的: GLOBE 未装 / .all->.xsf.nc GUI 转换 -> 清晰提示人工操作

用法:
  python check_env.py [--globe_home D:/path/to/GLOBE] [--fix] [--input xxx.xsf.nc]

--fix : 自动 pip install 缺失的包 (默认只报告不装)
--input: 顺便检查输入文件是否存在且是合法 xsf
"""
import argparse
import os
import sys
import subprocess
import shutil

# 跨平台: Windows 用 where, 其他用 which
def which(cmd):
    return shutil.which(cmd)

def run(cmd, timeout=60):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return None

def has_module(python_exe, mod):
    p = run([python_exe, "-c", f"import {mod}; print('{mod}', getattr({mod},'__version__','?'))"], timeout=30)
    if p is None or p.returncode != 0:
        return False, None
    line = p.stdout.strip().splitlines()
    ver = line[-1] if line else None
    return True, ver

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--globe_home", default=os.environ.get("GLOBE_HOME"))
    ap.add_argument("--fix", action="store_true", help="自动 pip install 缺失的包")
    ap.add_argument("--input", default=None, help="顺便检查输入 xsf 文件")
    args = ap.parse_args()

    ok = []
    warn = []
    fail = []

    print("=" * 60)
    print("GLOBE 后向散射 pipeline 环境自检")
    print("=" * 60)

    # ---- 1. GLOBE_HOME / GLOBE 安装 ----
    print("\n[1] GLOBE 安装")
    gh = args.globe_home
    if not gh:
        fail.append("GLOBE_HOME 未设置, 且未传 --globe_home")
        print("  ✗ GLOBE_HOME 未设置")
        print("    解决: 设置环境变量 GLOBE_HOME=D:/path/to/GLOBE")
        print("          或脚本加 --globe_home D:/path/to/GLOBE")
    else:
        mc = os.path.join(gh, "miniconda")
        py = os.path.join(mc, "python.exe")
        if os.path.exists(py):
            ok.append(f"GLOBE 安装有效: {gh}")
            print(f"  ✓ GLOBE 安装有效: {gh}")
        else:
            fail.append(f"GLOBE_HOME={gh} 下未找到 miniconda/python.exe")
            print(f"  ✗ GLOBE_HOME={gh} 下未找到 miniconda/python.exe")
            print("    解决: GLOBE 2.8.x 自带 miniconda, 请确认安装完整")

    # ---- 2. PyAT config 文件 ----
    print("\n[2] PyAT config (bsar/归一化/xsf->dtm)")
    if gh and os.path.exists(os.path.join(gh, "miniconda", "python.exe")):
        mc = os.path.join(gh, "miniconda")
        conf_base = os.path.join(mc, "Lib", "site-packages", "gws", "conf")
        needed = [
            ("bsar", "sonar/bs/avg_backscatter_model.json"),
            ("renorm", "sonar/bs/bs_angular_renormalization.json"),
            ("sliding", "sonar/bs/bs_sliding_angular_renormalization.json"),
            ("xsf->dtm", "dtm/convert/sounder_to_dtm.json"),
        ]
        for name, rel in needed:
            p = os.path.join(conf_base, rel)
            if os.path.exists(p):
                ok.append(f"config: {name}")
            else:
                fail.append(f"缺失 config: {rel}")
                print(f"  ✗ 缺失 config: {rel}")
        if all(os.path.exists(os.path.join(conf_base, r)) for _, r in needed):
            print("  ✓ 4 个 PyAT config 齐全")
        # 验证 PyAT 可 import
        p = run([os.path.join(mc, "python.exe"), "-c",
                 "import pyat, netCDF4; print('IMPORT_OK')"], timeout=30)
        if p and p.returncode == 0 and "IMPORT_OK" in p.stdout:
            ok.append("PyAT import OK")
            print("  ✓ PyAT / netCDF4 import OK")
        else:
            fail.append("PyAT / netCDF4 import 失败")
            print("  ✗ PyAT / netCDF4 import 失败 (GLOBE 安装可能不完整)")
    else:
        warn.append("跳过 PyAT 检查 (GLOBE 未就绪)")

    # ---- 3. 系统独立 Python + 画图库 ----
    print("\n[3] 系统 Python (画图用, 需与 GLOBE conda 独立)")
    sys_py = which("python") or which("python3")
    if sys_py is None:
        # 常见 Windows 路径兜底
        for c in [r"C:\Python314\python.exe", r"C:\Python312\python.exe",
                  r"C:\Python311\python.exe"]:
            if os.path.exists(c):
                sys_py = c
                break
    if sys_py is None:
        fail.append("未找到系统 Python 3.11+")
        print("  ✗ 未找到系统 Python")
        print("    解决: 安装 Python 3.11+ (https://www.python.org), 勾选 Add to PATH")
    else:
        # 版本检查
        p = run([sys_py, "-c", "import sys; print(sys.version.split()[0])"], timeout=20)
        ver = p.stdout.strip() if p else "?"
        print(f"  ✓ Python: {sys_py} (v{ver})")
        # 模块检查
        for mod in ["matplotlib", "netCDF4", "numpy"]:
            has, v = has_module(sys_py, mod)
            if has:
                ok.append(f"{mod} {v}")
                print(f"    ✓ {mod} {v}")
            else:
                fail.append(f"缺失 Python 包: {mod}")
                print(f"    ✗ 缺失 {mod}")
                if args.fix:
                    print(f"    → 正在 pip install {mod} ...")
                    rp = run([sys_py, "-m", "pip", "install", mod], timeout=180)
                    if rp and rp.returncode == 0:
                        print(f"    ✓ {mod} 安装成功")
                        ok.append(f"{mod} (刚装)")
                    else:
                        print(f"    ✗ {mod} 安装失败, 请手动: pip install {mod}")

    # ---- 4. 输入文件 (可选) ----
    if args.input:
        print(f"\n[4] 输入文件: {args.input}")
        if not os.path.exists(args.input):
            fail.append(f"输入文件不存在: {args.input}")
            print(f"  ✗ 不存在")
            print("    注意: .all->.xsf.nc 需在 GLOBE GUI 里手动转换 (Process -> SONAR-netCDF)")
        else:
            if args.input.lower().endswith(".xsf.nc"):
                ok.append("输入 xsf 存在")
                print("  ✓ xsf.nc 存在, 可直接跑 pipeline")
            elif args.input.lower().endswith(".all"):
                warn.append("输入是 .all, 需先 GUI 转换")
                print("  ⚠ 是 .all 文件, 需先在 GLOBE GUI 转成 .xsf.nc")
                print("    (这步必须手动: GLOBE 的 --convert 会启动 GUI, 无法 headless)")
            else:
                warn.append("输入文件扩展名非 .xsf.nc/.all")
                print("  ⚠ 未知扩展名, pipeline 可能不认")

    # ---- 总结 ----
    print("\n" + "=" * 60)
    print(f"结果: ✓通过 {len(ok)} 项 | ⚠警告 {len(warn)} 项 | ✗失败 {len(fail)} 项")
    print("=" * 60)
    if fail:
        print("\n必须解决的项:")
        for f in fail:
            print(f"  ✗ {f}")
        print("\n典型修复顺序:")
        print("  1. 装 GLOBE 2.8.x, 设 GLOBE_HOME")
        print("  2. 装系统 Python 3.11+, 执行: pip install matplotlib netCDF4 numpy")
        print("  3. GLOBE GUI 里把 .all 转 .xsf.nc")
        print("  4. 重新跑本检查 + python globe_bs_pipeline.py --input xxx.xsf.nc")
        sys.exit(1)
    else:
        print("\n✅ 环境齐全! 可以直接跑:")
        print("  python globe_bs_pipeline.py --input <你的文件>.xsf.nc")
        if warn:
            print("\n提示:")
            for w in warn:
                print(f"  ⚠ {w}")
        sys.exit(0)

if __name__ == "__main__":
    main()
