# 超星学习通 AI 自动答题

基于 **Playwright** 浏览器自动化 + **DeepSeek API** 的自动答题工具，支持章节作业和考试两种场景。

## 目录

- [脚本概览](#脚本概览)
- [环境准备](#环境准备)
- [快速开始](#快速开始)
- [详细配置](#详细配置)
- [章节作业脚本](#章节作业脚本)
- [考试脚本](#考试脚本)
- [技术栈](#技术栈)
- [实现原理](#实现原理)
- [项目结构](#项目结构)
- [常见问题](#常见问题)

---

## 脚本概览

| 脚本 | 用途 | 题型 | 自动提交 | 一键运行 |
|------|------|------|----------|----------|
| `chaoxing_ai_answer.py` | **章节作业** | 单选/多选/判断/填空 | ✅ 自动提交 | `run_chapter_answer.bat` |
| `chaoxing_exam_answer.py` | **考试测试** | 单选/多选/判断/简答 | ❌ 手动交卷 | `run_exam_answer.bat` |

两个脚本共用同一套 Cookie（`chaoxing_cookies.json`），登录一次两边都能用。

---

## 环境准备

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

| 包 | 用途 |
|---|------|
| `playwright` | 浏览器自动化，模拟点击、输入、提交 |
| `httpx` | 异步 HTTP 客户端，调用 DeepSeek API |
| `fonttools` | 解析超星自定义加密字体（font-cxsecret） |

### 2. 安装 Chromium 浏览器

```bash
playwright install chromium
```

Playwright 会下载独立的 Chromium，不需要系统安装 Chrome。

### 3. 配置 API Key

```bash
# Windows PowerShell
$env:DEEPSEEK_API_KEY = "sk-xxxxxxxxxxxxxxxx"

# Windows CMD
set DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

或者直接修改脚本中的 `DEEPSEEK_API_KEY` 默认值。

---

## 快速开始

```bash
# 章节作业
.venv\Scripts\python.exe chaoxing_ai_answer.py --url "章节URL" --mode answer

# 考试
.venv\Scripts\python.exe chaoxing_exam_answer.py --url "考试URL" --mode answer
```

首次运行会弹出浏览器窗口，手动登录一次后 Cookie 自动保存，后续无需重复登录。

---

## 详细配置

### API Key

脚本内置了默认 Key，你也可以通过环境变量覆盖：

```bash
# 使用自定义 DeepSeek API
$env:DEEPSEEK_API_KEY = "sk-your-key"

# 使用其他兼容 API（如 OpenAI、Ollama）
$env:DEEPSEEK_BASE_URL = "https://your-api.com"
```

### URL 获取

在浏览器中登录超星 → 进入目标页面 → 复制地址栏**完整网址**，直接整段粘贴即可。

### Cookie 管理

- 首次运行自动打开浏览器等待手动登录
- 登录后 Cookie 保存到 `chaoxing_cookies.json`
- Cookie 过期时自动检测并提示重新登录

---

## 章节作业脚本

**文件：** `chaoxing_ai_answer.py`  
**适用：** 课程章节的作业/习题页面  

### 运行模式

| 模式 | 命令 | 说明 |
|------|------|------|
| `answer` | `--mode answer` | **自动答题** — 提取题目 → AI作答 → 填入 → 提交 |
| `analyze` | `--mode analyze` | **结构分析** — dump 页面 DOM，排查识别问题 |
| `single` | `--mode single` | **单题测试** — 只测前5题，验证 AI 返回 |

### 题型支持

| 题型 | 识别方式 | 答题方式 |
|------|----------|----------|
| 单选题 | `role="radio"` + `li[onclick*="addChoice"]` | 点击选项 li |
| 多选题 | `role="checkbox"` + 标题标记 `【多选】` | 逐个点击 |
| 判断题 | 标题标记 `【判断】` | A=对 B=错 |
| 填空题 | `textarea` + UEditor | `UE.getEditor().setContent()` |

### 运行流程

1. 导航到章节页面 → 定位答题 iframe → 解密字体
2. 提取所有 `.TiMu` 题目和选项
3. 选择题和填空题分别发 AI（每批 20 题）
4. AI 返回后自动填入答案
5. 点击提交 + 确认弹窗
6. 浏览器保持打开，人工复核

---

## 考试脚本

**文件：** `chaoxing_exam_answer.py`  
**适用：** 课程考试/测试页面 ("整卷预览")

### 与章节作业的关键差异

| 维度 | 章节作业 | 考试 |
|------|----------|------|
| **页面位置** | 多层 iframe 嵌套 | 主页面直接渲染 |
| **题目容器** | `.TiMu` | `.questionLi.singleQuesId` |
| **选项元素** | `li[onclick*="addChoice"]` | `div.answerBg[onclick*="saveSingleSelect"]` |
| **简答编辑器** | UEditor（与填空共用） | UEditor + blur 触发保存 |
| **提交行为** | 自动点击提交 | **不自动交卷**，手动检查后自行点击 |
| **保存** | 无 | 答题完成后自动点击保存按钮 |

### 运行模式

| 模式 | 命令 | 说明 |
|------|------|------|
| `answer` | `--mode answer` | **自动答题** — 提取题目 → AI作答 → 填入 → 保存（不交卷） |
| `analyze` | `--mode analyze` | **结构分析** — dump 考试页面 DOM，排查问题 |

### 题型支持

| 题型 | 识别方式 | 答题方式 |
|------|----------|----------|
| 单选题 | `span.colorShallow` 含"单选" + `role="radio"` | JS 点击 `div.answerBg` |
| 多选题 | `span.colorShallow` 含"多选" + `role="checkbox"` | 逐个点击 |
| 判断题 | `span.colorShallow` 含"判断" | A=对 B=错 |
| 简答题 | `span.colorShallow` 含"简答" | UEditor `setContent()` + blur 触发保存 |

### 简答题处理（三步流程）

```
1. 点击激活 → 点击 .subEditor 激活 UEditor
2. 设值同步 → editor.setContent() + editor.sync()
3. 失焦保存 → 点击题目标题触发 blur → 页面自动保存
```

这是与章节作业填空的最大区别：考试简答题需要在设值后触发 blur 事件，否则页面不会记录答案。

### 运行流程

1. 导航到考试预览页面 → 检测登录 → 解密字体
2. 提取所有 `.questionLi` 题目和选项
3. 分类发送 AI（选择/判断 → 简答）
4. AI 返回后逐题填入答案（每题打印状态）
5. 自动点击"保存"按钮存档进度
6. **浏览器保持打开**，手动检查 → 自行点击"交卷"

---

## 技术栈

| 技术 | 用途 |
|------|------|
| **Python** | 主语言，asyncio 异步 I/O |
| **Playwright** | 浏览器自动化，驱动 Chromium |
| **httpx** | 异步 HTTP 客户端，调用 Chat Completions API |
| **fontTools** | 解析超星自定义字体构建解密映射 |
| **DeepSeek API** | 大语言模型推理正确答案 |

---

## 实现原理

### 整体架构

```
Cookie管理 → 浏览器导航 → 页面结构检测 → 字体解密
    → 题目提取 → AI分批作答 → 答案解析 → 自动填入 → 提交/保存
```

### 1. 页面导航

**章节作业：** 多层 iframe 嵌套结构，通过 `page.frames` 遍历定位 `doHomeWorkNew` 内容 iframe，等待 `.TiMu` 加载。

**考试：** 直接在主页面渲染，无 iframe 嵌套。等待 `.questionLi` 出现即可。4 个空 iframe 是反作弊监控用途，不包含题目内容。

### 2. 字体加密解密

超星使用自定义字体 `font-cxsecret` 混淆题目文字。解密原理：

1. 从页面 `<style>` 提取 base64 字体文件
2. `fontTools` 解析 cmap 表获取 `{码点 → 字形名}` 映射
3. 字形名 `uniXXXX` 中 `XXXX` 即为**原始字符 Unicode 码点**
4. 构建 `{乱码字符 → 真实字符}` 替换所有题目文字

### 3. 题目提取

**章节作业：** 遍历 `.TiMu` → 标题标记 + `li[onclick]` role 判断题型 → `.num_option` / `a.fl.after` 提取选项。

**考试：** 遍历 `.questionLi` → `span.colorShallow` + hidden input 判断题型 → `span.num_option[data]` / `div.answer_p` 提取选项。

### 4. AI 作答

```
题目 → Prompt（含题型标注+选项）→ DeepSeek → 正则解析 → 答案列表
```

- 选择题：`第N题：A` 格式，单选单字母/多选多字母
- 判断：A=对 B=错
- 填空/简答：`第N题：答案文字` 格式
- temperature=0.1 提高确定性
- 多种正则模式容错解析

### 5. 答案填入

**选择题：** JS `click()` 直接触发选项的 onclick 事件。

**填空题（章节作业）：** 调用 `UE.getEditor(id).setContent()` + `sync()`，通过 UEditor API 写入富文本编辑器。

**简答题（考试）：** 三步流程 — 点击激活 → setContent → 失焦触发页面保存机制。

---

## 项目结构

```
web work/
├── chaoxing_ai_answer.py      # 章节作业脚本
├── chaoxing_exam_answer.py    # 考试脚本
├── run_chapter_answer.bat     # 章节作业一键运行
├── run_exam_answer.bat        # 考试一键运行
├── chaoxing_cookies.json      # 登录 Cookie（自动生成）
├── requirements.txt           # Python 依赖
├── README.md                  # 本文件
└── .gitignore                 # Git 忽略规则
```

---

## 常见问题

### Q: Cookie 过期了怎么办？

脚本自动检测跳转到登录页，弹出浏览器等待手动登录。登录后 Cookie 自动更新。

### Q: 题目识别不全或错误？

先运行 `--mode analyze` 查看页面 DOM 结构。如果超星改版导致选择器失效，根据分析结果调整提取逻辑。

### Q: 填空题/简答题内容消失或未保存？

超星使用 UEditor 富文本编辑器，直接操作 textarea 无效。
- **章节填空：** 脚本通过 `UE.getEditor().setContent()` + `sync()` 适配
- **考试简答：** 额外需要点击其他区域触发编辑器 blur 事件，考试页面依赖此事件记录答案

### Q: 考试脚本为什么不自动交卷？

考试交卷后通常不可修改。脚本故意不自动交卷，让你在浏览器中检查所有答案后再手动点击"交卷"。

### Q: AI 回答错误怎么办？

- 使用 `temperature=0.1` 低温度参数提高确定性
- 可在 `build_prompt` 中调整提示词
- 修改 `DEEPSEEK_MODEL` 更换更强模型

### Q: 支持其他 AI API 吗？

支持所有兼容 OpenAI Chat Completions 接口的 API。设置 `DEEPSEEK_BASE_URL` 环境变量即可：

```bash
# Ollama 本地模型
$env:DEEPSEEK_BASE_URL = "http://localhost:11434/v1"
$env:DEEPSEEK_MODEL = "qwen2.5:7b"

# 其他兼容 API
$env:DEEPSEEK_BASE_URL = "https://your-api.com"
```

### Q: 两个脚本的 Cookie 通用吗？

是。共用 `chaoxing_cookies.json`。登录一次，两个脚本都能用。
