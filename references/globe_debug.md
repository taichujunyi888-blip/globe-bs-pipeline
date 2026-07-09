# GLOBE / PyAT 后向散射处理 — 调试知识库

浓缩的本 skill 在 2026-07 开发时踩过的坑与 GLOBE 内部结构。
普通用户只需看 SKILL.md；需要改脚本或排查失败时看这里。

## GLOBE 内部架构 (关键)
GLOBE 的所有后处理菜单 (BSAR / 归一化 / xsf→dtm) 本质都是同一个引擎:
```
python -m gws.service.deferred_service_executor   (配某个 config json)
```
不直接调 `gws.service.deferred_service_executor` 也行 —— 它依赖 RSocket 端口。
**更稳的做法**: 在 GLOBE miniconda 里直接复刻它的调用路径:
```python
from pyat.utils.application_utils import _extract_function, run, _init_logger
from pygws.service.progress_monitor import DefaultMonitor
fn = _extract_function(conf_json_path)   # 从 config 读函数名
logger = _init_logger(fn)
res = run(params_dict, DefaultMonitor, logger, fn)
```
`params_dict` 用 `repr()` 序列化传给子进程 (见下方 bool 坑)。

## 4 个 config 与对应 PyAT 函数
| 步骤 | config 相对路径 | PyAT 函数 |
|------|----------------|-----------|
| xsf→DTM | `dtm/convert/sounder_to_dtm.json` | `pyat.sounder.sounder_to_dtm.SounderToDtmExporter` |
| BSAR | `sonar/bs/avg_backscatter_model.json` | `pyat.sonarscope.bs_correction.stats_computer.compute_mean_model_process` |
| Angular Renorm | `sonar/bs/bs_angular_renormalization.json` | `pyat.sonarscope.bs_correction.angular_renormalization.xsf_constant_process` |
| Sliding Renorm | `sonar/bs/bs_sliding_angular_renormalization.json` | `pyat.sonarscope.bs_correction.sliding_angular_renormalization.xsf_sliding_process` |

config 全在: `GLOBE_HOME/miniconda/Lib/site-packages/gws/conf/`

## 坑 1: DTM 的 backscatter 层 (最阴)
PyAT 源码 `SounderToDtmExporter` (pyat/sounder/sounder_to_dtm.py):
- 默认只写 `elevation` + `value_count` (空壳, 无 backscatter)
- **必须** `layers=["backscatter"]` 才会 `add_layer("backscatter")` 并写出 backscatter 层
- 但同时 `spatial_antialiasing=True` (默认) 在命令行下 antialias 插值阶段 **segfault/崩溃**,
  导致只写出 x/y 坐标的空壳 (6.7KB)
- ✅ 正确参数组合: `layers=["backscatter"], spatial_antialiasing=False`

判别产物好坏: `netCDF4.Dataset(f).variables` 应含 `['x','y','crs','elevation','value_count','backscatter']`,
文件大小通常 >300KB。只有 `['x','y']` 的就是空壳。

## 坑 2: GDAL 环境 (极易漏, 曾导致整条 pipeline segfault)
PyAT 的 `dtm_angles_computer` 用 `gdal.Open("NETCDF:...:elevation")` 读 dtm。
裸跑会报 `NETCDF:...:elevation does not exist` (缺 GDAL_DATA/DRIVER_PATH/PROJ)。

但还有一个更阴的坑: 仅设上面几个变量不够。
`gdal_netCDF.dll` 本身依赖 proj / gdal 核心 DLL, 这些在 `miniconda/Library/bin`。
若 `PATH` 没包含该目录, 加载 gdal_netCDF.dll 会静默失败 (报错 "Can't load requested DLL:
gdal_netCDF.dll / 找不到指定的模块"), 进而在 BSAR / 归一化读 dtm 的 slope 阶段 进程被 killed (segfault, RC=127, 无 Python traceback)。

必须同时把 `miniconda/Library/bin` 前置进 PATH (脚本里 `apply_gdal_env` 已做, 但手动复刻调用时要记得):
```
# 关键: 先加 PATH, 否则 gdal_netCDF.dll 加载失败
os.environ["PATH"] = GLOBE_HOME/miniconda/Library/bin + os.pathsep + os.environ.get("PATH","")
GDAL_DATA      = GLOBE_HOME/miniconda/Library/share/gdal
GDAL_DRIVER_PATH = GLOBE_HOME/miniconda/Library/lib/gdalplugins   # 含 gdal_HDF5.dll / gdal_netCDF.dll
PROJ_DATA/PROJ_LIB = GLOBE_HOME/miniconda/Library/share/proj
NUMEXPR_MAX_THREADS = 16
```
验证 GDAL 是否真可用 (复刻调用前先跑这个, 返回 None 即 PATH 没设对):
```python
from osgeo import gdal
ds = gdal.Open("NETCDF:your.dtm.nc:elevation")   # 返回 None 即失败
arr = ds.ReadAsArray()                            # 能读 array 才算 OK
```

## 坑 3: matplotlib 在 GLOBE conda 下 savefig 崩溃
GLOBE 自带 conda 的 matplotlib (Agg) 在干净环境 / 带 GDAL 环境下 `plt.savefig()` 都
直接 segfault (进程被杀, 无 Python traceback, RC=127/空输出)。
→ 对比图改用**系统独立 Python** (PATH 上的 python, 或 C:\Python314 等),
  需 `pip install matplotlib netCDF4 numpy`。
  子进程里务必 `env.pop` 掉 GDAL_DATA/GDAL_DRIVER_PATH/PROJ_DATA/PROJ_LIB,
  且设 `HOME` (否则 matplotlib 报 "Could not determine home directory")。

## 坑 4: bool 序列化
调 PyAT 时把参数 dict 传给子进程, 用 `repr(params)` **不要** `json.dumps(params)`。
`json.dumps` 产出小写 `true/false`, Python `eval` 不认 → `NameError: name 'true' is not defined`。

## UTM 自动推断
xsf 用 group 组织, 经纬度在 `Sonar/Beam_group1/platform_longitude` / `platform_latitude`。
`zone = int((median_lon + 180)//6) + 1`, `south = median_lat < 0`。
(顶层变量和 `navigation` 组是兜底路径)

## `--convert` (all→xsf) 限制
`globec.exe -nosplash --convert <file.all>` 会启动整个 GLOBE GUI + IPC server,
**不能纯 headless**。脚本里这步需要桌面环境, 建议用户先在 GLOBE GUI 手动做。

## 正确产物校验
读 3 个 dtm 的 backscatter, std 应满足: 原始 > renorm > sliding
(归一化消除入射角效应后更均匀, std 递减 = 处理正确)。
本次实测: 原始 5.37 → renorm 4.87 → sliding 4.60 dB。
