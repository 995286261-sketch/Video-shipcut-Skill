# Freesound API key 配置指引卡（模板出生，2026-11-09 定稿）

> 用途：本卡是用户可见卡，照抄渲染、不改写、不即兴散文。渲染时机见文末"出场时机"。
> 红线：key 值永不进对话、永不进日志、永不回显；AI 侧只做"在场/可用"二值核验。

---

【Freesound API key 配置指引】

本项目的「AI 自行寻找 BGM」功能需要使用 Freesound 音乐库，
本机暂时没有找到 Freesound 的 API key（或 key 当前不可用）。

配置只需做一次，约 3 分钟：

第一步 · 申请 key
  1. 浏览器打开 https://freesound.org/apiv2/apply
     （没有账号先免费注册一个）
  2. 表单里 Redirect URL 填：http://localhost:3000/callback
  3. 提交后页面上显示的 Client Secret 就是你的 API key

第二步 · 配置到本机
  打开你自己的终端，逐行粘贴执行下面两条命令
  （第一条把"你的key"替换成刚拿到的那串）：

  echo 'export MUSIC_EXPERT_FREESOUND_TOKEN="你的key"' >> ~/.zshrc
  source ~/.zshrc

第三步 · 回来继续
  配置完成后回到这里说「继续」，我会自动检测一次，
  key 可用就直接进入找 BGM。

提示：key 请粘贴在你自己的终端里，不需要发进对话。

---

## 出场时机（三处，机器判定，不搞软提醒）

1. **G0 末能力盘点**：`capability_audit.py` 的"找乐通道"项探到凭据缺席、
   且本项目 BGM 意向走检索时，盘点结论内联渲染本卡。
2. **找乐门罢工瞬间**：`music_search_freesound.py` 返回
   `blocked/missing_token` 或 `blocked/invalid_token` 时，把本卡原文贴给玩家。
3. **用户主动要卡**：用户说"配置找乐钥匙"一类话术时直接出卡。

钥匙在场且可用时，本卡永不唠叨。

## AI 侧验证动线（值零接触）

- 在场核验只回布尔形状，禁止任何打印值的命令：
  `test -n "${MUSIC_EXPERT_FREESOUND_TOKEN:-}" && echo present || echo absent`
  ——注意：装载本机 shell 配置时也只用不回显的姿势，任何打印含 TOKEN 行的
  输出都禁止（token 泄露三次的既有纪律）。
- 可用核验由找乐脚本自己完成（`/account/self/` 一次轻量调用，见评审 #3 if 链），
  AI 不代跑网络请求、不接触值。
