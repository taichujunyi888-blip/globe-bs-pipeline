#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GLOBE 后向散射处理 pipeline (纯命令行版, 无需 GUI)
依赖: GLOBE 自带 miniconda 里的 PyAT 0.1.42 + GDAL

流程 (输入 .xsf.nc):
  1. SONAR-netCDF -> DTM        (原始 backscatter dtm, 需 UTM/分辨率)
  2. BSAR (角响应统计)          -> *.bsar.nc
  3. Angular Renormalization    -> *_bs_renorm.xsf.nc
  4. Sliding Angular Renorm.    -> *_bs_sliding.xsf.nc
  5. renorm/sliding -> DTM       -> *_bs_renorm.dtm.nc / *_bs_sliding.dtm.nc
  6. 生成对比图 (2x2: 原始 / Angular / Sliding / 残差)

用法:
  python globe_bs_pipeline.py --input <file.xsf.nc> [--zone 2] [--res 40] [--south]
                              [--globe_home <GLOBE安装目录>] [--outdir <输出目录>]

环境变量 (推荐):
  GLOBE_HOME  指向 GLOBE 安装目录 (含 miniconda 子目录), 设了就无需 --globe_home

前置依赖:
  1. GLOBE 软件 (2.8.x, 自带 miniconda + PyAT) 已安装
  2. 系统 Python 3.11+ (与 GLOBE conda 独立), 且已 pip install matplotlib netCDF4 numpy
     —— GLOBE 自带 conda 的 matplotlib 在命令行下会崩溃, 对比图必须用系统 Python

UTM zone 不传则自动从 xsf 经度推断; 南半球自动判断。
"""
import argparse
import os
import sys
import json
import logging
import subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("globe_bs")


def setup_globe_env(globe_home: str):
    """返回 gws_conf 目录路径并配置 GDAL/PROJ 环境变量"""
    mc = os.path.join(globe_home, "miniconda")
    python_exe = os.path.join(mc, "python.exe")
    if not os.path.exists(python_exe):
        raise FileNotFoundError(f"未找到 GLOBE miniconda: {python_exe}")
    apply_gdal_env(mc)
    gws_conf = os.path.join(mc, "Lib", "site-packages", "gws", "conf")
    return python_exe, gws_conf


def apply_gdal_env(mc):
    # GDAL 核心 DLL (proj/gdal 等) 在 Library/bin, 必须进 PATH 否则 gdal_netCDF.dll 加载失败 (segfault)
    lib_bin = os.path.join(mc, "Library", "bin")
    if lib_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = lib_bin + os.pathsep + os.environ.get("PATH", "")
    os.environ["GDAL_DATA"] = os.path.join(mc, "Library", "share", "gdal")
    os.environ["GDAL_DRIVER_PATH"] = os.path.join(mc, "Library", "lib", "gdalplugins")
    os.environ["PROJ_DATA"] = os.path.join(mc, "Library", "share", "proj")
    os.environ["PROJ_LIB"] = os.path.join(mc, "Library", "share", "proj")
    os.environ["NUMEXPR_MAX_THREADS"] = "16"


def run_pyat_in_globe(globe_home, gws_conf, conf_rel, params: dict):
    """在 GLOBE miniconda 里跑一个 PyAT 处理 (复用 application_utils.run 路径)"""
    mc = os.path.join(globe_home, "miniconda")
    conf_file = os.path.join(gws_conf, conf_rel)
    if not os.path.exists(conf_file):
        raise FileNotFoundError(f"找不到 config: {conf_file}")
    script = (
        "import logging\n"
        "logging.basicConfig(level=logging.INFO)\n"
        "from pyat.utils.application_utils import _extract_function, run, _init_logger\n"
        "from pygws.service.progress_monitor import DefaultMonitor\n"
        f"conf = r'{conf_file}'\n"
        "fn = _extract_function(conf)\n"
        "logger = _init_logger(fn)\n"
        "monitor = DefaultMonitor\n"
        f"args = {repr(params)}\n"
        "res = run(args, monitor, logger, fn)\n"
        "print('PYAT_RESULT:' + str(res is not None))\n"
    )
    env = os.environ.copy()
    apply_gdal_env(mc)
    p = subprocess.run([os.path.join(mc, "python.exe"), "-c", script],
                       capture_output=True, text=True, env=env, cwd=mc, timeout=600)
    if p.returncode != 0:
        log.error("PyAT 失败 (%s):\n%s\n%s", conf_rel, p.stdout[-2000:], p.stderr[-2000:])
        raise RuntimeError(f"PyAT 步骤失败: {conf_rel}")
    if "PYAT_RESULT:" not in p.stdout:
        log.warning("  无 PYAT_RESULT (可能仍成功): %s", conf_rel)


def infer_utm(xsf_path: str, globe_home: str):
    """从 xsf 经度推断 UTM zone + 半球"""
    mc = os.path.join(globe_home, "miniconda")
    env = os.environ.copy()
    apply_gdal_env(mc)
    script = (
        "import netCDF4, numpy as np, json\n"
        f"ds = netCDF4.Dataset(r'{xsf_path}')\n"
        "lon=None; lat=None\n"
        "# 1) 顶层变量\n"
        "for n in ds.variables:\n"
        "    v=ds.variables[n]\n"
        "    if v.ndim>=1 and ('lon' in n.lower() or 'east' in n.lower()):\n"
        "        lon=np.asarray(v[:]).ravel()\n"
        "    if v.ndim>=1 and ('lat' in n.lower() or 'north' in n.lower()):\n"
        "        lat=np.asarray(v[:]).ravel()\n"
        "# 2) Sonar/Beam_group1 平台经纬度 (CF 标准命名)\n"
        "if lon is None or lat is None:\n"
        "    try:\n"
        "        bg=ds.groups['Sonar'].groups['Beam_group1']\n"
        "        if 'platform_longitude' in bg.variables: lon=np.asarray(bg.variables['platform_longitude'][:]).ravel()\n"
        "        if 'platform_latitude' in bg.variables: lat=np.asarray(bg.variables['platform_latitude'][:]).ravel()\n"
        "    except Exception: pass\n"
        "# 3) navigation 组兜底\n"
        "if lon is None:\n"
        "    nav=ds.groups.get('navigation')\n"
        "    if nav:\n"
        "        for n in nav.variables:\n"
        "            if 'lon' in n.lower(): lon=np.asarray(nav.variables[n][:]).ravel()\n"
        "            if 'lat' in n.lower(): lat=np.asarray(nav.variables[n][:]).ravel()\n"
        "lon=lon[np.isfinite(lon)]; lat=lat[np.isfinite(lat)]\n"
        "print('LONLAT:'+json.dumps({'lon':float(np.median(lon)),'lat':float(np.median(lat))}))\n"
    )
    p = subprocess.run([os.path.join(mc, "python.exe"), "-c", script],
                       capture_output=True, text=True, env=env, cwd=mc, timeout=120)
    for line in p.stdout.splitlines():
        if line.startswith("LONLAT:"):
            d = json.loads(line.split(":", 1)[1])
            lon, lat = d["lon"], d["lat"]
            zone = int((lon + 180) // 6) + 1
            south = lat < 0
            return zone, south
    raise RuntimeError("无法从 xsf 推断 UTM (无经纬度)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help=".xsf.nc 或 .all 文件")
    ap.add_argument("--globe_home", default=os.environ.get("GLOBE_HOME"),
                     help="GLOBE 安装目录 (含 miniconda)。也可用环境变量 GLOBE_HOME 设置")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--zone", type=int, default=None, help="UTM 带号, 不传则自动推断")
    ap.add_argument("--res", type=float, default=40.0, help="DTM 分辨率 (米)")
    ap.add_argument("--south", action="store_true", help="南半球 (不传自动推断)")
    ap.add_argument("--datum", default="WGS84")
    ap.add_argument("--skip_dtm_raw", action="store_true")
    ap.add_argument("--make_fig", action="store_true", default=True)
    args = ap.parse_args()

    inp = os.path.abspath(args.input)
    if not os.path.exists(inp):
        log.error("输入不存在: %s", inp); sys.exit(1)

    if not args.globe_home:
        log.error("未指定 GLOBE 安装目录！请二选一:\n"
                   "  1) 设置环境变量 GLOBE_HOME=D:\\path\\to\\GLOBE\n"
                   "  2) 加参数 --globe_home D:\\path\\to\\GLOBE")
        sys.exit(1)

    outdir = args.outdir or os.path.dirname(inp)
    os.makedirs(outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(inp))[0]
    if base.endswith(".xsf"):
        base = base[:-4]
    stem = os.path.join(outdir, base)

    python_exe, gws_conf = setup_globe_env(args.globe_home)

    # 若输入是 .all -> 先转换 (需要 GLOBE GUI/转换服务)
    xsf = inp
    if inp.lower().endswith(".all"):
        log.info("输入 .all -> 调用 GLOBE 转换 (需 GUI)...")
        subprocess.run([os.path.join(args.globe_home, "globec.exe"), "-nosplash",
                        "--convert", inp], timeout=600, check=True)
        xsf = stem + ".xsf.nc"
        if not os.path.exists(xsf):
            raise RuntimeError("all->xsf 转换未产出 " + xsf)

    log.info("输入 xsf: %s", xsf)

    # UTM 推断
    if args.zone is None:
        zone, south_auto = infer_utm(xsf, args.globe_home)
        south = args.south or south_auto
        log.info("自动推断 UTM zone=%d, 南半球=%s", zone, south)
    else:
        zone, south = args.zone, args.south
    proj = f"+proj=utm +zone={zone} +{'south +' if south else ''}datum={args.datum} +units=m +no_defs"

    # 1. 原始 DTM (backscatter) — 已存在则跳过
    dtm_raw = stem + ".dtm.nc"
    if not args.skip_dtm_raw and not os.path.exists(dtm_raw):
        log.info("[1/5] 生成原始 DTM (backscatter, %g m)...", args.res)
        run_pyat_in_globe(args.globe_home, gws_conf, "dtm/convert/sounder_to_dtm.json", {
            "i_paths": [xsf], "o_paths": [dtm_raw], "overwrite": True,
            "layers": ["backscatter"], "target_spatial_reference": proj,
            "target_resolution": args.res, "valid_soundings_only": True,
            "spatial_antialiasing": False,
        })

    # 2. BSAR
    bsar = stem + ".bsar.nc"
    if not os.path.exists(bsar):
        log.info("[2/5] 生成 BSAR (角响应统计)...")
        run_pyat_in_globe(args.globe_home, gws_conf, "sonar/bs/avg_backscatter_model.json", {
            "i_paths": [xsf], "o_path": bsar, "overwrite": True,
            "sounder_type": "AUTO", "i_dtm": dtm_raw,
            "use_svp": True, "use_insonified_area": True,
            "remove_compensation": True, "remove_calibration": True,
            "integration_method": "MEAN", "linear_scale": "ENERGY",
        })

    # 3. Angular Renormalization
    renorm = stem + "_bs_renorm.xsf.nc"
    if not os.path.exists(renorm):
        log.info("[3/5] Angular Renormalization...")
        run_pyat_in_globe(args.globe_home, gws_conf, "sonar/bs/bs_angular_renormalization.json", {
            "i_paths": [xsf], "o_paths": [renorm], "overwrite": True,
            "mean_model_file": bsar, "apply_compensation": True,
            "reference_level": -20, "use_snippets": False, "i_dtm": dtm_raw,
        })

    # 4. Sliding Angular Renormalization
    sliding = stem + "_bs_sliding.xsf.nc"
    if not os.path.exists(sliding):
        log.info("[4/5] Sliding Angular Renormalization...")
        run_pyat_in_globe(args.globe_home, gws_conf, "sonar/bs/bs_sliding_angular_renormalization.json", {
            "i_paths": [xsf], "o_paths": [sliding], "overwrite": True,
            "sounder_type": "AUTO", "sliding_window": 10,
            "ref_angle_min": 30, "ref_angle_max": 60, "i_dtm": dtm_raw,
            "use_snippets": False, "use_svp": True, "use_insonified_area": True,
            "remove_calibration": True,
        })

    # 5. renorm/sliding -> DTM
    renorm_dtm = stem + "_bs_renorm.dtm.nc"
    sliding_dtm = stem + "_bs_sliding.dtm.nc"
    if not os.path.exists(renorm_dtm):
        log.info("[5a] renorm -> DTM...")
        run_pyat_in_globe(args.globe_home, gws_conf, "dtm/convert/sounder_to_dtm.json", {
            "i_paths": [renorm], "o_paths": [renorm_dtm], "overwrite": True,
            "layers": ["backscatter"], "target_spatial_reference": proj,
            "target_resolution": args.res, "valid_soundings_only": True,
            "spatial_antialiasing": False,
        })
    if not os.path.exists(sliding_dtm):
        log.info("[5b] sliding -> DTM...")
        run_pyat_in_globe(args.globe_home, gws_conf, "dtm/convert/sounder_to_dtm.json", {
            "i_paths": [sliding], "o_paths": [sliding_dtm], "overwrite": True,
            "layers": ["backscatter"], "target_spatial_reference": proj,
            "target_resolution": args.res, "valid_soundings_only": True,
            "spatial_antialiasing": False,
        })

    # 6. 对比图
    if args.make_fig:
        fig = os.path.join(outdir, base + "_backscatter_comparison.png")
        log.info("[6/6] 生成对比图 -> %s", fig)
        make_comparison(python_exe, dtm_raw, renorm_dtm, sliding_dtm, bsar, fig, args.globe_home)
        log.info("对比图已生成: %s", fig)

    log.info("全部完成! 产物目录: %s", outdir)
    for f in [dtm_raw, bsar, renorm, sliding, renorm_dtm, sliding_dtm]:
        if os.path.exists(f):
            log.info("  OK %s", os.path.basename(f))


def make_comparison(python_exe, dtm_raw, renorm_dtm, sliding_dtm, bsar, fig, globe_home):
    """用系统 Python (非 GLOBE conda, 避免 GDAL/matplotlib 冲突) 画对比图。
    自动探测系统 python, 不依赖特定用户名/路径。"""
    import shutil
    sys_py = shutil.which("python") or shutil.which("python3")
    if sys_py is None:
        # 常见安装位置兜底 (Windows)
        candidates = [
            r"C:\Users\%s\AppData\Local\Programs\Python\Python314\python.exe" % os.environ.get("USERNAME", ""),
            r"C:\Python314\python.exe",
            r"C:\Python312\python.exe",
            r"C:\Python311\python.exe",
        ]
        for c in candidates:
            if c and os.path.exists(c):
                sys_py = c
                break
    if sys_py is None:
        raise RuntimeError("找不到系统 Python！请安装 Python 3.11+ 并 pip install matplotlib netCDF4 numpy，\n"
                           "或将其加入 PATH。GLOBE 自带 conda 的 matplotlib 在命令行下会崩溃。")
    env = os.environ.copy()
    env.pop("GDAL_DATA", None)
    env.pop("GDAL_DRIVER_PATH", None)
    env.pop("PROJ_DATA", None)
    env.pop("PROJ_LIB", None)
    env["HOME"] = os.environ.get("HOME") or os.path.expanduser("~")
    script = (
        "import matplotlib, os\n"
        "matplotlib.use('Agg')\n"
        "# 尝试加载中文字体 (simhei) 否则退化为英文标题\n"
        "import matplotlib.font_manager as fm\n"
        "cn_font=None\n"
        "for p in [r'C:\\Windows\\Fonts\\simhei.ttf', r'C:\\Windows\\Fonts\\msyh.ttc']:\n"
        "    if os.path.exists(p):\n"
        "        cn_font=fm.FontProperties(fname=p); break\n"
        "if cn_font: matplotlib.rcParams['font.family']=cn_font.get_name()\n"
        "matplotlib.rcParams['axes.unicode_minus']=False\n"
        "import netCDF4, numpy as np\n"
        "import matplotlib.pyplot as plt\n"
        "def load_bs(p):\n"
        "    ds=netCDF4.Dataset(p); b=np.asarray(ds.variables['backscatter'][:]).astype(float); ds.close()\n"
        "    return np.ma.masked_invalid(b)\n"
        f"raw=load_bs(r'{dtm_raw}')\n"
        f"ren=load_bs(r'{renorm_dtm}')\n"
        f"sli=load_bs(r'{sliding_dtm}')\n"
        "# 共享色标: 三张 backscatter 取合并数据 2-98 分位 (便于对比)\n"
        "allv=np.ma.concatenate([raw,ren,sli]).compressed()\n"
        "vmin=float(np.percentile(allv,2)); vmax=float(np.percentile(allv,98))\n"
        "# 残差 (原始 - 滑动), 仅公共有效像元\n"
        "mask=np.ma.getmaskarray(raw)|np.ma.getmaskarray(sli)\n"
        "resid=np.ma.masked_where(mask, raw-sli)\n"
        "rl=float(np.percentile(np.abs(resid.compressed()),98)); rl=max(rl,0.1)\n"
        "fig,axs=plt.subplots(2,2,figsize=(13,11))\n"
        "panels=[(0,0,raw,'Original backscatter'),(0,1,ren,'Angular Renormalization'),(1,0,sli,'Sliding Angular Renormalization'),(1,1,resid,'Residual (Original - Sliding)')]\n"
        "for i,(r,c,d,t) in enumerate(panels):\n"
        "    ax=axs[r,c]\n"
        "    if i<3:\n"
        "        im=ax.imshow(d,cmap='jet',vmin=vmin,vmax=vmax,aspect='auto')\n"
        "    else:\n"
        "        im=ax.imshow(d,cmap='RdBu_r',vmin=-rl,vmax=rl,aspect='auto')\n"
        "    ax.set_title(t+'\\nmedian=%.1f dB'%np.ma.median(d),fontsize=11)\n"
        "    ax.set_xticks([]); ax.set_yticks([])\n"
        "    plt.colorbar(im,ax=ax,label='dB',fraction=0.046,pad=0.04)\n"
        "fig.suptitle('EM302 Backscatter: Original vs Angular & Sliding Renormalization',fontsize=13)\n"
        "plt.tight_layout()\n"
        f"plt.savefig(r'{fig}',dpi=110)\n"
        "print('FIG_DONE')\n"
    )
    p = subprocess.run([sys_py, "-c", script], capture_output=True, text=True,
                       env=env, timeout=300)
    if "FIG_DONE" not in p.stdout:
        raise RuntimeError("对比图生成失败:\n" + (p.stderr or p.stdout)[-1500:])


if __name__ == "__main__":
    main()
