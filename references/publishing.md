# 把 skill 发布/分享到 GitHub (跨机器)

用户两次要求把本 skill 推到 GitHub 给别人用。下面是本次实操过的干净流程。

## 前置检查 (本机常缺, 先确认)
- `git` 已装 (一般随 Git for Windows 有); `gh` CLI **通常不装** —— 用 HTTPS+token 更省事。
- 确认没有把数据/大文件误带进去: 仓库只装 skill 目录本身
  (`SKILL.md / README.md / .gitignore / scripts/* / references/*`), 绝不装 `D:/data/*.nc`/`.png`。
- 本 skill 的 `.gitignore` 已忽略 `*.dtm.nc / *.bsar.nc / *_bs_renorm*.nc /
  *_bs_sliding*.nc / *_backscatter_comparison.png / __pycache__/`。

## 步骤 A: 本地仓库 (agent 可独立完成)
```bash
cd <skill_dir>                 # 例: ~/.hermes/skills/data-science/globe-bs-pipeline
git init -q
git add SKILL.md README.md .gitignore scripts/check_env.py scripts/globe_bs_pipeline.py references/globe_debug.md
git commit -m "globe-bs-pipeline: 命令行一键 GLOBE EM302 后向散射处理 (四图对比图)"
```
> 首次提交前需 `git config --global user.name/user.email`; 用用户真实 GitHub
> 账号信息, 否则贡献记录不算他。若本机没配, 临时填 `Yll / yll@local` 也行,
> 但 push 前最好 `git commit --amend --reset-author` 改成真账号。

## 步骤 B: 推到 GitHub (需用户授权, agent 不能代登)
机器上无 `gh`/token/SSH key 时, 用 HTTPS + classic PAT:
1. 用户在 GitHub → New repository, 名 `globe-bs-pipeline`, **不要**勾 Add README
   (本地已有), Public (要给别人用)。
2. 用户生成 token: Settings → Developer settings → PAT (classic), 勾 `repo`,
   复制。用完建议 revoke。
3. agent 执行:
```bash
git remote add origin https://<TOKEN>@github.com/<用户名>/globe-bs-pipeline.git
git branch -M main
git push -u origin main
```
> 若本机 git 默认分支是 `master`, `git branch -M main` 改名对齐 GitHub。
> 用户已给 token 就直接推; 没给就停在这里等授权, 别瞎猜。

## 别人怎么装
clone 后把目录放到自己的 Hermes skills 目录即可 (如 `~/.hermes/skills/data-science/globe-bs-pipeline/`).
注意: GLOBE 软件本身、独立 Python + pip 包、GLOBE_HOME 环境变量仍需使用者自备
(见 SKILL.md "别人使用本 skill 的完整前置")。
