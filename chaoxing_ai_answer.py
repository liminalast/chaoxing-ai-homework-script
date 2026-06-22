"""
超星学习通 AI 自动答题脚本 (v3)
===============================
用法:
  python chaoxing_ai_answer.py --mode analyze   # 分析 HTML 结构
  python chaoxing_ai_answer.py --mode single    # 单题测试
  python chaoxing_ai_answer.py --mode answer    # 全部自动答题
"""

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── 配置 ─────────────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")  # 在此填入你的API Key 或设置环境变量
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = "deepseek-v4-pro"
COOKIE_FILE = Path(__file__).parent / "chaoxing_cookies.json"
TARGET_URL = ""  # 在此填入章节URL 或通过 --url 参数传入
@dataclass
class Question:
    qtype: str
    title: str
    options: list      # [{"label": "A", "text": "..."}, ...]
    container_idx: int


# ── 工具函数 ─────────────────────────────────────────────

def build_prompt(questions: list[Question]) -> str:
    """选择题/判断题的提示词"""
    lines = ["你是学习助手。请回答以下题目，每题只返回答案字母。"]
    lines.append("单选返回单字母(A), 多选返回多字母(ABD), 判断A=对/B=错。")
    lines.append("注意：部分文字因字体加密显示乱码，请根据上下文和专业知识推断。\n")
    for i, q in enumerate(questions, 1):
        tag = {"single": "单选", "multiple": "多选", "judge": "判断"}.get(q.qtype, "?")
        lines.append(f"第{i}题 [{tag}] {q.title}")
        for o in q.options:
            lines.append(f"  {o['label']}. {o['text']}")
        lines.append("")
    lines.append("请返回（每题一行）：\n第1题：A\n第2题：BC")
    return "\n".join(lines)


def parse_ai_answer(raw: str, count: int) -> list[str]:
    """解析选择题/判断题的字母答案"""
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


def build_fill_prompt(questions: list[Question]) -> str:
    """填空题的提示词：要求返回文字答案而非字母"""
    lines = ["你是学习助手，精通语音识别和机器学习。请回答以下填空题。"]
    lines.append("每题直接返回答案内容（简短词语或短语），不要解释，不要写'答案是'。\n")
    for i, q in enumerate(questions, 1):
        lines.append(f"第{i}题 {q.title}")
        lines.append("")
    lines.append("请严格按以下格式返回（每题一行）：\n第1题：答案\n第2题：答案")
    return "\n".join(lines)


def parse_fill_answer(raw: str, count: int) -> list[str]:
    """解析填空题的文字答案"""
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


# ── Cookie ───────────────────────────────────────────────
async def load_cookies(context):
    if COOKIE_FILE.exists():
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            await context.add_cookies(json.load(f))
        print(f"[Cookie] 已加载")
        return True
    return False


async def save_cookies(context):
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(await context.cookies(), f, ensure_ascii=False, indent=2)
    print("[Save] Cookie 已保存")


# ── 字体解密 ─────────────────────────────────────────────

def build_font_mapping(font_base64: str) -> dict:
    """解析超星 font-cxsecret 字体，构建 {乱码字符: 真实字符} 映射。
    原理：字体 cmap 表中的 glyph name 格式为 'uniXXXX'，
    其中 XXXX 是原始字符的 Unicode 码点。
    """
    from fontTools.ttLib import TTFont
    import base64, io

    # 去掉 CSS data URL 前缀
    b64 = font_base64
    if "base64," in b64:
        b64 = b64.split("base64,")[1]
    b64 = b64.strip().strip("'").strip('"')

    font_data = base64.b64decode(b64)
    font = TTFont(io.BytesIO(font_data))
    cmap = font.getBestCmap()  # {codepoint: glyphName}

    mapping = {}
    for codepoint, glyph_name in cmap.items():
        # glyph name 格式: uniXXXX 或 uXXXXX
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
    """使用字体映射解密文本"""
    if not mapping:
        return text
    return "".join(mapping.get(c, c) for c in text)


async def get_font_mapping(frame) -> dict:
    """从页面 CSS 中提取并解析 font-cxsecret 字体"""
    font_css = await frame.evaluate("""
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
            # 测试
            if mapping:
                test_chars = list(mapping.keys())[:3]
                for c in test_chars:
                    print(f"    '{c}' (U+{ord(c):04X}) -> '{mapping[c]}' (U+{ord(mapping[c]):04X})")
            return mapping
        except Exception as e:
            print(f"  [WARN] 字体解析失败: {e}")

    print("  [Font] 未找到加密字体，可能此页面不使用字体加密")
    return {}


# ── 导航 ─────────────────────────────────────────────────
async def navigate_to_exam(page):
    """导航到考试页面，返回内容 iframe"""
    print(f"  [Nav] 正在加载: {TARGET_URL[:100]}...")
    try:
        # 用 domcontentloaded 代替 networkidle，避免超星后台轮询导致超时
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"  [Nav] goto 超时/失败: {e}，继续等待页面渲染...")
        await asyncio.sleep(5)

    # 等待页面充分渲染
    await asyncio.sleep(2)

    # 检查是否被重定向到登录页
    current_url = page.url
    print(f"  [Nav] 当前页面: {current_url[:120]}")
    if "passport" in current_url or "login" in current_url.lower():
        print("  [WARN] 检测到登录页面！Cookie 可能已过期，请重新登录。")
        print("  请在浏览器中手动登录，登录完成后按 Enter 继续...")
        input()
        await save_cookies(page.context)
        print("  [Nav] Cookie 已更新，重新加载页面...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

    # 打印所有 iframe 方便调试
    all_frames = page.frames
    print(f"  [Nav] 页面共有 {len(all_frames)} 个 frame:")
    for i, fr in enumerate(all_frames):
        print(f"    frame[{i}]: name={fr.name!r}  url={fr.url[:100] if fr.url else '(empty)'}")

    # 等待作业 iframe 出现（放宽匹配条件）
    iframe_found = False
    for sel in ['iframe[src*="/work/"]', 'iframe[src*="doHomeWorkNew"]', 'iframe[id*="frame"]']:
        try:
            await page.wait_for_selector(sel, timeout=10000)
            print(f"  [Nav] 通过选择器 '{sel}' 找到了 iframe")
            iframe_found = True
            break
        except Exception:
            continue

    if not iframe_found:
        print("  [Nav] 等待 5 秒后重试...")
        await asyncio.sleep(5)

    # 优先通过 name 获取 frame_content
    f = page.frame(name="frame_content")
    if f and f.url and "doHomeWorkNew" in f.url:
        print(f"  [Nav] 内容 iframe (by name): {f.url[:120]}")
        try:
            await f.wait_for_function(
                "() => document.querySelectorAll('.TiMu').length > 0",
                timeout=30000)
            n = await f.evaluate("() => document.querySelectorAll('.TiMu').length")
            print(f"  [Nav] 发现 {n} 个 .TiMu")
        except Exception as e:
            print(f"  [WARN] 等待 .TiMu 超时: {e}")
        return f

    # fallback: 遍历所有 frame 找作业页面
    for fr in page.frames:
        if fr.url and "doHomeWorkNew" in fr.url:
            print(f"  [Nav] 内容 iframe (by url): {fr.url[:120]}")
            return fr
        if fr.url and "/work/" in fr.url:
            print(f"  [Nav] 作业 iframe (by /work/): {fr.url[:120]}")
            if fr.child_frames:
                cf = fr.child_frames[0]
                print(f"  [Nav] 子 iframe: {cf.url[:120]}")
                return cf
            return fr

    # 最后尝试：等页面完全加载后再找
    print("  [Nav] 未找到 iframe，等待 8 秒后最后尝试...")
    await asyncio.sleep(8)
    for fr in page.frames:
        if fr.url and ("doHomeWorkNew" in fr.url or "/work/" in fr.url or "knowledge/cards" in fr.url):
            print(f"  [Nav] 延迟发现 iframe: {fr.url[:120]}")
            return fr

    print("  [WARN] 未找到内容 iframe，浏览器将保持打开以便排查。")
    print("  请检查浏览器页面状态，按 Enter 继续(会关浏览器)...")
    input()
    return None


# ── 题目提取 ─────────────────────────────────────────────
async def extract_questions(frame, font_map: dict = None) -> list[Question]:
    """提取所有题目，用字体映射解密文字。
    题型检测:
      - li[onclick*="addChoice"] + radio → 单选/多选/判断
      - input/textarea/.blankItemDiv → 填空
    """
    if font_map is None:
        font_map = {}

    raw = await frame.evaluate("""
    (() => {
        const qs = [];
        document.querySelectorAll('.TiMu').forEach((el, idx) => {
            const tDiv = el.querySelector('.Zy_TItle .font-cxsecret, .Zy_TItle .fontLabel');
            let title = tDiv ? tDiv.textContent.trim().replace(/\\s+/g, ' ') : '';

            let qtype = 'single';
            if (title.includes('【多选')) qtype = 'multiple';
            else if (title.includes('【判断')) qtype = 'judge';
            else if (title.includes('【填空')) qtype = 'fill';

            title = title.replace(/【[^】]*】/g, '').trim();

            const opts = [];
            const choiceLis = el.querySelectorAll('li[onclick*="addChoice"]');

            if (choiceLis.length > 0) {
                // 选择题
                choiceLis.forEach((li, oi) => {
                    const num = li.querySelector('.num_option');
                    const txt = li.querySelector('a.fl.after, a.after');
                    opts.push({
                        label: num ? num.textContent.trim() : String.fromCharCode(65+oi),
                        text: txt ? txt.textContent.trim().replace(/\\s+/g, ' ') : ''
                    });
                });
                if (qtype === 'judge' && opts.length === 0) {
                    opts.push({label:'A',text:'对'},{label:'B',text:'错'});
                }
                // 根据 role 属性修正题型
                const firstLi = choiceLis[0];
                if (firstLi && firstLi.getAttribute('role') === 'radio') qtype = qtype === 'judge' ? 'judge' : 'single';
                else if (firstLi && firstLi.getAttribute('role') === 'checkbox') qtype = 'multiple';
            } else {
                // 检查是否是填空题
                const hasInput = !!el.querySelector('input[type="text"], textarea, .blankItemDiv, .tiankong');
                if (hasInput || title.includes('【填空')) {
                    qtype = 'fill';
                }
            }

            if (title || opts.length || qtype === 'fill') {
                qs.push({idx, qtype, title, options: opts.slice(0, 10)});
            }
        });
        const btns = [];
        document.querySelectorAll('.btnSubmit, .btnSave').forEach(el => {
            btns.push({cls:el.className?.toString()?.substring(0,60), text:el.textContent.trim().replace(/\\s+/g,' ')});
        });
        return {questions:qs, buttons:btns};
    })()
    """)

    for b in raw.get("buttons", []):
        print(f"  [Btn] .{b['cls']} -> \"{b['text']}\"")

    questions = []
    for it in raw.get("questions", []):
        title = it.get("title", "")
        qtype = it.get("qtype", "single")

        # 解密标题（如果有映射）
        if font_map:
            title = decrypt_text(title, font_map)

        # 解密选项
        options = []
        for o in it.get("options", []):
            text = o.get("text", "")
            if font_map:
                text = decrypt_text(text, font_map)
            options.append({"label": o.get("label", ""), "text": text})

        questions.append(Question(
            qtype=qtype,
            title=title,
            options=options,
            container_idx=it.get("idx", 0),
        ))

    return questions


# ── DeepSeek ─────────────────────────────────────────────
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

    async def answer_questions(self, questions: list[Question]) -> list[str]:
        prompt = build_prompt(questions)
        print(f"\n[AI] 发送 {len(questions)} 题给 {DEEPSEEK_MODEL}...")
        t0 = time.time()
        raw = await self.ask(prompt)
        print(f"[AI] {time.time()-t0:.1f}s")
        print(f"[AI] 回复:\n{raw[:800]}")
        answers = parse_ai_answer(raw, len(questions))
        print(f"[AI] 解析: {answers}")
        return answers

    async def answer_fill_questions(self, questions: list[Question]) -> list[str]:
        prompt = build_fill_prompt(questions)
        print(f"\n[AI] 发送 {len(questions)} 道填空题给 {DEEPSEEK_MODEL}...")
        t0 = time.time()
        raw = await self.ask(prompt)
        print(f"[AI] {time.time()-t0:.1f}s")
        print(f"[AI] 回复:\n{raw[:1200]}")
        answers = parse_fill_answer(raw, len(questions))
        print(f"[AI] 解析: {answers}")
        return answers


# ── 答题执行 ─────────────────────────────────────────────
async def click_option(frame, question: Question, answer: str):
    """点击对应选项或填写填空"""
    answer = answer.strip()
    idx = question.container_idx
    qtype = question.qtype

    if qtype == "fill":
        return await _fill_answer(frame, idx, answer)

    # 选择题
    answer_upper = answer.upper()
    label_idx = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5, "G": 6, "H": 7}
    opt_idx = label_idx.get(answer_upper, 0)

    # 多选题：逐个字母点击
    if qtype == "multiple":
        ok_all = True
        for ch in answer_upper:
            if ch in label_idx:
                ok = await _click_single(frame, idx, label_idx[ch])
                ok_all = ok_all and ok
                await asyncio.sleep(0.15)
        return ok_all

    return await _click_single(frame, idx, opt_idx)


async def _fill_answer(frame, idx: int, answer: str) -> bool:
    """填空题：拆分答案到多个空，逐个输入框用键盘打字填入"""
    import json as _json

    # 按分隔符拆分答案（中文逗号、顿号、分号、英文逗号）
    parts = re.split(r'[，,、；;]\s*', answer.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        parts = [answer.strip()]

    # 第一步：JS 只找 textarea（超星用 textarea 做富文本编辑器，div.blankItemInp 是包装壳）
    info = await frame.evaluate(f"""
    (() => {{
        const tiMu = document.querySelectorAll('.TiMu')[{idx}];
        if (!tiMu) return JSON.stringify({{ok: false, why: 'no .TiMu at ' + {idx}}});

        tiMu.setAttribute('data-fill-target', String({idx}));

        // 只取 textarea，跳过 div 包装壳
        let textareas = Array.from(tiMu.querySelectorAll('textarea'));

        // 如果找不到 textarea，尝试 input[type=text]
        if (textareas.length === 0) {{
            textareas = Array.from(tiMu.querySelectorAll('input[type=\"text\"]'));
        }}

        // 打标号
        textareas.forEach((ta, i) => {{
            ta.setAttribute('data-fill-n', String(i));
        }});

        // 探测框架
        const frameworks = [];
        if (typeof window.jQuery !== 'undefined') frameworks.push('jquery');
        const allEls = document.querySelectorAll('.TiMu, input, textarea, body');
        for (const el of allEls) {{
            for (const k of Object.keys(el)) {{
                if (k.startsWith('__vue') || k.startsWith('__v_')) {{ frameworks.push('vue'); break; }}
                if (k.startsWith('__reactFiber')) {{ frameworks.push('react'); break; }}
            }}
            if (frameworks.length > 1) break;
        }}

        return JSON.stringify({{
            ok: true,
            count: textareas.length,
            framework: [...new Set(frameworks)],
        }});
    }})()
    """)

    data = _json.loads(info)
    if not data.get("ok"):
        print(f"  [FILL-FAIL] 第{idx+1}题 -> {data.get('why', '?')}")
        return False

    blank_count = data.get("count", 0)
    framework = data.get("framework", [])
    if blank_count == 0:
        print(f"  [FILL-FAIL] 第{idx+1}题 -> 找不到任何输入框 (framework={framework})")
        return False

    print(f"  [FILL] 第{idx+1}题: 框架={framework}  真实空数={blank_count}  分词={parts}")

    ok_all = True
    for n, part in enumerate(parts):
        if n >= blank_count:
            print(f"  [FILL-WARN] 第{idx+1}题 多余分词丢弃: {parts[n:]}")
            break

        safe_part = _json.dumps(part, ensure_ascii=False)
        result = await frame.evaluate(f"""
        (() => {{
            const ta = document.querySelector('[data-fill-n="{n}"]');
            if (!ta) return 'no element';

            const editorId = ta.id;

            // 1. 先点 div.blankItemInp 激活 UEditor
            const blankDiv = ta.closest('.TiMu')?.querySelector('.blankItemInp');
            if (blankDiv) blankDiv.click();

            // 2. 通过 UE.getEditor 获取编辑器实例并设值
            if (typeof UE !== 'undefined') {{
                const editor = UE.getEditor(editorId);
                if (editor && editor.setContent) {{
                    // UEditor 的 setContent 接受 HTML 字符串
                    editor.setContent({safe_part});
                    // 同步到 textarea
                    editor.sync();
                    return 'ueditor ok';
                }}
            }}

            // 3. 尝试通过全局 codeEditors map
            if (typeof codeEditors !== 'undefined' && codeEditors && codeEditors[editorId]) {{
                const ed = codeEditors[editorId];
                if (ed && ed.setContent) {{
                    ed.setContent({safe_part});
                    if (ed.sync) ed.sync();
                    return 'codeEditors ok';
                }}
            }}

            // 4. 尝试 getCodeEditorByBusinessId
            if (typeof getCodeEditorByBusinessId === 'function') {{
                const ed = getCodeEditorByBusinessId(editorId);
                if (ed && ed.setContent) {{
                    ed.setContent({safe_part});
                    if (ed.sync) ed.sync();
                    return 'byBusinessId ok';
                }}
            }}

            // 5. 最后的 fallback: 直接设 textarea 值并触发 change
            ta.value = {safe_part};
            ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
            ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
            const $ = window.jQuery || window.$;
            if ($) $(ta).trigger('change');
            return 'fallback';
        }})()
        """)
        print(f"  [{'FILL-OK' if 'ok' in str(result).lower() else 'FILL-FAIL'}] 第{idx+1}题 第{n+1}空 -> {part[:40]}  [{result}]")
        if 'no element' in str(result):
            ok_all = False
        await asyncio.sleep(0.5)

    # 清理标记
    try:
        await frame.evaluate(f"""
        (() => {{
            const ti = document.querySelector('[data-fill-target="{idx}"]');
            if (ti) {{
                ti.removeAttribute('data-fill-target');
                ti.querySelectorAll('[data-fill-n]').forEach(el => el.removeAttribute('data-fill-n'));
            }}
        }})()
        """)
    except Exception:
        pass

    return ok_all


async def _click_single(frame, tiMuIdx: int, optIdx: int) -> bool:
    """点击第 tiMuIdx 个 .TiMu 中的第 optIdx 个选项 li"""
    try:
        li = await frame.query_selector(
            f".TiMu:nth-child({tiMuIdx+1}) li[onclick*=\"addChoice\"]:nth-child({optIdx+1})")
        if li:
            await li.click(timeout=3000)
            return True
    except Exception:
        pass
    # JS fallback
    result = await frame.evaluate(f"""
    (() => {{
        const el = document.querySelectorAll('.TiMu')[{tiMuIdx}];
        if (!el) return 'no TiMu';
        const lis = el.querySelectorAll('li[onclick*="addChoice"]');
        if (lis[{optIdx}]) {{ lis[{optIdx}].click(); return 'clicked'; }}
        return 'no li at {optIdx}';
    }})()
    """)
    return "clicked" in str(result)


async def click_submit(frame, page):
    """点击提交按钮，并处理确认弹窗"""
    # 1. 点击提交按钮
    clicked = False
    for sel in [".btnSubmit", ".ZY_sub .btnSubmit", "a:has-text('提交')"]:
        try:
            el = await frame.query_selector(sel)
            if el:
                await el.click(timeout=3000)
                print(f"  [Submit] 已点击 {sel}")
                clicked = True
                break
        except Exception:
            pass
    if not clicked:
        r = await frame.evaluate("""
            (() => {
                const b = document.querySelector('.btnSubmit');
                if (b) { b.click(); return 'clicked'; }
                return 'not found';
            })()
        """)
        print(f"  [Submit] {r}")

    # 2. 等待确认弹窗并点击确认
    await asyncio.sleep(1)
    confirm_clicked = await frame.evaluate("""
    (() => {
        // 先尝试常见的确认按钮选择器
        const cssSelectors = [
            '.layui-layer-dialog .layui-layer-btn0',
            '.dialog-btn .ok',
            '.ui-dialog .btn_confirm',
            '.submitDialog .confirmBtn',
            '.popup_box .confirm',
            '.layui-layer-btn .layui-layer-btn0',
            '.btn_ok',
            '.sureBtn',
            '.dialog-footer .btn-primary',
        ];
        for (const sel of cssSelectors) {
            const el = document.querySelector(sel);
            if (el && el.offsetParent !== null) {
                el.click();
                return 'css:' + sel;
            }
        }
        // fallback: 找包含"确定/确认/是"文字的可见按钮
        const keywords = ['确', '交', '是', 'OK', 'ok'];
        const allBtns = document.querySelectorAll('a, button, .layui-layer-btn a, div[onclick], span[onclick]');
        for (const btn of allBtns) {
            const txt = (btn.textContent || '').trim();
            for (const kw of keywords) {
                if (txt.includes(kw) && btn.offsetParent !== null) {
                    btn.click();
                    return 'text:' + txt.substring(0, 20);
                }
            }
        }
        return null;
    })()
    """)
    if confirm_clicked:
        print(f"  [Confirm] 已点击确认: {confirm_clicked}")
    else:
        print("  [Confirm] 未检测到确认弹窗 (可能已直接提交)")

    await asyncio.sleep(2)
    print("  [Submit] 提交完成，等待页面响应...")


# ── 主流程 ───────────────────────────────────────────────

async def analyze_mode():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        cookie_ok = await load_cookies(ctx)
        page = await ctx.new_page()
        frame = await navigate_to_exam(page)
        if not cookie_ok:
            print("\n请手动登录后按 Enter...")
            input()
            await save_cookies(ctx)
        if frame:
            await asyncio.sleep(2)
            info = await frame.evaluate("""
            (() => {
                const classes = new Set();
                document.querySelectorAll('[class]').forEach(e => {
                    e.className.split(/\\s+/).forEach(c => classes.add(c));
                });
                const t = document.querySelector('.TiMu');
                const lis = t ? [...t.querySelectorAll('li[onclick*="addChoice"]')].map(li => ({
                    html: li.outerHTML.substring(0, 350)
                })) : [];
                return {
                    tiMuCount: document.querySelectorAll('.TiMu').length,
                    allClasses: [...classes].sort(),
                    firstTiMuHTML: t?.outerHTML?.substring(0, 2000) || '',
                    firstOptions: lis
                };
            })()
            """)
            print(f"\n[Dump] .TiMu 数量: {info['tiMuCount']}")
            print(f"[Dump] 所有 class ({len(info['allClasses'])}):")
            for c in info['allClasses']:
                print(f"  .{c}")
            print(f"\n[Dump] 第1题 HTML:\n{info['firstTiMuHTML'][:2000]}")
            print(f"\n[Dump] 第1题选项结构:")
            for o in info.get('firstOptions', []):
                print(f"  {o['html']}")
        await browser.close()


async def single_mode():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        await load_cookies(ctx)
        page = await ctx.new_page()
        frame = await navigate_to_exam(page)
        if not frame:
            print("[ERROR] 未找到 iframe")
            await browser.close(); return

        # 字体解密
        font_map = await get_font_mapping(frame)
        questions = await extract_questions(frame, font_map)
        print(f"\n[Extract] {len(questions)} 题 (含解密)")
        if not questions:
            await browser.close(); return

        # 分类统计
        types = {}
        for q in questions:
            types[q.qtype] = types.get(q.qtype, 0) + 1
        print(f"[Types] {types}")

        for i, q in enumerate(questions[:5]):
            print(f"\n{'─'*50}\n第{i+1}题 [{q.qtype}]\n  {q.title[:200]}")
            for o in q.options:
                print(f"    {o['label']}. {o['text'][:120]}")

        client = DeepSeekClient()
        raw = await client.ask(build_prompt(questions[:1]))
        print(f"\n{'='*50}\nAI 回复:\n{raw}")
        await browser.close()


async def answer_mode():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        await load_cookies(ctx)
        page = await ctx.new_page()
        frame = await navigate_to_exam(page)
        if not frame:
            print("[ERROR] 未找到内容 iframe，浏览器保持打开以便排查。")
            print("按 Enter 退出...")
            input()
            await browser.close(); return

        # 字体解密
        font_map = await get_font_mapping(frame)
        questions = await extract_questions(frame, font_map)
        types = {}
        for q in questions:
            types[q.qtype] = types.get(q.qtype, 0) + 1
        print(f"\n[Extract] {len(questions)} 题 | {types}")

        if not questions:
            print("[ERROR] 未提取到任何题目！可能页面结构有变化，浏览器保持打开以便排查。")
            print("按 Enter 退出...")
            input()
            await browser.close(); return

        # ── 打印所有题目到终端 ──
        for i, q in enumerate(questions):
            tag = {"single": "单选", "multiple": "多选", "judge": "判断", "fill": "填空"}.get(q.qtype, "?")
            print(f"\n{'─'*55}")
            print(f" 第{i+1}题 [{tag}] ")
            print(f"   题干: {q.title[:200]}")
            for o in q.options:
                print(f"     {o['label']}. {o['text'][:150]}")
        print(f"{'─'*55}\n")

        # 分离选择题和填空题
        choice_qs = [q for q in questions if q.qtype in ("single", "multiple", "judge")]
        fill_qs = [q for q in questions if q.qtype == "fill"]

        client = DeepSeekClient()
        all_answers = []
        BATCH = 20

        # 选择题分批作答
        if choice_qs:
            print(f"\n[AI] 处理 {len(choice_qs)} 道选择题...")
            for start in range(0, len(choice_qs), BATCH):
                batch = choice_qs[start:start + BATCH]
                try:
                    ans = await client.answer_questions(batch)
                    all_answers.extend(ans)
                except Exception as e:
                    print(f"  [ERROR] AI 调用失败: {e}")
                    all_answers.extend(["?"] * len(batch))
                if start + BATCH < len(choice_qs):
                    await asyncio.sleep(1)

        # 填空题分批作答
        fill_answers = []
        if fill_qs:
            print(f"\n[AI] 处理 {len(fill_qs)} 道填空题...")
            for start in range(0, len(fill_qs), BATCH):
                batch = fill_qs[start:start + BATCH]
                try:
                    ans = await client.answer_fill_questions(batch)
                    fill_answers.extend(ans)
                except Exception as e:
                    print(f"  [ERROR] AI 调用失败: {e}")
                    fill_answers.extend(["?"] * len(batch))
                if start + BATCH < len(fill_qs):
                    await asyncio.sleep(1)

        print(f"\n[Result] 选择题答案: {len(all_answers)}, 填空题答案: {len(fill_answers)}, 开始执行...")

        # 点击选择题
        for i, (q, ans) in enumerate(zip(choice_qs, all_answers)):
            try:
                ok = await click_option(frame, q, ans)
            except Exception as e:
                print(f"  [ERR] 点击第{i+1}题失败: {e}")
            await asyncio.sleep(0.2)
            if (i + 1) % 30 == 0:
                print(f"  ... 已完成选择题 {i+1}/{len(choice_qs)}")

        # 填写填空题
        for i, (q, ans) in enumerate(zip(fill_qs, fill_answers)):
            try:
                ok = await click_option(frame, q, ans)
            except Exception as e:
                print(f"  [ERR] 填空第{i+1}题失败: {e}")
            await asyncio.sleep(0.2)
            if (i + 1) % 10 == 0:
                print(f"  ... 已完成填空题 {i+1}/{len(fill_qs)}")

        print(f"\n[Action] 点击提交...")
        try:
            await click_submit(frame, page)
        except Exception as e:
            print(f"  [ERR] 提交失败: {e}")

        print("\n[Done] 答题完成! 浏览器保持打开，请检查页面确认提交结果。")
        print("按 Enter 退出程序...")
        input()
        await browser.close()


# ── 入口 ─────────────────────────────────────────────────
async def main():
    import argparse
    p = argparse.ArgumentParser(description="超星学习通 AI 答题助手")
    p.add_argument("--mode", choices=["analyze", "answer", "single"], default="analyze")
    p.add_argument("--url", type=str, default="", help="自定义目标URL (不填则用默认配置)")
    args = p.parse_args()

    global TARGET_URL
    if args.url:
        TARGET_URL = args.url
        print(f"[Config] 使用自定义 URL: {TARGET_URL[:120]}...")

    if not TARGET_URL:
        print("[ERROR] 请指定章节URL！")
        print("  方式一: python chaoxing_ai_answer.py --url \"章节页面完整URL\" --mode answer")
        print("  方式二: 编辑脚本中的 TARGET_URL 变量")
        return

    if args.mode == "analyze":    await analyze_mode()
    elif args.mode == "answer":   await answer_mode()
    elif args.mode == "single":   await single_mode()

if __name__ == "__main__":
    asyncio.run(main())
