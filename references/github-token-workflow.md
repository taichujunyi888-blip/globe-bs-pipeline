# GitHub 发布: 无 gh CLI, 用 token + API 推送 (已验证 Windows 11 + Git Bash)

## 场景
机器没装 gh CLI, 也不想弹浏览器登录。用 classic Personal Access Token + curl 建仓库/补 description,
git push 时临时带 token (remote 配置不含 token, 安全)。

## 前置
- 用户在 GitHub 建好空仓库 (不要勾 README/.gitignore/License, 本地已有)
- 或让 agent 用 API 建 (见下, 422=已存在则跳过)
- classic token: Settings → Developer settings → PAT (classic) → Generate, 勾 `repo`, 短过期
- 提醒用户: token 用完即 revoke

## 命令 (复制即用, 替换 TOKEN/USER/REPO)
```bash
# 建仓库 (带 description). 201 成功, 422 已存在
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  -d '{"name":"REPO","description":"...","private":false}' \
  https://api.github.com/user/repos

# 补/改 description
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  -d '{"description":"..."}' https://api.github.com/repos/USER/REPO

# 设 remote (无 token) + 带 token 推送
git remote add origin https://github.com/USER/REPO.git
git push -u https://$TOKEN@github.com/USER/REPO.git master

# 验证
curl -s -H "Authorization: Bearer $TOKEN" https://api.github.com/repos/USER/REPO \
  | python -c "import sys,json;d=json.load(sys.stdin);print(d.get('name'),d.get('description'))"
```

## 坑
- commit 作者: 先 `git config user.name/email` 设真实 GitHub 身份, 否则不算用户账号
- remote URL 不得含 token: `git remote get-url origin` 输出应无 `ghp_`
- token 只在 push 命令里出现, 不要写进 remote
- 在 skill 目录内 init git, 不要在含数据的目录 (否则 .gitignore 拦不住仓库外文件)
- 对比图固定 2x2 四张, 不要回归 3 张 (论文样式)
