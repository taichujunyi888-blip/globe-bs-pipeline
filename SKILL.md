---
name: globe-bs-pipeline
description: >
  GLOBE 软件 EM302 多波束后向散射 (backscatter) 处理自动化 skill。
  给定 GLOBE 导出的 .xsf.nc (或原始 .all)，纯命令行 (无需 GUI) 一键生成
  bsar/dtmsliding 全部产物 + 对比图。适用于测绘/海洋勘测课程设计、报告。
  关键前提: 用户机器上装有 GLOBE (自带 miniconda + PyAT 0.1.42), 通过 GLOBE_HOME 环境变量或 --globe_home 指向它。
triggers:
  - 用户要 "GLOBE 后向散射处理" / "bsar" / "bsar dtm" / "Angular Renormalization"
  - 用户要 "自动生成 backscatter 图" / "EM302 后向散射对比图"
  - 用户提到 GLOBE 软件 + 处理 + 不用手动点菜单
---

# GLOBE 后向散射处理 Pipeline (命令行自动化)

## 适用场景
- 已用 GLOBE 把原始 .all 转成 .xsf.nc (Process → SONAR-netCDF 转换)
- 想批量/一键生成: bsar、原始 dtm、Angular Renormalization、Sliding Renormalization
  及其对应 dtm，最后出一张四图对比图 (2x2: 原始/角归一化/滑动归一化/残差)
- 想避免手动在 GLOBE GUI 里点 5+ 次菜单、设参数

## 核心事实 (已验证, 2026-07)
GLOBE 的所有后处理 (BSAR / 归一化 / xsf→dtm) 本质都是同一个引擎:
```
python -m gws.service.deferred_service_executor  (配不同 config json)
```
配置 json 在: `GLOBE_HOME/miniconda/Lib/site-packages/gws/conf/`
- bsar:        `sonar/bs/avg_backscatter_model.json`  → func `compute_mean_model_process`
- renorm:      `sonar/bs/bs_angular_renormalization.json` → func `xsf_constant_process`
- sliding:     `sonar/bs/bs_sliding_angular_renormalization.json` → func `xsf_sliding_process`
- xsf→dtm:     `dtm/convert/sounder_to_dtm.json` → func `SounderToDtmExporter`

脚本里直接复用 PyAT 的 `application_utils.run()` 调这些函数, 绕过 RSocket/GUI。

## 参数自动推断
- **UTM zone**: 从 xsf 的 `Sonar/Beam_group1/platform_longitude` 推断
  `zone = int((lon+180)//6)+1`, 南半球 iff `lat<0`
- **分辨率**: 默认 40m (用户原实验设定), 可 `--res` 改
- **EM302 声呐**: `sounder_type=AUTO` 自动检测, 无需手填
- **引用电平**: renorm 默认 `-20` dB (GLOBE 菜单默认值)
- **滑动窗口**: sliding 默认 10 分钟

→ 用户只需给 .xsf.nc 路径, 其余全自动。无需像 GUI 那样手动填 40m/UTM。

## ⚠️ 关键坑 (必读, 踩过)
1. **DTM 导出必须 `layers=["backscatter"]`** 才会写 backscatter 层。
   不传 layers → 只写 elevation+value_count (空壳, 无 backscatter)。
   但 **不能** 同时依赖 antialias: `spatial_antialiasing=True` 在命令行下
   会崩溃 (GLOBE 自带 conda 环境里 antialias 插值 segfault)。
   → 正确参数: `layers=["backscatter"], spatial_antialiasing=False`
2. **GDAL 环境**: PyAT 的 dtm_angles_computer 用 gdal.Open 读 dtm elevation。
   必须设 `GDAL_DATA / GDAL_DRIVER_PATH / PROJ_DATA` 指向 miniconda/Library,
   否则 `NETCDF:...:elevation does not exist`。
3. **matplotlib 冲突**: GLOBE 的 conda python 在干净/带 GDAL 环境下 savefig 都
   segfault。→ 对比图改用**系统独立 Python** (脚本自动探测 PATH 上的 python,
   或常见安装路径如 C:\Python314), 需 `pip install matplotlib netCDF4 numpy`。
4. **bool 序列化**: 调 PyAT 时参数 dict 用 `repr()` 而非 `json.dumps()`
   (json 小写 true/false Python 不认)。
5. **`--convert` (all→xsf)**: 会启动整个 GLOBE GUI, 不能纯 headless。
   建议用户先在 GLOBE 里手动做这步, 或脚本调 `--convert` 但需要桌面环境。

## 产物清单 (以 stem 为前缀)
- `stem.dtm.nc`              原始 backscatter dtm (UTM, 40m)
- `stem.bsar.nc`             BSAR 角响应统计
- `stem_bs_renorm.xsf.nc`    Angular Renormalization 结果
- `stem_bs_sliding.xsf.nc`   Sliding Angular Renormalization 结果
- `stem_bs_renorm.dtm.nc`    renorm → dtm
- `stem_bs_sliding.dtm.nc`   sliding → dtm
- `stem_backscatter_comparison.png`  四图对比图 (2x2: 原始/角归一化/滑动归一化/残差)

这些 .nc 可直接在 GLOBE 里 File → Open 加载看成图。

## 使用方法
```bash
# 推荐: 先设环境变量 (一次即可, 跨会话生效)
export GLOBE_HOME="D:/path/to/GLOBE"        # Linux/Mac 用 export, Windows 用 set 或系统环境变量面板
python globe_bs_pipeline.py --input D:/data/xxx.xsf.nc

# 或不设环境变量, 每次显式指定
python globe_bs_pipeline.py --input D:/data/xxx.xsf.nc --globe_home D:/path/to/GLOBE

# 指定 UTM/分辨率 (手动覆盖自动推断)
python globe_bs_pipeline.py --input D:/data/xxx.xsf.nc --zone 51 --res 30 --south
```
脚本依赖:
- GLOBE 自带 miniconda 的 PyAT (处理 bsar/归一化/xsf→dtm)
- **系统独立 Python 3.11+** 的 matplotlib/netCDF4/numpy (画对比图, 见下方坑#3)

### 别人使用本 skill 的完整前置 (跨机器)
1. 安装 GLOBE 2.8.x (自带 miniconda + PyAT)
2. 安装一个独立 Python (非 GLOBE conda), 并执行:
   `pip install matplotlib netCDF4 numpy`
2. 在 GLOBE GUI 里把原始 .all 转成 .xsf.nc
   (Process → SONAR-netCDF 转换; 这步必须 GUI, 脚本无法 headless 替代)
3. 设 GLOBE_HOME 环境变量
4. (可选) 先跑环境自检, 确认齐全:
   `python scripts/check_env.py --globe_home <GLOBE目录>`
5. 然后跑上面的命令

→ 无需任何手动填 UTM/分辨率/声呐 (全自动), 也无需知道作者机器路径。

## 验证步骤
1. 跑完检查 7 个产物是否存在且大小合理 (dtm 应有 backscatter 层, >300KB)
2. 用 netCDF4 读 dtm 的 backscatter, 确认 std: 原始 > renorm > sliding
   (归一化后更均匀, std 递减是正确标志)
3. 对比图应有 4 子图 (2x2: 原始/角归一化/滑动归一化/残差) + 各自 colorbar

## 文件
- 主脚本: `scripts/globe_bs_pipeline.py` (见 linked_files)
- 环境自检: `scripts/check_env.py` — agent 接手后先跑, 自动装缺失 pip 包 (`--fix`), 报告 GLOBE/GUI 转换等需人工项
- 调试知识库: `references/globe_debug.md` (GLOBE/PyAT 内部结构、4 个坑的源码级原因、UTM 推断逻辑、产物校验公式) — 改脚本或排查失败时看

## 快速验证命令 (跑完用)
```python
import netCDF4, numpy as np
for f in ["stem.dtm.nc","stem_bs_renorm.dtm.nc","stem_bs_sliding.dtm.nc"]:
    ds=netCDF4.Dataset(f); b=np.ma.masked_invalid(np.asarray(ds.variables['backscatter'][:]).astype(float)); ds.close()
    print(f, "std=%.2f"%b.std())   # 应: 原始 > renorm > sliding
```
