# 超星学习通 AI 自动答题

基于 **Playwright** 浏览器自动化 + **DeepSeek API** 大语言模型的超星学习通自动答题脚本，支持单选题、多选题、判断题、填空题（含多空）。

## 目录

- [环境准备](#环境准备)
- [快速开始](#快速开始)
- [详细配置](#详细配置)
- [使用方法](#使用方法)
- [技术栈](#技术栈)
- [实现原理](#实现原理)
- [常见问题](#常见问题)

---

## 环境准备

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

依赖包：
| 包 | 用途 |
|---|------|
| `playwright` | 浏览器自动化，模拟点击、输入、提交 |
| `httpx` | 异步 HTTP 客户端，调用 AI API |
| `fontTools` | 解析超星自定义加密字体 |

### 2. 安装 Chromium 浏览器

```bash
playwright install chromium
```

Playwright 会下载一个独立的 Chromium，不需要你系统上有 Chrome。

---

## 快速开始

```bash
# 1. 设置 API Key
set DEEPSEEK_API_KEY=你的密钥          # Windows CMD
# 或
$env:DEEPSEEK_API_KEY = "你的密钥"     # Windows PowerShell

# 2. 运行（首次会打开浏览器让你登录）
python chaoxing_ai_answer.py --url "章节页面的完整URL" --mode answer
```

---

## 详细配置

### 1. DeepSeek API Key（必须）

**方式一：环境变量（推荐）**

```bash
# Windows PowerShell
$env:DEEPSEEK_API_KEY = "sk-xxxxxxxxxxxxxxxx"

# Windows CMD
set DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx

# Linux / macOS
export DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

**方式二：直接修改脚本**

编辑 `chaoxing_ai_answer.py` 第 23 行，将 API Key 填入默认值：
```python
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-你的密钥")
```

> 如果使用 DeepSeek 以外的 API（如 OpenAI、Ollama、本地模型等），同时设置 `DEEPSEEK_BASE_URL` 环境变量指向兼容的 API 地址。

### 2. 目标章节 URL（必须）

**方式一：写入脚本**

编辑 `chaoxing_ai_answer.py` 第 29 行：
```python
TARGET_URL = "https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=..."
```

**方式二：命令行参数（每次指定）**

```bash
python chaoxing_ai_answer.py --url "完整URL" --mode answer
```

> **如何获取 URL：** 在浏览器中登录超星学习通 → 进入课程 → 点击要答题的章节 → 复制浏览器地址栏的**完整网址**。不要手动挑选参数，直接整段复制粘贴即可。

### 3. 登录与 Cookie（首次运行自动完成）

首次运行时脚本会打开一个浏览器窗口：
1. 在浏览器中**手动登录**超星学习通（账号密码 / 扫码）
2. 确认已经进入课程页面
3. 回到终端按 **Enter**
4. Cookie 会自动保存到 `chaoxing_cookies.json`，后续运行无需重复登录

Cookie 过期后脚本会自动检测跳转到登录页，并提示你重新登录。

---

## 使用方法

### 三种运行模式

| 模式 | 命令 | 说明 |
|------|------|------|
| `answer` | `--mode answer` | **自动答题**（最常用）— 提取题目、调用 AI、填入答案、提交 |
| `analyze` | `--mode analyze` | **结构分析** — 打印页面 DOM 结构和 CSS class，用于调试 |
| `single` | `--mode single` | **单题测试** — 只取前 5 题，查看 AI 返回结果，验证解析正确性 |

### 常用命令

```bash
# 自动答题（写入脚本的默认 URL）
python chaoxing_ai_answer.py --mode answer

# 自动答题（命令行指定 URL）
python chaoxing_ai_answer.py --url "https://mooc1.chaoxing.com/mycourse/studentstudy?..." --mode answer

# 分析页面结构（题目识别有问题时先用这个排查）
python chaoxing_ai_answer.py --url "https://..." --mode analyze
```

### 运行过程

1. 脚本导航到目标章节页面
2. 定位答题 iframe，识别并解密加密字体
3. 提取所有题目的题干和选项
4. 将所有题目打印到终端供预览
5. 选择题和填空题分别分批发送给 AI（每批 20 题）
6. AI 返回答案后，脚本自动执行：
   - 选择题：点击对应选项（多选逐个点击）
   - 填空题：通过 UEditor API 填入答案文字
7. 全部作答完成后自动点击提交按钮并确认弹窗
8. **浏览器保持打开**，检查无误后按 **Enter** 退出

---

## 技术栈

| 技术 | 用途 |
|------|------|
| **Python** | 主语言，异步 I/O（asyncio） |
| **Playwright** | 浏览器自动化引擎，驱动 Chromium 实现页面导航、元素定位、点击、键盘输入 |
| **httpx** | 异步 HTTP 客户端，调用 DeepSeek Chat Completions API |
| **fontTools** | 解析超星自定义字体（font-cxsecret），构建乱码→真实字符的映射表 |
| **DeepSeek API** | 大语言模型，根据题目内容推理并返回正确答案 |

### 为什么选择这些技术

- **Playwright vs Selenium**：Playwright 原生支持异步、自动等待元素、iframe 管理更简洁，且内置 Chromium 无需额外驱动
- **httpx vs requests**：httpx 原生支持 async/await，与 Playwright 的异步模型一致
- **fontTools vs OCR**：超星使用字形替换加密（glyph name 编码原始字符的 Unicode），fontTools 直接解析字体文件获取码点映射，比 OCR 截图识别更准确更快

---

## 实现原理

### 整体架构

```
用户配置 → 浏览器导航 → iframe 定位 → 字体解密 → 题目提取
    → AI 分批作答 → 答案解析 → 自动填入 → 提交 → 人工复核
```

### 1. 页面导航与 iframe 定位

超星课程页面使用多层 iframe 嵌套结构。脚本的处理流程：

1. 使用 `page.goto()` 加载目标 URL（`domcontentloaded` 策略，避免 `networkidle` 被后台轮询卡住）
2. 检测是否被重定向到登录页（Cookie 过期），若是则等待手动登录并自动保存新 Cookie
3. 遍历所有 iframe 查找包含 `doHomeWorkNew` 的作业内容 iframe
4. 等待 `.TiMu` 元素加载完成

### 2. 字体加密解密

超星部分课程使用自定义字体 `font-cxsecret` 来混淆题目文字：将正常字符替换为私有 Unicode 区域的乱码字形。

**解密原理：**
- 从页面 `<style>` 标签中提取 base64 编码的字体文件
- 使用 `fontTools` 解析字体的 `cmap` 表（字符码点到字形名的映射）
- 字形名格式为 `uniXXXX`，其中 `XXXX` 即是**原始正确字符的 Unicode 码点**
- 构建 `{乱码字符 → 真实字符}` 的映射字典，对所有题目文字进行替换

### 3. 题目提取与题型识别

通过 JavaScript 注入到 iframe，遍历所有 `.TiMu` 元素：

- **题型判断**：标题中的标记（`【单选】`、`【多选】`、`【判断】`、`【填空】`）+ DOM 结构（`li[onclick="addChoice"]` 的 `role` 属性）
- **选项提取**：每个 `li` 中的 `.num_option`（标签）和 `a.fl.after`（选项文本）
- **填空检测**：查找 `textarea`、`input[type="text"]` 等输入元素

### 4. AI 作答

```
题目 → 构建 Prompt → DeepSeek API → 解析回复 → 答案列表
```

**选择题 Prompt 设计：**
- System prompt 要求只返回答案字母不解释
- 每题标注题型（单选/多选/判断），列出选项
- 要求严格按 `第N题：A` 格式返回

**填空题 Prompt 设计：**
- 要求返回简短文字答案
- 多空答案用中文逗号分隔（如 `频率，带宽`）
- 正则解析时自动按分隔符拆分并匹配多个空

**容错机制：**
- API 调用失败时该批次答案全部标记为 `?`，继续处理后续题目
- 多种正则模式匹配 AI 回复格式，适应不同回复风格

### 5. 答案填入

**选择题：**
- Playwright 定位 `li[onclick*="addChoice"]` 元素并点击
- 多选题逐字母点击（如 `ABD` → 点 A、点 B、点 D）
- 失败时 fallback 到 JS 直接触发 `click()` 事件

**填空题（关键难点）：**

超星使用 **百度 UEditor** 富文本编辑器，textarea 是隐藏的数据容器，需要直接操作编辑器实例：

1. 通过 `UE.getEditor(textareaId)` 获取 UEditor 实例
2. 调用 `editor.setContent(text)` 设置内容
3. 调用 `editor.sync()` 同步到 textarea（确保提交时数据被读取）
4. 多空题：先按分隔符拆分 AI 答案，再将每个词填入对应的编辑器实例

### 6. 提交

- 多选择器定位提交按钮并点击
- 处理 layui 弹窗确认（CSS 选择器 + 关键字匹配双保险）

---

## 项目结构

```
web work/
├── chaoxing_ai_answer.py    # 主脚本（全部逻辑）
├── chaoxing_cookies.json     # 登录 Cookie（自动生成，.gitignore 已排除）
├── requirements.txt          # Python 依赖
├── README.md                 # 本文件
└── .gitignore                # Git 忽略规则
```

---

## 常见问题

### Q: Cookie 过期了怎么办？

脚本会自动检测登录页跳转并提示。在打开的浏览器中重新登录，回到终端按 Enter 即可，新 Cookie 会自动保存。

### Q: 题目识别不全或识别错误？

先运行 `--mode analyze` 查看页面 DOM 结构。如果页面改版导致 `.TiMu` 选择器失效，需要根据分析结果调整 `extract_questions` 中的选择器。

### Q: 填空题内容消失了？

超星使用 UEditor 富文本编辑器，直接操作 textarea 无效。脚本已通过 `UE.getEditor().setContent()` 适配。如果仍失效，说明页面可能更换了编辑器，需重新探测。

### Q: AI 回答错误怎么办？

脚本使用 `temperature=0.1` 低温度参数以提高确定性。如仍有错误，可在 `build_prompt` 中调整提示词，或更换更强的模型（修改 `DEEPSEEK_MODEL`）。

### Q: 支持其他 AI API 吗？

支持所有兼容 OpenAI Chat Completions 接口的 API。设置 `DEEPSEEK_BASE_URL` 环境变量指向你的 API 地址即可（如 Ollama：`http://localhost:11434/v1`）。
