# globe-bs-pipeline

GLOBE 软件 EM302 多波束后向散射 (backscatter) 处理自动化 skill。
给定 GLOBE 导出的 `.xsf.nc`（或原始 `.all`），**纯命令行、无需 GUI** 一键生成
BSAR / 原始 DTM / Angular Renormalization / Sliding Renormalization 及其对应 DTM，
最后出一张 **四图对比图**（2×2：原始 / 角归一化 / 滑动归一化 / 残差）。

适用于测绘 / 海洋勘测课程设计、实验报告，避免手动在 GLOBE GUI 里点 5+ 次菜单。

## 特性

- **全自动推断参数**：UTM 带号（从 xsf 经度）、半球、分辨率、声呐类型（EM302 AUTO 检测）
- **7 个产物**一步到位
- **四图对比图**：2×2 布局，前三张共享同一色标便于对比，第四张为残差图（原始−滑动，红蓝发散色标）
- **跨机器可分享**：不硬编码任何作者路径，GLOBE 位置靠 `GLOBE_HOME` 环境变量或 `--globe_home` 指定

## 前置依赖（使用者需准备）

1. 安装 **GLOBE 2.8.x**（自带 miniconda + PyAT 0.1.42）
2. 装一个**独立 Python 3.11+**（不要用 GLOBE 自带的 conda），并：
   ```bash
   pip install matplotlib netCDF4 numpy
   ```
3. 在 GLOBE GUI 里把原始 `.all` 转成 `.xsf.nc`
   （`Process → SONAR-netCDF 转换`；这步必须 GUI，脚本无法 headless 替代）
4. 设 `GLOBE_HOME` 环境变量指向 GLOBE 安装目录

## 安装到 Hermes

把本目录整体放到 Hermes 的 skills 目录下（如 `~/.hermes/skills/data-science/globe-bs-pipeline/`）。

## 使用

```bash
# 先跑环境自检（自动检测缺失项，--fix 可自动装 pip 包）
python scripts/check_env.py --globe_home D:/path/to/GLOBE

# 跑 pipeline
python scripts/globe_bs_pipeline.py --input D:/data/xxx.xsf.nc --globe_home D:/path/to/GLOBE
```

不设 `--globe_home` 时，脚本会读取 `GLOBE_HOME` 环境变量。

常用参数：

| 参数 | 说明 | 默认 |
|------|------|------|
| `--input` | `.xsf.nc` 或 `.all` | 必填 |
| `--globe_home` | GLOBE 安装目录 | 读 `GLOBE_HOME` |
| `--zone` | UTM 带号 | 自动推断 |
| `--res` | DTM 分辨率 (米) | 40 |
| `--south` | 南半球 | 自动推断 |

## 产物清单（以 `stem` 为前缀）

- `stem.dtm.nc`            原始 backscatter DTM (UTM, 40m)
- `stem.bsar.nc`           BSAR 角响应统计
- `stem_bs_renorm.xsf.nc`  Angular Renormalization 结果
- `stem_bs_sliding.xsf.nc` Sliding Angular Renormalization 结果
- `stem_bs_renorm.dtm.nc`  renorm → DTM
- `stem_bs_sliding.dtm.nc` sliding → DTM
- `stem_backscatter_comparison.png` 四图对比图

## 正确性验证

归一化后后向散射应更均匀，std 递减是正确标志：

```python
import netCDF4, numpy as np
for f in ["stem.dtm.nc","stem_bs_renorm.dtm.nc","stem_bs_sliding.dtm.nc"]:
    ds = netCDF4.Dataset(f)
    b = np.ma.masked_invalid(np.asarray(ds.variables['backscatter'][:]).astype(float))
    ds.close()
    print(f, "std=%.2f" % b.std())   # 应: 原始 > renorm > sliding
```

## 已知限制

- `.all → .xsf.nc` 转换必须借助 GLOBE GUI，无法 headless 自动化。
- 对比图必须用能独立运行 matplotlib 的系统 Python 生成（GLOBE 自带 conda 的
  matplotlib 在命令行下 `savefig` 会 segfault）。
