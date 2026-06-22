"""
超星学习通 考试自动答题脚本
============================
用法:
  python chaoxing_exam_answer.py --mode analyze   # 分析考试页面结构
  python chaoxing_exam_answer.py --mode answer    # 自动答题（不自动交卷）

与章节作业脚本的区别:
  - 考试页面无iframe，题目在主页面直接渲染
  - 题目容器: .questionLi.singleQuesId
  - 选项: div.answerBg (onclick="saveSingleSelect")
  - 不自动提交，答题完成后保留浏览器页面
"""

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── 配置 ─────────────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")  # 在此填入你的API Key 或设置环境变量
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = "deepseek-v4-pro"
COOKIE_FILE = Path(__file__).parent / "chaoxing_cookies.json"

# 默认考试URL（可通过 --url 参数覆盖）
EXAM_URL = ""  # 在此填入考试URL 或通过 --url 参数传入


@dataclass
class Question:
    qtype: str          # "single", "multiple", "judge", "short_answer"
    title: str
    options: list       # [{"label": "A", "text": "..."}, ...]
    question_id: str    # 题目ID（如 "885908821"）
    container_index: int
    section: str        # "单选题", "判断题", "简答题" 等


# ── AI 客户端 ────────────────────────────────────────────

class DeepSeekClient:
    async def ask(self, prompt: str) -> str:
        import httpx
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": "你是精准的答题助手，只返回答案不解释。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1, "max_tokens": 4000,
        }
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    async def answer_choice_questions(self, questions: list[Question]) -> list[str]:
        """选择题/判断题的AI作答"""
        prompt = self._build_choice_prompt(questions)
        print(f"\n[AI] 发送 {len(questions)} 道选择/判断题给 {DEEPSEEK_MODEL}...")
        t0 = time.time()
        raw = await self.ask(prompt)
        print(f"[AI] {time.time()-t0:.1f}s")
        print(f"[AI] 回复:\n{raw[:800]}")
        answers = self._parse_letter_answers(raw, len(questions))
        print(f"[AI] 解析: {answers}")
        return answers

    async def answer_short_questions(self, questions: list[Question]) -> list[str]:
        """简答题的AI作答"""
        prompt = self._build_short_prompt(questions)
        print(f"\n[AI] 发送 {len(questions)} 道简答题给 {DEEPSEEK_MODEL}...")
        t0 = time.time()
        raw = await self.ask(prompt)
        print(f"[AI] {time.time()-t0:.1f}s")
        print(f"[AI] 回复:\n{raw[:1200]}")
        answers = self._parse_text_answers(raw, len(questions))
        print(f"[AI] 解析: {answers}")
        return answers

    def _build_choice_prompt(self, questions: list[Question]) -> str:
        lines = ["你是学习助手。请回答以下题目，每题只返回答案字母。"]
        lines.append("单选返回单字母(A), 多选返回多字母(ABD), 判断A=对/B=错。")
        lines.append("注意：部分文字可能显示乱码，请根据上下文和专业知识推断。\n")
        for i, q in enumerate(questions, 1):
            tag = {"single": "单选", "multiple": "多选", "judge": "判断"}.get(q.qtype, "?")
            lines.append(f"第{i}题 [{tag}] {q.title}")
            for o in q.options:
                lines.append(f"  {o['label']}. {o['text']}")
            lines.append("")
        lines.append("请返回（每题一行）：\n第1题：A\n第2题：BC")
        return "\n".join(lines)

    def _build_short_prompt(self, questions: list[Question]) -> str:
        lines = ["你是学习助手，精通自然语言处理和机器学习。请回答以下简答题。"]
        lines.append("每题直接返回答案内容（简短回答即可），不要解释，不要写'答案是'。\n")
        for i, q in enumerate(questions, 1):
            lines.append(f"第{i}题 {q.title}")
            lines.append("")
        lines.append("请严格按以下格式返回（每题一行）：\n第1题：答案\n第2题：答案")
        return "\n".join(lines)

    def _parse_letter_answers(self, raw: str, count: int) -> list[str]:
        answers = []
        for i in range(1, count + 1):
            found = None
            for pat in [
                rf"第{i}题[：:]\s*([^\n]+)",
                rf"{i}[\.\、]\s*([^\n]+)",
                rf"^{i}\s+([A-Z对错√×]+)",
            ]:
                m = re.search(pat, raw, re.MULTILINE | re.IGNORECASE)
                if m:
                    found = m.group(1).strip().upper().rstrip(".。")
                    break
            answers.append(found if found else "?")
        return answers

    def _parse_text_answers(self, raw: str, count: int) -> list[str]:
        answers = []
        for i in range(1, count + 1):
            found = None
            for pat in [
                rf"第{i}题[：:]\s*(.+?)(?:\n|$)",
                rf"{i}[\.\、]\s*(.+?)(?:\n|$)",
                rf"^{i}\s+(.+?)(?:\n|$)",
            ]:
                m = re.search(pat, raw, re.MULTILINE | re.IGNORECASE)
                if m:
                    found = m.group(1).strip().rstrip(".。,，、！!；;：:")
                    break
            answers.append(found if found else "?")
        return answers


# ── Cookie 管理 ──────────────────────────────────────────

async def load_cookies(context):
    if COOKIE_FILE.exists():
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            await context.add_cookies(json.load(f))
        print("[Cookie] 已加载")
        return True
    return False


async def save_cookies(context):
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(await context.cookies(), f, ensure_ascii=False, indent=2)
    print("[Save] Cookie 已保存")


# ── 字体解密 ─────────────────────────────────────────────

def build_font_mapping(font_base64: str) -> dict:
    """解析超星 font-cxsecret 字体，构建 {乱码字符: 真实字符} 映射"""
    from fontTools.ttLib import TTFont
    import base64
    import io

    b64 = font_base64
    if "base64," in b64:
        b64 = b64.split("base64,")[1]
    b64 = b64.strip().strip("'").strip('"')

    font_data = base64.b64decode(b64)
    font = TTFont(io.BytesIO(font_data))
    cmap = font.getBestCmap()

    mapping = {}
    for codepoint, glyph_name in cmap.items():
        if glyph_name.startswith("uni") and len(glyph_name) == 7:
            try:
                real_char = chr(int(glyph_name[3:], 16))
                garbled_char = chr(codepoint)
                mapping[garbled_char] = real_char
            except (ValueError, OverflowError):
                pass
        elif glyph_name.startswith("u") and len(glyph_name) > 4:
            try:
                real_char = chr(int(glyph_name[1:], 16))
                garbled_char = chr(codepoint)
                mapping[garbled_char] = real_char
            except (ValueError, OverflowError):
                pass

    font.close()
    return mapping


def decrypt_text(text: str, mapping: dict) -> str:
    if not mapping:
        return text
    return "".join(mapping.get(c, c) for c in text)


async def get_font_mapping(page) -> dict:
    """从页面 CSS 中提取并解析 font-cxsecret 字体"""
    font_css = await page.evaluate("""
    (() => {
        const styles = document.querySelectorAll('style');
        for (const s of styles) {
            const txt = s.textContent || '';
            const m = txt.match(/url\\('[^']*base64,[^']*'\\)/);
            if (m) return m[0].replace(/^url\\('/, '').replace(/'\\)$/, '');
        }
        return '';
    })()
    """)

    if font_css:
        try:
            print(f"  [Font] 提取到加密字体 ({len(font_css)} 字节), 解析中...")
            mapping = build_font_mapping(font_css)
            print(f"  [Font] 解密映射: {len(mapping)} 个字符")
            if mapping:
                test_chars = list(mapping.keys())[:3]
                for c in test_chars:
                    print(f"    '{c}' (U+{ord(c):04X}) -> '{mapping[c]}' (U+{ord(mapping[c]):04X})")
            return mapping
        except Exception as e:
            print(f"  [WARN] 字体解析失败: {e}")

    print("  [Font] 未找到加密字体，可能此页面不使用字体加密")
    return {}


# ── 页面导航 ─────────────────────────────────────────────

async def navigate_to_exam(page, exam_url: str):
    """导航到考试页面。考试页面结构简单，无iframe嵌套。"""
    print(f"  [Nav] 正在加载考试页面...")

    try:
        await page.goto(exam_url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"  [Nav] goto 超时: {e}，继续等待页面渲染...")
        await asyncio.sleep(8)

    await asyncio.sleep(3)
    current_url = page.url
    print(f"  [Nav] 当前页面: {current_url[:150]}")

    # 检测是否被重定向到登录页
    if "passport" in current_url or "login" in current_url.lower():
        print("\n" + "=" * 60)
        print("[AUTH] Cookie 已过期，请在弹出的浏览器中手动登录")
        print("[AUTH] 登录完成后会自动继续（最多等待 5 分钟）...")
        print("=" * 60 + "\n")
        try:
            await page.wait_for_url(
                lambda url: "passport" not in url and "login" not in url.lower(),
                timeout=300000
            )
            print("[AUTH] 登录成功！")
            await asyncio.sleep(3)
            await save_cookies(page.context)
            await asyncio.sleep(2)
        except Exception as e:
            print(f"[AUTH] 登录等待超时: {e}")
            print("[AUTH] 浏览器将保持打开，请手动登录后重新运行脚本")
            return False

    # 等待题目出现（增大超时）
    try:
        await page.wait_for_selector(".questionLi", timeout=60000)
        print("  [Nav] 考试题目已加载 (.questionLi)")
    except Exception:
        print("  [WARN] 未检测到 .questionLi，等待 10 秒后继续尝试...")
        await asyncio.sleep(10)

    return True


# ── 题目提取 ─────────────────────────────────────────────

async def extract_questions(page, font_map: dict = None) -> list[Question]:
    """从考试页面提取所有题目"""
    if font_map is None:
        font_map = {}

    raw = await page.evaluate("""
    (() => {
        const questions = [];

        // 遍历所有题目容器
        document.querySelectorAll('.questionLi').forEach((el, idx) => {
            // 题目ID
            const qid = el.getAttribute('data') || '';

            // 题型和题目文字
            const markName = el.querySelector('h3.mark_name');
            let title = '';
            let qtype = 'single';

            if (markName) {
                // 获取完整题目文本（去掉题号和题型标签）
                const typeSpan = markName.querySelector('.colorShallow');
                let typeText = typeSpan ? typeSpan.textContent.trim() : '';
                // 例如: "(单选题, 5.0分)" 或 "(判断题, 5.0分)" 或 "(简答题, 7.5分)"
                if (typeText.includes('单选')) qtype = 'single';
                else if (typeText.includes('多选')) qtype = 'multiple';
                else if (typeText.includes('判断')) qtype = 'judge';
                else if (typeText.includes('简答') || typeText.includes('问答') || typeText.includes('填空')) qtype = 'short_answer';

                // 获取纯题目文字（在overflow:hidden的div中）
                const titleDiv = markName.querySelector('div[style*="overflow"]');
                if (titleDiv) {
                    title = titleDiv.textContent.trim().replace(/\\s+/g, ' ');
                } else {
                    // fallback: 克隆节点，移除题型span，取剩余文字
                    const clone = markName.cloneNode(true);
                    const ts = clone.querySelector('.colorShallow');
                    if (ts) ts.remove();
                    // 移除题号（如 "1. "）
                    const text = clone.textContent.trim().replace(/^\\d+\\.\\s*/, '').replace(/\\s+/g, ' ');
                    title = text;
                }
            }

            // 备选：从隐藏input获取题型
            if (!qtype || qtype === 'single') {
                const typeInput = el.querySelector('input[name*="typeName"]');
                if (typeInput) {
                    const tn = typeInput.value;
                    if (tn.includes('多选')) qtype = 'multiple';
                    else if (tn.includes('判断')) qtype = 'judge';
                    else if (tn.includes('简答') || tn.includes('问答')) qtype = 'short_answer';
                }
            }

            // 提取选项
            const options = [];
            const answerDivs = el.querySelectorAll('.answerBg');
            answerDivs.forEach(div => {
                const numSpan = div.querySelector('.num_option');
                const textDiv = div.querySelector('.answer_p');
                if (numSpan) {
                    options.push({
                        label: (numSpan.getAttribute('data') || numSpan.textContent).trim(),
                        text: textDiv ? textDiv.textContent.trim().replace(/\\s+/g, ' ') : '',
                    });
                }
            });

            // 判断题特殊处理：如果没有提取到选项，补上"对/错"
            if (options.length === 0 && qtype === 'judge') {
                options.push({label: 'A', text: '对'}, {label: 'B', text: '错'});
            }

            if (title || options.length > 0 || qtype === 'short_answer') {
                questions.push({
                    idx,
                    qid,
                    qtype,
                    title,
                    options,
                });
            }
        });

        // 获取section标题信息（用于context）
        const sections = [];
        document.querySelectorAll('.mark_table .type_tit').forEach(el => {
            sections.push(el.textContent.trim().replace(/\\s+/g, ' '));
        });

        // 获取提交按钮信息
        const buttons = [];
        document.querySelectorAll('a.completeBtn, a.subBack, .savebtndiv a').forEach(el => {
            buttons.push({
                class: el.className?.toString()?.substring(0, 60),
                text: el.textContent.trim().replace(/\\s+/g, ' '),
            });
        });

        return JSON.stringify({questions, sections, buttons});
    })()
    """)

    data = json.loads(raw)

    print(f"  [Sections] {data.get('sections', [])}")
    for b in data.get("buttons", []):
        print(f"  [Btn] .{b['class']} -> \"{b['text']}\"")

    questions = []
    for i, item in enumerate(data.get("questions", [])):
        title = item.get("title", "")
        qtype = item.get("qtype", "single")
        qid = item.get("qid", "")

        # 解密标题
        if font_map:
            title = decrypt_text(title, font_map)

        # 解密选项
        options = []
        for o in item.get("options", []):
            text = o.get("text", "")
            if font_map:
                text = decrypt_text(text, font_map)
            options.append({"label": o.get("label", ""), "text": text})

        # 确定题型标签
        type_labels = {
            "single": "单选题", "multiple": "多选题",
            "judge": "判断题", "short_answer": "简答题",
        }
        section = type_labels.get(qtype, "未知")

        questions.append(Question(
            qtype=qtype,
            title=title,
            options=options,
            question_id=qid,
            container_index=i,
            section=section,
        ))

    return questions


# ── 答题执行 ─────────────────────────────────────────────

async def click_answer(page, question: Question, answer: str) -> bool:
    """点击对应选项或填写简答题"""
    answer = answer.strip()
    qtype = question.qtype
    qid = question.question_id

    if qtype == "short_answer":
        return await _fill_short_answer(page, question, answer)

    # 选择题/判断题: 点击 div.answerBg
    answer_upper = answer.upper()
    label_map = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5, "G": 6, "H": 7}

    if qtype == "multiple":
        ok_all = True
        for ch in answer_upper:
            if ch in label_map:
                ok = await _click_single_option(page, qid, label_map[ch])
                ok_all = ok_all and ok
                await asyncio.sleep(0.15)
        return ok_all

    # 单选/判断
    opt_idx = label_map.get(answer_upper, 0)
    return await _click_single_option(page, qid, opt_idx)


async def _click_single_option(page, qid: str, opt_idx: int) -> bool:
    """点击第 opt_idx 个选项 (.answerBg 在 .stem_answer 内，用 querySelectorAll 定位)"""
    # JS 直接点击（最可靠）
    result = await page.evaluate(f"""
    (() => {{
        const qDiv = document.querySelector('.questionLi[data="{qid}"]');
        if (!qDiv) return 'no questionLi for {qid}';
        const opts = qDiv.querySelectorAll('.answerBg');
        if (opts[{opt_idx}]) {{
            opts[{opt_idx}].click();
            return 'clicked option {opt_idx}';
        }}
        return 'no option at idx {opt_idx}, found ' + opts.length + ' options';
    }})()
    """)
    ok = "clicked" in str(result)
    if not ok:
        print(f"  [WARN] 点击失败: {result}")
    return ok


async def _fill_short_answer(page, question: Question, answer: str) -> bool:
    """填写简答题 — 激活编辑器 → 设值 → 触发保存"""
    qid = question.question_id
    idx = question.container_index
    safe_answer = json.dumps(answer, ensure_ascii=False)

    print(f"  [SHORT] 第{idx+1}题 (qid={qid}): {answer[:60]}...")

    # 第一步：点击编辑器区域激活
    await page.evaluate(f"""
    (() => {{
        const qDiv = document.querySelector('.questionLi[data="{qid}"]');
        if (!qDiv) return;
        // 点击 subEditor 或编辑器容器激活
        const sub = qDiv.querySelector('.subEditor');
        if (sub) {{ sub.click(); }}
        // 也点一下 textarea 的父级
        const ta = qDiv.querySelector('textarea');
        if (ta && ta.parentElement) {{ ta.parentElement.click(); }}
    }})()
    """)
    await asyncio.sleep(0.3)

    # 第二步：通过 UEditor API 或 fallback 设值
    fill_result = await page.evaluate(f"""
    (() => {{
        const qDiv = document.querySelector('.questionLi[data="{qid}"]');
        if (!qDiv) return 'no questionLi';

        const ta = qDiv.querySelector('textarea');
        const editorId = ta ? ta.id : '';

        // 1. 尝试 UE.getEditor
        if (typeof UE !== 'undefined' && editorId) {{
            try {{
                const editor = UE.getEditor(editorId);
                if (editor && editor.setContent) {{
                    editor.setContent({safe_answer});
                    editor.sync();
                    console.log('[ExamBot] UEditor setContent done');
                }}
            }} catch(e) {{ console.log('[ExamBot] UE error:', e); }}
        }}

        // 2. 尝试 codeEditors
        if (typeof codeEditors !== 'undefined' && codeEditors && codeEditors[editorId]) {{
            try {{
                const ed = codeEditors[editorId];
                if (ed && ed.setContent) {{
                    ed.setContent({safe_answer});
                    if (ed.sync) ed.sync();
                }}
            }} catch(e) {{}}
        }}

        // 3. 直接操作 textarea（兜底）
        if (ta) {{
            ta.value = {safe_answer};
            ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
            ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
            ta.dispatchEvent(new Event('blur', {{ bubbles: true }}));
        }}

        // 4. 也尝试 contentEditable 区域的 innerHTML（有些编辑器用 div）
        const editArea = qDiv.querySelector('[contenteditable="true"], .edui-editor-iframeholder');
        if (editArea) {{
            // 不做，UEditor 的 setContent 已经处理了
        }}

        return editorId ? 'done with ' + editorId : 'textarea fallback';
    }})()
    """)

    print(f"  [SHORT] 设值: {fill_result}")

    # 第三步：失焦 — 点击题目区域触发 blur，让页面保存机制生效
    await asyncio.sleep(0.3)
    await page.evaluate(f"""
    (() => {{
        const qDiv = document.querySelector('.questionLi[data="{qid}"]');
        if (!qDiv) return;
        // 点击题目标题区域来让编辑器失焦
        const title = qDiv.querySelector('h3.mark_name');
        if (title) {{
            title.click();
            return;
        }}
        // fallback: 点击 body 空白处
        document.body.click();
    }})()
    """)
    await asyncio.sleep(0.2)

    # 第四步：对 textarea 再触发一次 change（保险）
    await page.evaluate(f"""
    (() => {{
        const qDiv = document.querySelector('.questionLi[data="{qid}"]');
        if (!qDiv) return;
        const ta = qDiv.querySelector('textarea');
        if (ta) {{
            ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
            ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
    }})()
    """)

    print(f"  [SHORT] 完成 (含 blur+change 触发)")
    return True


# ── 主流程 ───────────────────────────────────────────────

async def analyze_mode(exam_url: str):
    """分析考试页面结构（浏览器不自动关闭）"""
    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=False)
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
    await load_cookies(ctx)
    page = await ctx.new_page()

    async def keep_open(msg: str = ""):
        if msg:
            print(f"\n{msg}")
        print("\n" + "=" * 60)
        print("  浏览器窗口保持打开，关闭浏览器窗口即可退出程序...")
        print("=" * 60)
        while True:
            try:
                if not browser.is_connected():
                    print("  浏览器已关闭，程序退出。")
                    break
                await asyncio.sleep(0.5)
            except Exception:
                print("  浏览器连接断开，程序退出。")
                break

    try:
        nav_ok = await navigate_to_exam(page, exam_url)
        if not nav_ok:
            await keep_open("[ERROR] 导航失败。")
            return

        await asyncio.sleep(2)

        # 探测页面详细结构
        info = await page.evaluate("""
        (() => {
            const result = {};
            const classes = new Set();
            document.querySelectorAll('[class]').forEach(e => {
                e.className.split(/\\s+/).forEach(c => classes.add(c));
            });
            result.allClasses = [...classes].sort();
            result.questionCount = document.querySelectorAll('.questionLi').length;
            const firstQ = document.querySelector('.questionLi');
            result.firstQuestionHTML = firstQ ? firstQ.outerHTML.substring(0, 3000) : '';
            result.sections = [];
            document.querySelectorAll('.type_tit').forEach(el => {
                result.sections.push(el.textContent.trim());
            });
            const submitForm = document.getElementById('submitTest');
            if (submitForm) {
                const inputs = {};
                submitForm.querySelectorAll('input[type="hidden"]').forEach(inp => {
                    inputs[inp.name || inp.id] = inp.value;
                });
                result.submitFormInputs = inputs;
            }
            const buttons = [];
            document.querySelectorAll('a.completeBtn, a.subBack, .savebtndiv a').forEach(el => {
                buttons.push({ html: el.outerHTML.substring(0, 300), text: el.textContent.trim() });
            });
            result.buttons = buttons;
            const editors = [];
            document.querySelectorAll('.subEditor, textarea').forEach(el => {
                editors.push({ tag: el.tagName, id: el.id, class: el.className?.toString()?.substring(0, 80) });
            });
            result.editors = editors;
            return JSON.stringify(result);
        })()
        """)

        data = json.loads(info)
        print(f"\n{'='*60}")
        print(f"  考试页面结构分析")
        print(f"{'='*60}")
        print(f"  题目总数: {data.get('questionCount', 0)}")
        print(f"  Sections: {data.get('sections', [])}")
        print(f"  按钮: {[b['text'] for b in data.get('buttons', [])]}")
        print(f"  编辑器: {data.get('editors', [])}")
        print(f"\n  第一题 HTML:")
        print(f"  {data.get('firstQuestionHTML', 'N/A')[:2000]}")
        print(f"\n  提交表单 hidden inputs:")
        for k, v in data.get('submitFormInputs', {}).items():
            print(f"    {k} = {v}")

        await keep_open("[Done] 结构分析完成。")

    except Exception as e:
        print(f"\n[FATAL] 错误: {e}")
        import traceback
        traceback.print_exc()
        await keep_open("[ERROR] 脚本异常退出。")
    finally:
        try:
            await p.stop()
        except Exception:
            pass


async def answer_mode(exam_url: str):
    """自动答题模式（不自动交卷，浏览器不自动关闭）"""
    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=False)
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
    await load_cookies(ctx)
    page = await ctx.new_page()

    async def keep_browser_open(msg: str = ""):
        """保持浏览器打开直到用户手动关闭窗口"""
        if msg:
            print(f"\n{msg}")
        print("\n" + "=" * 60)
        print("  浏览器窗口保持打开，关闭浏览器窗口即可退出程序...")
        print("=" * 60)
        # 轮询检测浏览器是否还活着
        while True:
            try:
                if not browser.is_connected():
                    print("  浏览器已关闭，程序退出。")
                    break
                await asyncio.sleep(0.5)
            except Exception:
                print("  浏览器连接断开，程序退出。")
                break

    try:
        # 导航
        nav_ok = await navigate_to_exam(page, exam_url)
        if not nav_ok:
            await keep_browser_open("[ERROR] 导航失败，浏览器保持打开以便排查。")
            return

        # 字体解密
        font_map = await get_font_mapping(page)

        # 提取题目
        questions = await extract_questions(page, font_map)

        # 分类统计
        type_counts = {}
        for q in questions:
            type_counts[q.qtype] = type_counts.get(q.qtype, 0) + 1
        print(f"\n[Extract] 共 {len(questions)} 题 | {type_counts}")

        if not questions:
            await keep_browser_open("[ERROR] 未提取到任何题目！可能页面结构有变化，请手动排查。")
            return

        # ── 打印所有题目到终端 ──
        for i, q in enumerate(questions):
            print(f"\n{'─'*55}")
            print(f" 第{i+1}题 [{q.section}] ID={q.question_id}")
            print(f"   题干: {q.title[:200]}")
            for o in q.options:
                print(f"     {o['label']}. {o['text'][:150]}")
        print(f"{'─'*55}\n")

        # 分类处理
        choice_qs = [q for q in questions if q.qtype in ("single", "multiple", "judge")]
        short_qs = [q for q in questions if q.qtype == "short_answer"]

        client = DeepSeekClient()
        BATCH = 20

        # ── 选择题/判断题 ──
        choice_answers = []
        if choice_qs:
            print(f"\n[AI] 处理 {len(choice_qs)} 道选择/判断题...")
            for start in range(0, len(choice_qs), BATCH):
                batch = choice_qs[start:start + BATCH]
                try:
                    ans = await client.answer_choice_questions(batch)
                    choice_answers.extend(ans)
                except Exception as e:
                    print(f"  [ERROR] AI 调用失败: {e}")
                    choice_answers.extend(["?"] * len(batch))
                if start + BATCH < len(choice_qs):
                    await asyncio.sleep(1)

        # ── 简答题 ──
        short_answers = []
        if short_qs:
            print(f"\n[AI] 处理 {len(short_qs)} 道简答题...")
            for start in range(0, len(short_qs), BATCH):
                batch = short_qs[start:start + BATCH]
                try:
                    ans = await client.answer_short_questions(batch)
                    short_answers.extend(ans)
                except Exception as e:
                    print(f"  [ERROR] AI 调用失败: {e}")
                    short_answers.extend(["?"] * len(batch))
                if start + BATCH < len(short_qs):
                    await asyncio.sleep(1)

        # ── 执行答题 ──
        print(f"\n[Action] 开始填入答案...")
        print(f"  选择题答案: {len(choice_answers)} 个")
        print(f"  简答题答案: {len(short_answers)} 个")

        # 点击选择题
        for i, (q, ans) in enumerate(zip(choice_qs, choice_answers)):
            ans_display = ans if ans != "?" else "? (AI未返回)"
            try:
                ok = await click_answer(page, q, ans)
                status = "✓" if ok else "✗"
            except Exception as e:
                status = "✗"
                print(f"  [ERR] 第{q.container_index+1}题 点击失败: {e}")
            print(f"  [{status}] 第{q.container_index+1}题 [{q.section}] -> {ans_display}")
            await asyncio.sleep(0.25)
            if (i + 1) % 10 == 0 and i + 1 < len(choice_qs):
                print(f"  ... 已完成 {i+1}/{len(choice_qs)} 选择/判断题")

        # 填写简答题
        for i, (q, ans) in enumerate(zip(short_qs, short_answers)):
            ans_display = ans[:50] + "..." if len(ans) > 50 else ans
            try:
                ok = await click_answer(page, q, ans)
                status = "✓" if ok else "✗"
            except Exception as e:
                status = "✗"
                print(f"  [ERR] 简答第{q.container_index+1}题 填写失败: {e}")
            print(f"  [{status}] 第{q.container_index+1}题 [简答题] -> {ans_display}")
            await asyncio.sleep(0.5)
            if (i + 1) % 5 == 0 and i + 1 < len(short_qs):
                print(f"  ... 已完成 {i+1}/{len(short_qs)} 简答题")

        # ── 完成，不提交 ──
        print(f"\n{'='*60}")
        print(f"  [Done] 所有题目已完成作答！")

        # 自动保存进度（不交卷，只点击"保存"按钮）
        print(f"  [Save] 正在保存答题进度...")
        try:
            save_result = await page.evaluate("""
            (() => {
                const saveBtns = document.querySelectorAll('.savebtndiv a, a.saveButtonClass');
                for (const btn of saveBtns) {
                    if (btn.textContent.includes('保存') || btn.className.includes('save')) {
                        btn.click();
                        return 'clicked save: ' + btn.textContent.trim().substring(0, 30);
                    }
                }
                if (typeof saveTest === 'function') {
                    saveTest();
                    return 'called saveTest()';
                }
                if (typeof submitTest === 'function') {
                    return 'found submitTest but did not call (交卷)';
                }
                return 'no save button found';
            })()
            """)
            print(f"  [Save] {save_result}")
        except Exception as e:
            print(f"  [Save] 保存失败: {e}")

        print(f"  [INFO] 未自动交卷，请手动检查答案后点击'交卷'按钮")
        await keep_browser_open("[Done] 答题完成！")

    except Exception as e:
        print(f"\n[FATAL] 发生未预期错误: {e}")
        import traceback
        traceback.print_exc()
        await keep_browser_open("[ERROR] 脚本异常退出，浏览器保持打开。")
    finally:
        try:
            await p.stop()
        except Exception:
            pass


# ── 入口 ─────────────────────────────────────────────────

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="超星学习通 考试 AI 答题助手")
    parser.add_argument("--mode", choices=["analyze", "answer"], default="analyze",
                        help="analyze=分析页面结构, answer=自动答题")
    parser.add_argument("--url", type=str, default="",
                        help="考试页面完整URL（不填则用脚本内置的默认URL）")
    args = parser.parse_args()

    target_url = args.url if args.url else EXAM_URL
    if not target_url:
        print("[ERROR] 请指定考试URL！")
        print("  方式一: python chaoxing_exam_answer.py --url \"考试页面完整URL\" --mode answer")
        print("  方式二: 编辑脚本中的 EXAM_URL 变量")
        return
    print(f"[Config] 目标URL: {target_url[:120]}...")
    print(f"[Config] 模式: {args.mode}")

    if args.mode == "analyze":
        await analyze_mode(target_url)
    elif args.mode == "answer":
        await answer_mode(target_url)


if __name__ == "__main__":
    asyncio.run(main())
