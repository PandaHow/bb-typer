#!/usr/bin/env python3
"""
BB Typer - 选中文字后按快捷键自动转换为目标语言
BB Typer - Auto-convert selected text to target language via hotkey
"""

APP_VERSION = '1.0.0'
GITHUB_REPO = 'PandaHow/bb-typer'

import sys
import json
import time
import subprocess
import platform
import re
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from threading import Thread, Lock

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSystemTrayIcon, QMenu, QAction, QFrame,
    QComboBox, QLineEdit, QScrollArea, QGridLayout, QTabWidget,
    QDialog, QTextEdit, QDialogButtonBox, QMessageBox, QInputDialog,
    QListWidget, QListWidgetItem, QFileDialog, QToolTip
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QCursor

from pynput import keyboard
from pynput.keyboard import Key, Controller
from opencc import OpenCC

# Platform detection
IS_MACOS = platform.system() == 'Darwin'
IS_WINDOWS = platform.system() == 'Windows'

# Platform-specific imports
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    user32 = getattr(ctypes, 'windll').user32

# Cross-platform clipboard
try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    pyperclip = None
    HAS_PYPERCLIP = False


# Data files
DATA_FILE = Path(__file__).parent / 'stats.json'
CUSTOM_DICT_FILE = Path(__file__).parent / 'custom_dict.txt'
CUSTOM_DICT_HK_FILE = Path(__file__).parent / 'custom_dict_hk.txt'
CONFIG_FILE = Path(__file__).parent / 'config.json'
HISTORY_FILE = Path(__file__).parent / 'history.json'
LOCK_FILE = Path(__file__).parent / '.app.lock'

# Default hotkey
DEFAULT_HOTKEY = {'modifier': 'cmd' if IS_MACOS else 'ctrl', 'key': 'a'}

DEFAULT_QUICK_TEMPLATES = {
    '📢 公告': [
        {'name': '维护通知', 'text': '亲爱的玩家们，服务器将于今日进行维护更新，预计维护时间为2小时，届时将无法登录游戏，请大家提前做好准备，感谢您的理解与支持！'},
        {'name': '活动预告', 'text': '🎉 活动预告！即将上线全新活动，敬请期待！活动详情将在稍后公布，请密切关注官方公告~'},
        {'name': '更新完成', 'text': '✅ 维护已完成！服务器现已开放，感谢大家的耐心等待！如遇到任何问题请随时反馈~'},
        {'name': '紧急公告', 'text': '⚠️ 紧急通知：由于突发技术问题，服务器暂时关闭中，我们正在全力修复，请大家耐心等待，抱歉给您带来不便！'},
    ],
    '💬 回复': [
        {'name': '感谢反馈', 'text': '感谢您的反馈！我们已经记录下来，会尽快处理，如有进展会第一时间通知您~'},
        {'name': '问题收到', 'text': '您好！问题已收到，我们正在核实中，请稍等片刻~'},
        {'name': '已转交处理', 'text': '您好！您反映的问题我们已经转交给相关部门处理，会尽快给您答复，感谢您的耐心等待！'},
        {'name': '请提供信息', 'text': '您好！为了更好地帮助您解决问题，请提供一下您的游戏ID和出现问题的具体时间，谢谢配合~'},
    ],
    '🙏 致歉': [
        {'name': 'Bug致歉', 'text': '非常抱歉给您带来不好的游戏体验！我们已经定位到问题并正在修复中，修复后会第一时间通知大家，感谢您的理解！'},
        {'name': '延迟致歉', 'text': '抱歉让您久等了！由于反馈量较大，回复稍有延迟，我们会尽快处理您的问题~'},
        {'name': '补偿公告', 'text': '为了补偿大家因本次问题造成的损失，我们将发放补偿礼包，请留意游戏内邮件，再次感谢大家的理解与支持！'},
    ],
    '👋 问候': [
        {'name': '欢迎新人', 'text': '欢迎新朋友加入我们的大家庭！有任何问题都可以在群里问，大家都很热心的~'},
        {'name': '活动开始', 'text': '🎮 活动正式开始啦！大家冲冲冲！有问题随时问我~'},
        {'name': '節日祝福', 'text': '祝大家节日快乐！感谢一直以来的陪伴与支持，愿大家游戏愉快，欧气满满！🎊'},
    ],
}

TARGET_LANGUAGES = {
    'zh-TW': ('🇨🇳 台湾繁体', 'zh-TW', True),
    'zh-HK': ('🇭🇰 香港繁体', 'zh-TW', True),  # 使用本地词典 + OpenCC s2hk + LLM 润色
    'ja': ('🇯🇵 日语', 'ja', False),
    'ko': ('🇰🇷 韩语', 'ko', False),
    'en': ('🇬🇧 英语', 'en', False),
    'th': ('🇹🇭 泰语', 'th', False),
    'fr': ('🇫🇷 法语', 'fr', False),
}

SENTENCE_PATTERNS = [
    (r'有没有人知道', r'有沒有人知道'),
    (r'有没有人', r'有沒有人'),
    (r'有人吗$', r'有人嗎'),
    (r'谁知道', r'有誰知道'),
    (r'怎么样$', r'怎麼樣啊'),
    (r'好不好$', r'好不好啊'),
    (r'行不行$', r'行不行啊'),
    (r'可以吗$', r'可以嗎'),
    (r'是不是$', r'是不是啊'),
    (r'对不对$', r'對不對'),
    (r'是吗$', r'是嗎'),
    (r'对吗$', r'對嗎'),
    (r'好吗$', r'好嗎'),
    (r'行吗$', r'行嗎'),
    (r'能不能', r'能不能'),
    (r'会不会', r'會不會'),
    (r'要不要', r'要不要'),
    (r'有没有', r'有沒有'),
    (r'你说呢', r'你說呢'),
    (r'你们觉得呢', r'你們覺得呢'),
    (r'什么意思', r'什麼意思'),
    (r'怎么了$', r'怎麼了'),
    (r'干嘛$', r'幹嘛'),
    (r'干什么$', r'幹什麼'),
    (r'为什么$', r'為什麼'),
    (r'为啥$', r'為啥'),
    (r'很好$', r'很好欸'),
    (r'不错$', r'不錯欸'),
    (r'太棒$', r'太棒了啦'),
    (r'好看$', r'好看欸'),
    (r'好吃$', r'好吃欸'),
    (r'好玩$', r'好玩欸'),
    (r'厉害$', r'厲害欸'),
    (r'可爱$', r'可愛欸'),
    (r'开心$', r'開心欸'),
    (r'有意思$', r'有意思欸'),
    (r'有趣$', r'有趣欸'),
    (r'好听$', r'好聽欸'),
    (r'好帅$', r'好帥欸'),
    (r'好美$', r'好美欸'),
    (r'好强$', r'好強欸'),
    (r'好快$', r'好快欸'),
    (r'好难$', r'好難欸'),
    (r'好累$', r'好累喔'),
    (r'好烦$', r'好煩喔'),
    (r'好气$', r'好氣喔'),
    (r'真的$', r'真的欸'),
    (r'太扯了$', r'太扯了吧'),
    (r'太夸张了$', r'太誇張了吧'),
    (r'太过分了$', r'太過分了吧'),
    (r'我觉得', r'我覺得'),
    (r'我认为', r'我覺得'),
    (r'我感觉', r'我感覺'),
    (r'你觉得', r'你覺得'),
    (r'大家觉得', r'大家覺得'),
    (r'没想到', r'沒想到'),
    (r'想不到', r'想不到'),
    (r'说实话', r'說實話'),
    (r'老实说', r'老實說'),
    (r'不得不说', r'不得不說'),
    (r'怎么说呢', r'怎麼說呢'),
    (r'话说回来', r'話說回來'),
    (r'说到底', r'說到底'),
    (r'总的来说', r'總之'),
    (r'总而言之', r'總之'),
    (r'一般来说', r'一般來說'),
    (r'换句话说', r'換句話說'),
    (r'不管怎样', r'不管怎樣'),
    (r'反正就是', r'反正就是'),
    (r'你看看', r'你看看'),
    (r'你想想', r'你想想'),
    (r'你说说', r'你說說'),
    (r'然后呢', r'然後呢'),
    (r'然后', r'然後'),
    (r'所以说', r'所以說'),
    (r'就是说', r'就是說'),
    (r'也就是说', r'也就是說'),
    (r'意思是', r'意思是說'),
    (r'比如说', r'比如說'),
    (r'举个例子', r'舉個例子'),
    (r'特别(\S)', r'超\1'),
    (r'非常(\S)', r'超\1'),
    (r'超级(\S)', r'超\1'),
    (r'巨(\S)', r'超\1'),
    (r'贼(\S)', r'超\1'),
    (r'挺(\S)的', r'蠻\1的'),
    (r'蛮(\S)的', r'蠻\1的'),
    (r'相当(\S)', r'相當\1'),
    (r'搞不懂', r'搞不懂'),
    (r'看不懂', r'看不懂'),
    (r'听不懂', r'聽不懂'),
    (r'想不通', r'想不通'),
    (r'说不定', r'說不定'),
    (r'搞不好', r'搞不好'),
    (r'没事儿', r'沒事'),
    (r'没关系', r'沒關係'),
    (r'有点儿', r'有點'),
    (r'一点儿', r'一點'),
    (r'好玩儿', r'好玩'),
    (r'一块儿', r'一起'),
    (r'哪儿', r'哪裡'),
    (r'这儿', r'這裡'),
    (r'那儿', r'那裡'),
    (r'啥时候', r'什麼時候'),
    (r'多会儿', r'什麼時候'),
    (r'咋回事', r'怎麼回事'),
    (r'咋整', r'怎麼辦'),
    (r'咋办', r'怎麼辦'),
    (r'咋了', r'怎麼了'),
    (r'整个人都', r'整個人都'),
    (r'走着$', r'走吧'),
    (r'整起来', r'弄起來'),
    (r'你瞅瞅', r'你看看'),
    (r'得劲', r'舒服'),
    (r'不赖', r'不錯'),
    (r'忒', r'太'),
    (r'的话', r'的話'),
    (r'来着', r'來著'),
    (r'着呢', r'著呢'),
    (r'但是吧', r'但是呢'),
    (r'不过吧', r'不過呢'),
    (r'虽然吧', r'雖然呢'),
    (r'算了吧', r'算了啦'),
    (r'行了吧', r'好了啦'),
    (r'别介', r'別這樣'),
    (r'得了吧', r'算了吧'),
    (r'拉倒吧', r'算了啦'),
    (r'^嗯嗯$', r'嗯嗯'),
    (r'^哦$', r'喔'),
    (r'^哦哦$', r'喔喔'),
    (r'^好嘞$', r'好喔'),
    (r'^成$', r'好'),
    (r'^中$', r'好'),
    (r'^行$', r'好'),
    (r'^得嘞$', r'好喔'),
    (r'^没毛病$', r'沒問題'),
    (r'^靠谱$', r'靠譜'),
    (r'^不靠谱$', r'不靠譜'),
    (r'^稳$', r'穩'),
    (r'^妥$', r'好'),
    (r'^妥妥的$', r'穩的'),
    (r'^安排$', r'安排'),
    (r'^收到$', r'收到'),
    (r'^明白$', r'了解'),
    (r'^懂了$', r'懂了'),
    (r'^了解$', r'了解'),
    (r'^好的$', r'好的'),
    (r'^好吧$', r'好吧'),
    (r'^行吧$', r'好吧'),
    (r'^随便$', r'隨便'),
    (r'^无所谓$', r'都可以'),
    (r'^都行$', r'都可以'),
    (r'^看你$', r'看你'),
    (r'^你定$', r'你決定'),
    (r'^你决定$', r'你決定'),
    (r'天哪', r'天啊'),
    (r'天呐', r'天啊'),
    (r'我的天', r'我的天'),
    (r'^我去$', r'靠'),
    (r'我勒个去', r'靠'),
    (r'卧槽', r'靠北'),
    (r'我草', r'靠'),
    (r'牛逼', r'超強'),
    (r'牛B', r'超強'),
    (r'NB', r'超強'),
    (r'666', r'讚讚'),
    (r'厉害了', r'太厲害了吧'),
]

# Language -> timezone city mapping
LANG_TIMEZONE_MAP = {
    'zh-TW': ('台北', 'Asia/Taipei', '🇨🇳'),
    'zh-HK': ('香港', 'Asia/Hong_Kong', '🇭🇰'),
    'en': ('伦敦', 'Europe/London', '🇬🇧'),
    'ja': ('东京', 'Asia/Tokyo', '🇯🇵'),
    'ko': ('首尔', 'Asia/Seoul', '🇰🇷'),
    'fr': ('巴黎', 'Europe/Paris', '🇫🇷'),
    'de': ('柏林', 'Europe/Berlin', '🇩🇪'),
    'it': ('罗马', 'Europe/Rome', '🇮🇹'),
    'pt': ('里斯本', 'Europe/Lisbon', '🇧🇷'),
    'ru': ('莫斯科', 'Europe/Moscow', '🇷🇺'),
    'ar': ('利雅得', 'Asia/Riyadh', '🇸🇦'),
    'th': ('曼谷', 'Asia/Bangkok', '🇹🇭'),
    'vi': ('河内', 'Asia/Ho_Chi_Minh', '🇻🇳'),
    'id': ('雅加达', 'Asia/Jakarta', '🇮🇩'),
    'ms': ('吉隆坡', 'Asia/Kuala_Lumpur', '🇲🇾'),
    'tl': ('马尼拉', 'Asia/Manila', '🇵🇭'),
    'my': ('仰光', 'Asia/Yangon', '🇲🇲'),
}

THEMES = {
    'light': {
        'bg': '#E8EDF2',
        'card': '#FFFFFF',
        'card_alt': '#F7F7F7',
        'text': '#111111',
        'text_secondary': '#999999',
        'border': '#D9D9D9',
        'hover': '#D8D8D8',
        'accent': '#07C160',
        'accent_hover': '#06AD56',
        'link': '#576B95',
        'danger': '#FA5151',
        'danger_hover': '#CC0000',
        'tab_bg': '#EDEDED',
        'tab_selected_bg': '#FFFFFF',
        'input_bg': '#F7F7F7',
        'disabled_bg': '#C8C8C8',
        'disabled_hover': '#B0B0B0',
    }
}
# LLM 配置：使用 Pie Gateway
PIE_BASE_URL = os.environ.get('PIE_BASE_URL', 'http://8.222.169.8:3000')
PIE_TOKEN = os.environ.get('PIE_TOKEN', '')
PIE_LLM_MODEL = 'gemini-2.5-flash-lite'

LLM_SYSTEM_PROMPT = '''你是一個台灣繁體中文潤色助手。你的任務是將已經初步轉換的繁體中文文字，潤色成更自然、更道地的台灣口語表達。

規則：
1. 保持原意不變，只調整用詞和語氣
2. 使用台灣人日常說話的方式，包括台灣特有的俗語、網路用語和流行語
3. 適當加入台灣語氣詞（喔、啦、欸、齁、蛤、捏、der）
4. 將大陸俗語/網路用語轉為台灣等價表達，例如：
   - 「給力」→「讚」或「超讚」
   - 「666」→「太神了」
   - 「躺平」→「躺平」（兩岸通用可保留）
   - 「yyds」→「YYDS」或「永遠的神」
   - 「絕絕子」→「太扯了吧」
   - 「內卷」→「捲」
5. 不要過度修改，保持自然
6. 不要加引號、不要解釋、不要加任何前綴後綴
7. 直接輸出潤色後的文字，不要輸出其他任何內容
8. 如果原文已經很自然，就直接輸出原文'''

LLM_SYSTEM_PROMPT_HK = '''你是一個香港繁體中文潤色助手。你的任務是將已經初步轉換的繁體中文文字，潤色成更自然、更地道的香港廣東話書面表達。

規則：
1. 保持原意不變，只調整用詞和語氣
2. 使用香港人日常書寫的方式，包括香港特有的俗語和網路用語
3. 適當加入香港語氣詞（啡、啦、喓、吗、嘻、喊）
4. 將大陸用語轉為香港等價表達，例如：
   - 「給力」→「勁」
   - 「牛逼」→「勁」或「超勁」
   - 「絕絕子」→「絕了」
   - 「內卷」→「捲」
   - 「單車」→「單車」（通用可保留）
5. 不要過度修改，保持自然
6. 不要加引號、不要解釋、不要加任何前綴後綴
7. 直接輸出潤色後的文字，不要輸出其他任何內容
8. 如果原文已經很自然，就直接輸出原文'''

def apply_sentence_patterns(text: str) -> str:
    for pattern, replacement in SENTENCE_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


def llm_polish(text: str, system_prompt: str = '') -> str:
    """使用 Pie Gateway LLM 润色"""
    prompt = system_prompt or LLM_SYSTEM_PROMPT
    if not PIE_TOKEN:
        return text
    try:
        url = f'{PIE_BASE_URL}/v1/app/chat/completions'
        payload = json.dumps({
            'model': PIE_LLM_MODEL,
            'messages': [
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': text}
            ],
            'max_tokens': 500,
            'temperature': 0.3
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Authorization', f'Bearer {PIE_TOKEN}')
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            polished = result['choices'][0]['message']['content'].strip()
            if len(polished) > len(text) * 3 or len(polished) < len(text) * 0.3:
                return text
            return polished
    except Exception:
        return text


def is_simplified_chinese(text: str) -> bool:
    """Detect if text is predominantly simplified Chinese.
    Uses Google Translate's language detection via translating with sl=auto.
    Falls back to character-based heuristic if API fails.
    """
    # Quick heuristic: count CJK characters
    cjk_chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
    if not cjk_chars:
        return False  # No Chinese characters at all
    # Try Google Translate's auto-detect
    try:
        url = 'https://translate.googleapis.com/translate_a/single'
        params = urllib.parse.urlencode({
            'client': 'gtx', 'sl': 'auto', 'tl': 'en', 'dt': 't', 'q': text[:100]
        })
        req = urllib.request.Request(f'{url}?{params}')
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            detected_lang = data[2] if len(data) > 2 else ''
            return detected_lang == 'zh-CN'
    except Exception:
        # Fallback: use OpenCC to convert to simplified and compare
        # If text barely changes, it's already simplified
        try:
            converter_t2s = OpenCC('t2s')
            simplified = converter_t2s.convert(text)
            # If converting trad→simplified changes very few characters, text is already simplified
            diff_count = sum(1 for a, b in zip(text, simplified) if a != b)
            return diff_count < len(cjk_chars) * 0.15
        except Exception:
            return True  # Default assume simplified


def google_translate(text: str, target_lang: str = 'zh-TW', source_lang: str = 'zh-CN') -> str:
    try:
        url = 'https://translate.googleapis.com/translate_a/single'
        params = urllib.parse.urlencode({
            'client': 'gtx',
            'sl': source_lang,
            'tl': target_lang,
            'dt': 't',
            'q': text
        })
        req = urllib.request.Request(f'{url}?{params}')
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            translated = ''.join(part[0] for part in data[0] if part[0])
            if translated.strip():
                return translated
            return text
    except Exception:
        return ''


def get_clipboard() -> str:
    if HAS_PYPERCLIP and pyperclip is not None:
        return pyperclip.paste()
    elif IS_MACOS:
        result = subprocess.run(['pbpaste'], capture_output=True, text=True, timeout=1)
        return result.stdout
    elif IS_WINDOWS:
        result = subprocess.run(['powershell', '-command', 'Get-Clipboard'], capture_output=True, text=True, timeout=1)
        return result.stdout.rstrip('\r\n')
    return ""


def set_clipboard(text: str):
    if HAS_PYPERCLIP and pyperclip is not None:
        pyperclip.copy(text)
    elif IS_MACOS:
        subprocess.run(['pbcopy'], input=text.encode('utf-8'), timeout=1)
    elif IS_WINDOWS:
        subprocess.run(['powershell', '-command', f'Set-Clipboard -Value "{text}"'], timeout=1)


def get_modifier_key() -> Key:
    return Key.cmd if IS_MACOS else Key.ctrl


def load_config() -> dict:
    default = {
        'hotkey': DEFAULT_HOTKEY,
        'target_lang': 'zh-TW',
        'llm_polish': True,
    }
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text())
            for key in default:
                if key not in config:
                    config[key] = default[key]
            return config
        except:
            return default
    return default


def save_config(config: dict):
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2))


def load_custom_dict(dict_file=None) -> dict:
    mappings = {}
    filepath = dict_file or CUSTOM_DICT_FILE
    if filepath.exists():
        for line in filepath.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split('\t')
                if len(parts) == 2:
                    mappings[parts[0]] = parts[1]
    sorted_mappings = dict(sorted(mappings.items(), key=lambda x: len(x[0]), reverse=True))
    return sorted_mappings

def get_timezone_time(tz_name: str) -> str:
    offsets = {
        'Asia/Tokyo': 9,
        'Asia/Bangkok': 7,
        'Asia/Jakarta': 7,
        'Asia/Seoul': 9,
        'Asia/Singapore': 8,
        'Asia/Hong_Kong': 8,
        'Asia/Manila': 8,
        'Asia/Taipei': 8,
        'Asia/Shanghai': 8,
        'Europe/London': 0,
        'Europe/Paris': 1,
        'Europe/Berlin': 1,
        'Europe/Rome': 1,
        'Europe/Lisbon': 0,
        'Europe/Moscow': 3,
        'Asia/Riyadh': 3,
        'Asia/Ho_Chi_Minh': 7,
        'Asia/Kuala_Lumpur': 8,
        'Asia/Yangon': 6.5,
    }
    offset_hours = offsets.get(tz_name, 0)
    tz = timezone(timedelta(hours=offset_hours))
    now = datetime.now(tz)
    return now.strftime('%H:%M')


class KeyboardSignal(QObject):
    stats_updated = pyqtSignal()
    key_pressed = pyqtSignal(str)
    conversion_done = pyqtSignal(str, str)
    google_status = pyqtSignal(bool)
    history_updated = pyqtSignal()


class StatsManager:
    
    def __init__(self):
        self.data = self._load()
        self.lock = Lock()
    
    def _load(self) -> dict:
        if DATA_FILE.exists():
            try:
                return json.loads(DATA_FILE.read_text())
            except:
                return {}
        return {}
    
    def _save(self):
        DATA_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))
    
    def add_chars(self, count: int):
        with self.lock:
            today = str(date.today())
            self.data[today] = self.data.get(today, 0) + count
            self._save()
    
    def clear_today_stats(self):
        with self.lock:
            today = str(date.today())
            self.data[today] = 0
            self._save()
    
    def get_today(self) -> int:
        return self.data.get(str(date.today()), 0)
    
    def get_total(self) -> int:
        return sum(self.data.values())


class ClipboardHistory:
    
    def __init__(self, max_items: int = 20):
        self.max_items = max_items
        self.items = self._load()
    
    def _load(self) -> list:
        if HISTORY_FILE.exists():
            try:
                return json.loads(HISTORY_FILE.read_text())
            except:
                return []
        return []
    
    def _save(self):
        HISTORY_FILE.write_text(json.dumps(self.items, ensure_ascii=False, indent=2))
    
    def add(self, original: str, translated: str, target_lang: str):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        item = {
            'original': original,
            'translated': translated,
            'target_lang': target_lang,
            'timestamp': timestamp
        }
        self.items.insert(0, item)
        if len(self.items) > self.max_items:
            self.items = self.items[:self.max_items]
        self._save()
    
    def clear(self):
        self.items = []
        self._save()
    
    def get_all(self) -> list:
        return self.items


class TemplateButton(QPushButton):
    """Button that shows tooltip on hover immediately"""
    def __init__(self, name, full_text, parent=None):
        super().__init__(name, parent)
        self._full_text = full_text

    def enterEvent(self, event):
        if self._full_text:
            QToolTip.showText(QCursor.pos(), self._full_text, self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)



class TaiwanConverterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.converter = OpenCC('s2twp')
        self.custom_dict = load_custom_dict()
        self.converter_hk = OpenCC('s2hk')
        self.custom_dict_hk = load_custom_dict(CUSTOM_DICT_HK_FILE)
        self.keyboard_controller = Controller()
        self.stats = StatsManager()
        self.config = load_config()
        self.history = ClipboardHistory()
        self.is_enabled = True
        self.is_converting = False
        self.convert_lock = Lock()
        self.last_key = ""
        self.key_count = 0
        self.cmd_pressed = False
        self.ctrl_pressed = False
        self.alt_pressed = False
        self.shift_pressed = False
        self.recording_hotkey = False
        self.pending_hotkey = None
        self.translation_cache = {}  # {translated_text: original_text} 用于反向还原
        
        self.signal = KeyboardSignal()
        self.signal.stats_updated.connect(self.update_stats_display)
        self.signal.key_pressed.connect(self.update_key_display)
        self.signal.conversion_done.connect(self.update_conversion_display)
        self.signal.google_status.connect(self.update_google_status)
        self.signal.history_updated.connect(self.update_history_display)
        
        self.listener = None
        
        self.init_ui()
        self.init_tray()
        self.start_listening()
        
        self.google_timer = QTimer()
        self.google_timer.timeout.connect(self.check_google_connectivity)
        self.google_timer.start(30000)
        QTimer.singleShot(1000, self.check_google_connectivity)
        
        self.timezone_timer = QTimer()
        self.timezone_timer.timeout.connect(self.update_timezone_display)
        self.timezone_timer.start(60000)
        self.update_timezone_display()
        
        # 启动 3 秒后检查更新
        QTimer.singleShot(3000, self.check_for_updates)
    
    def init_ui(self):
        self.setWindowTitle(f'BB Typer v{APP_VERSION}')
        self.setFixedSize(380, 420)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_tabs = QTabWidget()
        self.main_tabs.addTab(self._create_core_tab(), '语言设置')
        self.main_tabs.addTab(self._create_toolbox_tab(), '工具箱')
        main_layout.addWidget(self.main_tabs)

        self.apply_theme()

    def _create_core_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(0)

        # ── Status header: Google status (left) + toggle (right) ──
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.google_status_label = QLabel('🟢 Google已连接')
        self.google_status_label.setFont(QFont('PingFang SC', 11))
        header.addWidget(self.google_status_label)

        self.google_help_btn = QPushButton('?')
        self.google_help_btn.setFixedSize(20, 20)
        self.google_help_btn.clicked.connect(self.show_google_help)
        header.addWidget(self.google_help_btn)

        header.addStretch()

        self.toggle_btn = QPushButton('⏸ 暂停')
        self.toggle_btn.setFixedHeight(26)
        self.toggle_btn.clicked.connect(self.toggle_enabled)
        header.addWidget(self.toggle_btn)

        layout.addLayout(header)
        layout.addSpacing(14)

        # ── Main control card ──
        card = QFrame()
        card.setObjectName('core_card')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(14)

        # Row 1: Language
        lang_row = QHBoxLayout()
        lang_row.setSpacing(0)
        lang_lbl = QLabel('语言')
        lang_lbl.setFont(QFont('PingFang SC', 13))
        lang_lbl.setFixedWidth(60)
        lang_row.addWidget(lang_lbl)
        self.lang_combo = QComboBox()
        self.lang_combo.setFixedHeight(30)
        for key, (display_name, _, _) in TARGET_LANGUAGES.items():
            self.lang_combo.addItem(display_name, key)
        current_lang = self.config.get('target_lang', 'zh-TW')
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == current_lang:
                self.lang_combo.setCurrentIndex(i)
                break
        self.lang_combo.currentIndexChanged.connect(self.on_lang_changed)
        lang_row.addWidget(self.lang_combo)
        card_layout.addLayout(lang_row)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setObjectName('card_sep')
        card_layout.addWidget(sep1)

        # Row 2: Hotkey
        hotkey_row = QHBoxLayout()
        hotkey_row.setSpacing(0)
        hotkey_lbl = QLabel('快捷键')
        hotkey_lbl.setFont(QFont('PingFang SC', 13))
        hotkey_lbl.setFixedWidth(60)
        hotkey_row.addWidget(hotkey_lbl)
        self.hotkey_value_label = QLabel(self.format_hotkey())
        self.hotkey_value_label.setFont(QFont('PingFang SC', 13, QFont.Bold))
        hotkey_row.addWidget(self.hotkey_value_label)
        hotkey_row.addStretch()
        self.change_hotkey_btn = QPushButton('修改')
        self.change_hotkey_btn.setFixedHeight(26)
        self.change_hotkey_btn.clicked.connect(self.start_recording_hotkey)
        hotkey_row.addWidget(self.change_hotkey_btn)

        self.confirm_hotkey_btn = QPushButton('确定')
        self.confirm_hotkey_btn.setFixedHeight(26)
        self.confirm_hotkey_btn.clicked.connect(self.finish_recording_hotkey)
        self.confirm_hotkey_btn.hide()
        hotkey_row.addWidget(self.confirm_hotkey_btn)

        self.cancel_hotkey_btn = QPushButton('取消')
        self.cancel_hotkey_btn.setFixedHeight(26)
        self.cancel_hotkey_btn.clicked.connect(self.cancel_recording_hotkey)
        self.cancel_hotkey_btn.hide()
        hotkey_row.addWidget(self.cancel_hotkey_btn)
        card_layout.addLayout(hotkey_row)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setObjectName('card_sep')
        card_layout.addWidget(sep2)

        # Row 3: Timezone
        tz_row = QHBoxLayout()
        tz_row.setSpacing(0)
        tz_lbl = QLabel('时区')
        tz_lbl.setFont(QFont('PingFang SC', 13))
        tz_lbl.setFixedWidth(60)
        tz_row.addWidget(tz_lbl)
        self.timezone_label = QLabel('')
        self.timezone_label.setFont(QFont('PingFang SC', 13))
        tz_row.addWidget(self.timezone_label)
        tz_row.addStretch()
        card_layout.addLayout(tz_row)

        layout.addWidget(card)
        layout.addSpacing(10)

        # ── AI 润色状态 ──
        ai_card = QFrame()
        ai_card.setObjectName('ai_card')
        ai_layout = QHBoxLayout(ai_card)
        ai_layout.setContentsMargins(10, 6, 10, 6)
        ai_layout.setSpacing(8)
        ai_lbl = QLabel('AI 润色')
        ai_lbl.setFont(QFont('PingFang SC', 11))
        ai_layout.addWidget(ai_lbl)
        self.ai_status_lbl = QLabel()
        self.ai_status_lbl.setFont(QFont('PingFang SC', 10))
        ai_layout.addWidget(self.ai_status_lbl)
        ai_layout.addStretch()
        self.ai_toggle_btn = QPushButton()
        self.ai_toggle_btn.setFixedHeight(26)
        self.ai_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ai_toggle_btn.clicked.connect(self.toggle_ai_polish)
        ai_layout.addWidget(self.ai_toggle_btn)
        ai_help_btn = QPushButton('?')
        ai_help_btn.setFixedSize(20, 20)
        ai_help_btn.clicked.connect(self.show_ai_help)
        self.ai_help_btn = ai_help_btn
        ai_layout.addWidget(ai_help_btn)
        layout.addWidget(ai_card)
        self.update_ai_status()

        # ── Stats bar ──
        self.status_bar_frame = QFrame()
        self.status_bar_frame.setObjectName('stats_bar')
        stats_layout = QHBoxLayout(self.status_bar_frame)
        stats_layout.setContentsMargins(16, 8, 16, 8)
        self.stats_label = QLabel('今日 0 字 | 累计 0 字')
        self.stats_label.setFont(QFont('PingFang SC', 12))
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()
        self.update_stats_display()
        layout.addWidget(self.status_bar_frame)

        # ── Bottom buttons: tutorial + feedback ──
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        self.tutorial_btn = QPushButton('📖 使用教程')
        self.tutorial_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tutorial_btn.clicked.connect(self.show_tutorial)
        bottom_row.addWidget(self.tutorial_btn)
        self.feedback_btn = QPushButton('💬 提交反馈')
        self.feedback_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.feedback_btn.clicked.connect(self.open_feedback)
        bottom_row.addWidget(self.feedback_btn)
        layout.addLayout(bottom_row)

        layout.addStretch()
        return widget

    def _create_toolbox_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(10)
        self.content_tabs = QTabWidget()
        self.content_tabs.addTab(self._create_templates_tab(), '💬 快速回复')
        self.content_tabs.addTab(self._create_history_tab(), '📋 翻译历史')
        layout.addWidget(self.content_tabs, 1)

        self.preview_original = QLabel('')
        self.preview_original.setFont(QFont('PingFang SC', 12))
        self.preview_original.setVisible(False)
        layout.addWidget(self.preview_original)

        self.preview_converted = QLabel('')
        self.preview_converted.setFont(QFont('PingFang SC', 12))
        self.preview_converted.setVisible(False)
        layout.addWidget(self.preview_converted)

        return widget

    def _create_templates_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(8)
        
        # Header row: search + buttons
        header = QHBoxLayout()
        
        self.template_search = QLineEdit()
        self.template_search.setPlaceholderText('搜索模板...')
        self.template_search.setFixedWidth(120)
        self.template_search.setStyleSheet('''
            QLineEdit {
                background-color: #F7F7F7;
                border: 1px solid #D9D9D9;
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 12px;
            }
        ''')
        self.template_search.textChanged.connect(self.filter_templates)
        header.addWidget(self.template_search)
        
        header.addStretch()
        
        link_btn_style = '''
            QPushButton {
                background-color: transparent;
                color: #576B95;
                border: none;
                font-size: 13px;
            }
            QPushButton:hover {
                color: #07C160;
            }
        '''
        
        add_btn = QPushButton('+ 新增')
        add_btn.setStyleSheet(link_btn_style)
        add_btn.clicked.connect(self.add_custom_template)
        header.addWidget(add_btn)
        
        import_btn = QPushButton('导入')
        import_btn.setStyleSheet(link_btn_style)
        import_btn.clicked.connect(self.import_templates)
        header.addWidget(import_btn)
        
        export_btn = QPushButton('导出')
        export_btn.setStyleSheet(link_btn_style)
        export_btn.clicked.connect(self.export_templates)
        header.addWidget(export_btn)
        
        layout.addLayout(header)
        
        # Template category tabs (nested inside this tab)
        self.templates_tab = QTabWidget()
        self.templates_tab.setStyleSheet('''
            QTabWidget::pane {
                border: 1px solid #D9D9D9;
                border-radius: 4px;
                background-color: #F7F7F7;
            }
            QTabBar::tab {
                background-color: #EDEDED;
                color: #999999;
                padding: 4px 10px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #F7F7F7;
                color: #07C160;
            }
        ''')
        self.load_templates_ui()
        layout.addWidget(self.templates_tab)
        
        return widget
    
    def _create_history_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(5)
        
        # Header with clear button
        header = QHBoxLayout()
        
        hint_label = QLabel('双击条目可复制到剪贴板')
        hint_label.setFont(QFont('PingFang SC', 12))
        hint_label.setStyleSheet('color: #999999;')
        header.addWidget(hint_label)
        
        header.addStretch()
        
        clear_btn = QPushButton('清空')
        clear_btn.setStyleSheet('''
            QPushButton {
                background-color: transparent;
                color: #FA5151;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #CC0000;
            }
        ''')
        clear_btn.clicked.connect(self.clear_history)
        header.addWidget(clear_btn)
        
        layout.addLayout(header)
        
        # History list
        self.history_list = QListWidget()
        self.history_list.setStyleSheet('''
            QListWidget {
                background-color: #F7F7F7;
                border: 1px solid #D9D9D9;
                border-radius: 6px;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid #F0F0F0;
            }
            QListWidget::item:hover {
                background-color: #D8D8D8;
            }
        ''')
        self.history_list.itemDoubleClicked.connect(self.copy_history_item)
        layout.addWidget(self.history_list)
        
        self.update_history_display()
        
        return widget


    def apply_theme(self):
        t = THEMES['light']

        # Window background
        self.setStyleSheet(f'''
            QMainWindow {{
                background-color: {t['bg']};
            }}
            QLabel {{
                color: {t['text']};
            }}
            QToolTip {{
                background-color: #FFFFFF;
                color: #1F2329;
                border: 1px solid #D0D7DE;
                border-radius: 8px;
                padding: 8px 10px;
                font-size: 12px;
            }}
        ''')

        # Top-level tabs
        self.main_tabs.setStyleSheet(f'''
            QTabWidget::pane {{
                border: none;
                background-color: {t['bg']};
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {t['text_secondary']};
                padding: 8px 20px;
                margin-right: 2px;
                font-size: 13px;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: {t['accent']};
                font-weight: bold;
                border-bottom: 2px solid {t['accent']};
            }}
            QTabBar::tab:hover {{
                color: {t['text']};
            }}
        ''')

        # Google status
        if '已连接' in self.google_status_label.text():
            self.google_status_label.setStyleSheet(f'color: {t["accent"]};')
        else:
            self.google_status_label.setStyleSheet(f'color: {t["danger"]};')

        # Toggle button
        if self.is_enabled:
            self.toggle_btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {t['accent']};
                    color: white;
                    border: none;
                    border-radius: 13px;
                    padding: 4px 14px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {t['accent_hover']};
                }}
            ''')
        else:
            self.toggle_btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {t['disabled_bg']};
                    color: white;
                    border: none;
                    border-radius: 13px;
                    padding: 4px 14px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {t['disabled_hover']};
                }}
            ''')

        # Core card
        for frame in self.findChildren(QFrame):
            name = frame.objectName()
            if name == 'core_card':
                frame.setStyleSheet(
                    f'QFrame#core_card {{ background-color: {t["card"]}; '
                    f'border: 1px solid {t["border"]}; border-radius: 12px; }}'
                )
            elif name == 'stats_bar':
                frame.setStyleSheet(
                    f'QFrame#stats_bar {{ background-color: {t["card"]}; '
                    f'border: 1px solid {t["border"]}; border-radius: 10px; }}'
                )
            elif name == 'card_sep':
                frame.setStyleSheet(f'color: {t["border"]};')

        # Lang combo
        self.lang_combo.setStyleSheet(f'''
            QComboBox {{
                background-color: {t['input_bg']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 13px;
                color: {t['text']};
            }}
            QComboBox:hover {{
                border-color: {t['accent']};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {t['card']};
                selection-background-color: {t['accent']};
                color: {t['text']};
            }}
        ''')

        # Hotkey value
        if self.recording_hotkey:
            self.hotkey_value_label.setStyleSheet(f'''
                color: {t["accent"]};
                background-color: {t["input_bg"]};
                border: 1px dashed {t["accent"]};
                border-radius: 6px;
                padding: 2px 8px;
            ''')
        else:
            self.hotkey_value_label.setStyleSheet(f'color: {t["accent"]};')

        # Change hotkey btn
        self.change_hotkey_btn.setStyleSheet(f'''
            QPushButton {{
                background-color: {t['input_bg']};
                border: 1px solid {t['border']};
                border-radius: 13px;
                padding: 4px 14px;
                font-size: 12px;
                color: {t['text_secondary']};
            }}
            QPushButton:hover {{
                border-color: {t['accent']};
                color: {t['accent']};
            }}
        ''')

        self.confirm_hotkey_btn.setStyleSheet(f'''
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 13px;
                padding: 4px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {t['accent_hover']};
            }}
        ''')

        self.cancel_hotkey_btn.setStyleSheet(f'''
            QPushButton {{
                background-color: {t['input_bg']};
                border: 1px solid {t['border']};
                border-radius: 13px;
                padding: 4px 14px;
                font-size: 12px;
                color: {t['text_secondary']};
            }}
            QPushButton:hover {{
                border-color: {t['accent']};
                color: {t['accent']};
            }}
        ''')

        self.google_help_btn.setStyleSheet(f'''
            QPushButton {{
                background-color: {t['input_bg']};
                color: {t['text_secondary']};
                border: 1px solid {t['border']};
                border-radius: 10px;
                font-size: 11px;
                padding: 0;
            }}
            QPushButton:hover {{
                border-color: {t['accent']};
                color: {t['accent']};
            }}
        ''')

        # AI 润色 help button
        self.ai_help_btn.setStyleSheet(f'''
            QPushButton {{
                background-color: {t['input_bg']};
                color: {t['text_secondary']};
                border: 1px solid {t['border']};
                border-radius: 10px;
                font-size: 11px;
                padding: 0;
            }}
            QPushButton:hover {{
                border-color: {t['accent']};
                color: {t['accent']};
            }}
        ''')
        # Timezone
        self.timezone_label.setStyleSheet(f'color: {t["link"]};')

        # Stats label
        self.stats_label.setStyleSheet(f'color: {t["text_secondary"]}; font-size: 12px;')

        # Tutorial & Feedback buttons
        for btn in (self.tutorial_btn, self.feedback_btn):
            btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {t['card']};
                    color: {t['text_secondary']};
                    border: 1px solid {t['border']};
                    border-radius: 8px;
                    padding: 6px 16px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {t['card_alt']};
                    border-color: {t['accent']};
                    color: {t['accent']};
                }}
            ''')

        # ── Toolbox tab widgets ──
        # Content tabs (templates + history)
        self.content_tabs.setStyleSheet(f'''
            QTabWidget::pane {{
                background-color: {t['card']};
                border: 1px solid {t['border']};
                border-radius: 6px;
            }}
            QTabBar::tab {{
                background-color: {t['tab_bg']};
                color: {t['text_secondary']};
                padding: 6px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 13px;
            }}
            QTabBar::tab:selected {{
                background-color: {t['tab_selected_bg']};
                color: {t['accent']};
                font-weight: bold;
            }}
            QTabBar::tab:hover {{
                background-color: {t['hover']};
            }}
        ''')

        self.templates_tab.setStyleSheet(f'''
            QTabWidget::pane {{
                border: 1px solid {t['border']};
                border-radius: 4px;
                background-color: {t['card_alt']};
            }}
            QTabBar::tab {{
                background-color: {t['tab_bg']};
                color: {t['text_secondary']};
                padding: 4px 10px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background-color: {t['card_alt']};
                color: {t['accent']};
            }}
        ''')

        self.template_search.setStyleSheet(f'''
            QLineEdit {{
                background-color: {t['input_bg']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 12px;
                color: {t['text']};
            }}
        ''')

        self.history_list.setStyleSheet(f'''
            QListWidget {{
                background-color: {t['input_bg']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                font-size: 13px;
                color: {t['text']};
            }}
            QListWidget::item {{
                padding: 8px 10px;
                border-bottom: 1px solid {t['border']};
            }}
            QListWidget::item:hover {{
                background-color: {t['hover']};
            }}
        ''')

        self.preview_original.setStyleSheet(f'color: {t["text_secondary"]};')
        self.preview_converted.setStyleSheet(f'color: {t["text_secondary"]};')
    
    def init_tray(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QColor('#07C160'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        
        self.tray_icon = QSystemTrayIcon(QIcon(pixmap), self)
        
        tray_menu = QMenu()
        
        self.tray_status = QAction('● 已启用', self)
        self.tray_status.setEnabled(False)
        tray_menu.addAction(self.tray_status)
        
        tray_menu.addSeparator()
        
        toggle_action = QAction('暂停/继续', self)
        toggle_action.triggered.connect(self.toggle_enabled)
        tray_menu.addAction(toggle_action)
        
        show_action = QAction('显示窗口', self)
        show_action.triggered.connect(self.show_and_activate)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction('退出', self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_activated)
        self.tray_icon.show()
    
    def show_and_activate(self):
        self.show()
        self.raise_()
        self.activateWindow()
    
    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_and_activate()
    
    def start_listening(self):
        if self.listener is None:
            self.listener = keyboard.Listener(
                on_press=self.on_key_press,
                on_release=self.on_key_release
            )
            self.listener.start()
    
    def stop_listening(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
    
    def toggle_enabled(self):
        t = THEMES['light']
        self.is_enabled = not self.is_enabled
        if self.is_enabled:
            self.toggle_btn.setText('⏸ 暂停')
            self.toggle_btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {t['accent']};
                    color: white;
                    border: none;
                    border-radius: 13px;
                    padding: 4px 14px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {t['accent_hover']};
                }}
            ''')
            self.tray_status.setText('● 已启用')
        else:
            self.toggle_btn.setText('▶ 继续')
            self.toggle_btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {t['disabled_bg']};
                    color: white;
                    border: none;
                    border-radius: 13px;
                    padding: 4px 14px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {t['disabled_hover']};
                }}
            ''')
            self.tray_status.setText('● 已暂停')

    
    def update_stats_display(self):
        today = self.stats.get_today()
        total = self.stats.get_total()
        self.stats_label.setText(f'今日 {today:,} 字 | 累计 {total:,} 字')
    
    def format_hotkey(self) -> str:
        hotkey = self.config.get('hotkey', DEFAULT_HOTKEY)
        modifier = hotkey.get('modifier', 'cmd')
        key = hotkey.get('key', 'a')
        
        modifier_symbols = {
            'cmd': '⌘',
            'ctrl': '⌃',
            'alt': '⌥',
            'shift': '⇧'
        }
        
        symbol = modifier_symbols.get(modifier, modifier)
        return f"{symbol}+{key.upper()}"
    
    def start_recording_hotkey(self):
        self.recording_hotkey = True
        self.pending_hotkey = None
        self.hotkey_value_label.setText('请按下快捷键...')
        self.change_hotkey_btn.hide()
        self.confirm_hotkey_btn.show()
        self.cancel_hotkey_btn.show()
        self.apply_theme()

    def cancel_recording_hotkey(self):
        self.recording_hotkey = False
        self.pending_hotkey = None
        self.hotkey_value_label.setText(self.format_hotkey())
        self.confirm_hotkey_btn.hide()
        self.cancel_hotkey_btn.hide()
        self.change_hotkey_btn.show()
        self.apply_theme()

    def finish_recording_hotkey(self):
        if self.pending_hotkey:
            modifier, key = self.pending_hotkey
            self.config['hotkey'] = {'modifier': modifier, 'key': key}
            save_config(self.config)
        self.recording_hotkey = False
        self.hotkey_value_label.setText(self.format_hotkey())
        self.pending_hotkey = None
        self.confirm_hotkey_btn.hide()
        self.cancel_hotkey_btn.hide()
        self.change_hotkey_btn.show()
        self.apply_theme()

    def show_google_help(self):
        QMessageBox.information(
            self,
            'Google 翻译服务说明',
            '本工具通过 Google 翻译检测网络连接状态\n\n'
            '• 台湾繁体 / 香港繁体：不依赖 Google 翻译，'
            '使用本地词典 + OpenCC + AI 润色，'
            '离线也能用\n\n'
            '• 其他语言（日语、韩语、泰语等）：'
            '依赖 Google 翻译，需要保持网络连接'
            '且能访问 Google 服务\n\n'
            '如果显示“未连接”：\n'
            '  - 台湾/香港繁体用户可正常使用，不受影响\n'
            '  - 其他语言用户请检查网络或代理设置\n\n'
            '翻译结果仅供参考，建议人工校对重要内容'
        )
    
    def show_tutorial(self):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle('BB Typer - 使用教程')
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            '<h3>🌟 一键翻译，无缝运营海外社区</h3>'
            '<p>专为<b>海外游戏社区运营</b>打造的智能翻译工具，'
            '让每条回复都像本地人写的一样自然。</p>'
            '<hr>'
            '<h4>✨ 核心功能</h4>'
            '<p><b>🔄 智能双向翻译</b><br>'
            '在聊天对话框中输入文字，按下快捷键直接选中并转换<br>'
            '再次按下快捷键，自动转换回简体中文</p>'
            '<p><b>🇹🇼 台湾/香港本地化</b><br>'
            '不是简单繁简转换！内置 <b>1600+ 台湾词典</b>、<b>1100+ 香港词典</b><br>'
            '“卧槽”→“靠北”、“服务器”→“伺服器”、“充值”→“傲值”<br>'
            '再经 AI 润色，语气像本地人发文一样自然</p>'
            '<p><b>🌍 多语言支持</b><br>'
            '日语、韩语、英语、泰语、法语，覆盖主流市场</p>'
            '<p><b>⚡ 快捷回复模板</b><br>'
            '预设公告/回复/致歉/问候等场景模板，一键复制发送<br>'
            '支持自定义模板、导入导出，团队共享</p>'
            '<hr>'
            '<h4>🚀 使用方法</h4>'
            '<p><b>1.</b> 选择目标语言<br>'
            '<b>2.</b> 在对话框中输入文字，按下快捷键即可选中并转换<br>'
            '<b>3.</b> 再次按下快捷键，直接转换回简体中文</p>'
        )
        msg.exec()

    def open_feedback(self):
        import webbrowser
        webbrowser.open('https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=8b2rdb48-2c41-4de2-ac3d-448828648b5f')

    def check_for_updates(self):
        """Check GitHub Releases for new version"""
        import threading
        def _check():
            try:
                url = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'
                req = urllib.request.Request(url)
                req.add_header('Accept', 'application/vnd.github.v3+json')
                req.add_header('User-Agent', 'BB-Typer')
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    latest = data.get('tag_name', '').lstrip('v')
                    if latest and latest != APP_VERSION:
                        download_url = data.get('html_url', '')
                        self._update_info = {
                            'version': latest,
                            'url': download_url,
                            'body': data.get('body', '')
                        }
                        # Emit signal to show dialog on main thread
                        QTimer.singleShot(0, self._show_update_dialog)
            except Exception:
                pass  # Silent fail, don't bother user
        threading.Thread(target=_check, daemon=True).start()

    def _show_update_dialog(self):
        info = getattr(self, '_update_info', None)
        if not info:
            return
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle('发现新版本')
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            f'<b>发现新版本 v{info["version"]}</b><br><br>'
            f'当前版本：v{APP_VERSION}<br>'
            f'最新版本：v{info["version"]}<br><br>'
            '点击「下载更新」跳转到下载页面'
        )
        download_btn = msg.addButton('下载更新', QMessageBox.ButtonRole.AcceptRole)
        msg.addButton('稍后再说', QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        if msg.clickedButton() == download_btn:
            import webbrowser
            webbrowser.open(info['url'])
    def toggle_ai_polish(self):
        current = self.config.get('llm_polish', True)
        self.config['llm_polish'] = not current
        save_config(self.config)
        self.update_ai_status()

    def update_ai_status(self):
        lang_key = self.config.get('target_lang', 'zh-TW')
        lang_config = TARGET_LANGUAGES.get(lang_key, TARGET_LANGUAGES['zh-TW'])
        supports_polish = lang_config[2]  # True = 支持本地管道+AI润色
        enabled = self.config.get('llm_polish', True)
        t = THEMES['light']

        if not supports_polish:
            # 该语言不支持 AI 润色
            self.ai_status_lbl.setText('➖ 不适用')
            self.ai_status_lbl.setStyleSheet('color: #999999; font-size: 11px;')
            self.ai_toggle_btn.setText('不适用')
            self.ai_toggle_btn.setEnabled(False)
            self.ai_toggle_btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {t['card']};
                    color: #BBBBBB;
                    border: 1px solid {t['border']};
                    border-radius: 6px;
                    font-size: 11px;
                    padding: 2px 10px;
                }}
            ''')
        elif enabled:
            self.ai_toggle_btn.setEnabled(True)
            self.ai_status_lbl.setText('✅ 已开启')
            self.ai_status_lbl.setStyleSheet('color: #07C160; font-size: 11px;')
            self.ai_toggle_btn.setText('关闭')
            self.ai_toggle_btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {t['card']};
                    color: {t['text_secondary']};
                    border: 1px solid {t['border']};
                    border-radius: 6px;
                    font-size: 11px;
                    padding: 2px 10px;
                }}
                QPushButton:hover {{ border-color: {t['danger']}; color: {t['danger']}; }}
            ''')
        else:
            self.ai_toggle_btn.setEnabled(True)
            self.ai_status_lbl.setText('⚪ 已关闭')
            self.ai_status_lbl.setStyleSheet('color: #999999; font-size: 11px;')
            self.ai_toggle_btn.setText('开启')
            self.ai_toggle_btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {t['accent']};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 11px;
                    padding: 2px 10px;
                }}
                QPushButton:hover {{ background-color: {t['accent_hover']}; }}
            ''')

    def show_ai_help(self):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle('AI 润色说明')
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            '<b>什么是 AI 润色？</b><br><br>'
            '台湾/香港繁体模式下，翻译结果会经过 AI 进一步润色，<br>'
            '让文字更像本地人写的，而不是生硬的机器翻译。<br><br>'
            '<b>效果对比：</b><br>'
            '│ 无润色：親愛的玩家們，伺服器<b>將於</b>今日進行維護更新<br>'
            '│ 有润色：各位玩家們，伺服器今天<b>會</b>進行維護更新<b>嗔！</b><br><br>'
            '│ 无润色：靠北這個 bug 也太<b>離譜</b>了吧<br>'
            '│ 有润色：靠北這個 bug 也太<b>扯</b>了吧<br><br>'
            '│ 无润色：這個活動太<b>強</b>了，獎勵超級豐厚<br>'
            '│ 有润色：這個活動 <b>hen 讚欸</b>，獎品超豐厚，大家快來<b>參加啦！</b><br><br>'
            '<b>适用范围：</b><br>'
            '✅ 台湾繁体、香港繁体：自动润色<br>'
            'ℹ️ 日语、韩语、英语、泰语、法语：暂不适用'
        )
        msg.exec()

    def on_lang_changed(self, index):
        lang_key = self.lang_combo.itemData(index)
        self.config['target_lang'] = lang_key
        # 台湾/香港自动开启 AI 润色
        lang_config = TARGET_LANGUAGES.get(lang_key)
        if lang_config and lang_config[2]:
            self.config['llm_polish'] = True
        save_config(self.config)
        self.update_timezone_display()
        self.update_ai_status()

    def update_timezone_display(self):
        time_strs = []
        # Always show Beijing time
        beijing_time = get_timezone_time('Asia/Shanghai')
        time_strs.append(f'🇨🇳 北京 {beijing_time}')
        # Show target language city time
        target_lang = self.config.get('target_lang', 'zh-TW')
        lang_city = LANG_TIMEZONE_MAP.get(target_lang)
        if lang_city and lang_city[1] != 'Asia/Shanghai':
            city_name, tz_name, flag = lang_city
            city_time = get_timezone_time(tz_name)
            time_strs.append(f'{flag} {city_name} {city_time}')
        self.timezone_label.setText(' | '.join(time_strs))

    def update_key_display(self, key_str: str):
        self.key_count += 1
    
    def update_conversion_display(self, original: str, converted: str):
        try:
            orig_display = original[:50] + '...' if len(original) > 50 else original
            conv_display = converted[:50] + '...' if len(converted) > 50 else converted
            self.preview_original.setText(f'原文: {orig_display}')
            self.preview_converted.setText(f'转换: {conv_display}')
        except Exception as e:
            print(f'[显示错误] {e}')

    def check_google_connectivity(self):
        def _check():
            try:
                url = 'https://translate.googleapis.com/translate_a/single'
                params = urllib.parse.urlencode({'client': 'gtx', 'sl': 'zh-CN', 'tl': 'en', 'dt': 't', 'q': 'ok'})
                req = urllib.request.Request(f'{url}?{params}')
                req.add_header('User-Agent', 'Mozilla/5.0')
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        self.signal.google_status.emit(True)
                    else:
                        self.signal.google_status.emit(False)
            except Exception:
                self.signal.google_status.emit(False)
        Thread(target=_check, daemon=True).start()
    
    def update_google_status(self, connected: bool):
        t = THEMES['light']
        try:
            if connected:
                self.google_status_label.setText('🟢 Google已连接')
                self.google_status_label.setStyleSheet(f'color: {t["accent"]};')
            else:
                self.google_status_label.setText('🔴 Google未连接')
                self.google_status_label.setStyleSheet(f'color: {t["danger"]};')
        except Exception as e:
            print(f'[Google状态错误] {e}')

    def load_templates_ui(self):
        t = THEMES['light']
        templates = self.config.get('quick_templates', DEFAULT_QUICK_TEMPLATES)
        
        self.templates_tab.clear()
        
        for category, items in templates.items():
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet('QScrollArea { border: none; background-color: transparent; }')
            
            container = QWidget()
            grid = QGridLayout(container)
            grid.setSpacing(4)
            grid.setContentsMargins(4, 4, 4, 4)
            
            for i, template in enumerate(items):
                btn = TemplateButton(template['name'], template['text'])
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(f'''
                    QPushButton {{
                        background-color: {t['card']};
                        color: {t['text']};
                        border: 1px solid {t['border']};
                        border-radius: 8px;
                        padding: 4px 8px;
                        font-size: 12px;
                        text-align: left;
                    }}
                    QPushButton:hover {{
                        background-color: {t['card_alt']};
                        border-color: {t['accent']};
                        color: {t['accent']};
                    }}
                ''')
                btn.clicked.connect(lambda checked, t=template['text']: self.use_template(t))
                row = i // 4
                col = i % 4
                grid.addWidget(btn, row, col)
            
            scroll.setWidget(container)
            tab_name = category.split(' ')[-1] if ' ' in category else category
            self.templates_tab.addTab(scroll, tab_name)
    
    def filter_templates(self, text: str):
        """Filter template buttons by search text"""
        search_text = text.strip().lower()
        for tab_index in range(self.templates_tab.count()):
            scroll = self.templates_tab.widget(tab_index)
            if scroll is None:
                continue
            container = scroll.widget()
            if container:
                grid = container.layout()
                if grid:
                    for i in range(grid.count()):
                        item = grid.itemAt(i)
                        widget = item.widget() if item else None
                        if widget is not None:
                            if not search_text:
                                widget.show()
                            else:
                                name = widget.text().lower()
                                tip = (getattr(widget, '_full_text', '') or widget.toolTip() or '').lower()
                                widget.setVisible(search_text in name or search_text in tip)
    
    def use_template(self, template_text: str):
        target_lang = self.config.get('target_lang', 'zh-TW')
        lang_config = TARGET_LANGUAGES.get(target_lang, TARGET_LANGUAGES['zh-TW'])
        _, google_lang_code, has_opencc_fallback = lang_config

        converted = google_translate(template_text, google_lang_code, 'zh-CN')
        if not converted and has_opencc_fallback:
            text_with_custom = template_text
            for simplified, taiwan in self.custom_dict.items():
                text_with_custom = text_with_custom.replace(simplified, taiwan)
            text_with_patterns = apply_sentence_patterns(text_with_custom)
            converted = self.converter.convert(text_with_patterns)
        elif not converted:
            converted = template_text

        if target_lang == 'zh-TW' and self.config.get('llm_polish', True):
            converted = llm_polish(converted)
        set_clipboard(converted)

        self.signal.conversion_done.emit(template_text, converted)

        chinese_count = sum(1 for c in template_text if '\u4e00' <= c <= '\u9fff')
        if chinese_count > 0:
            self.stats.add_chars(chinese_count)
            self.signal.stats_updated.emit()

        self.history.add(template_text, converted, target_lang)
        self.update_history_display()
        # Show '已复制' tooltip near cursor
        QToolTip.showText(QCursor.pos(), '✓ 已复制', self, self.rect(), 2000)

    def add_custom_template(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('新增模板')
        dialog.setFixedSize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        cat_label = QLabel('选择分类:')
        layout.addWidget(cat_label)
        
        cat_combo = QComboBox()
        templates = self.config.get('quick_templates', DEFAULT_QUICK_TEMPLATES)
        for cat in templates.keys():
            cat_combo.addItem(cat)
        cat_combo.addItem('➕ 新增分类...')
        layout.addWidget(cat_combo)
        
        name_label = QLabel('模板名称:')
        layout.addWidget(name_label)
        name_input = QLineEdit()
        name_input.setPlaceholderText('例如: 感谢回复')
        layout.addWidget(name_input)
        
        text_label = QLabel('模板内容:')
        layout.addWidget(text_label)
        text_input = QTextEdit()
        text_input.setPlaceholderText('输入模板内容...')
        layout.addWidget(text_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec_() == QDialog.Accepted:
            name = name_input.text().strip()
            text = text_input.toPlainText().strip()
            
            if not name or not text:
                QMessageBox.warning(self, '错误', '请填写模板名称和内容')
                return
            
            category = cat_combo.currentText()
            
            if category == '➕ 新增分类...':
                new_cat, ok = QInputDialog.getText(self, '新增分类', '输入分类名称:')
                if ok and new_cat.strip():
                    category = new_cat.strip()
                else:
                    return
            
            templates = self.config.get('quick_templates', DEFAULT_QUICK_TEMPLATES.copy())
            if category not in templates:
                templates[category] = []
            
            templates[category].append({'name': name, 'text': text})
            self.config['quick_templates'] = templates
            save_config(self.config)
            
            self.load_templates_ui()
            
            QMessageBox.information(self, '成功', f'已新增模板「{name}」到「{category}」')
    
    def import_templates(self):
        file_path, _ = QFileDialog.getOpenFileName(self, '导入模板', '', 'JSON Files (*.json)')
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    imported = json.load(f)
                self.config['quick_templates'] = imported
                save_config(self.config)
                self.load_templates_ui()
                QMessageBox.information(self, '成功', '模板导入成功')
            except Exception as e:
                QMessageBox.warning(self, '错误', f'导入失败: {str(e)}')
    
    def export_templates(self):
        file_path, _ = QFileDialog.getSaveFileName(self, '导出模板', 'templates.json', 'JSON Files (*.json)')
        if file_path:
            try:
                templates = self.config.get('quick_templates', DEFAULT_QUICK_TEMPLATES)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(templates, f, ensure_ascii=False, indent=2)
                QMessageBox.information(self, '成功', '模板导出成功')
            except Exception as e:
                QMessageBox.warning(self, '错误', f'导出失败: {str(e)}')
    
    def update_history_display(self):
        try:
            self.history_list.clear()
            for item in self.history.get_all()[:20]:
                orig = item.get('original', '')[:30]
                trans = item.get('translated', '')[:30]
                if len(item.get('original', '')) > 30:
                    orig += '...'
                if len(item.get('translated', '')) > 30:
                    trans += '...'
                list_item = QListWidgetItem(f'{orig} → {trans}')
                list_item.setData(Qt.ItemDataRole.UserRole, item.get('translated', ''))
                self.history_list.addItem(list_item)
        except Exception as e:
            print(f'[历史显示错误] {e}')
    def copy_history_item(self, item):
        text = item.data(Qt.ItemDataRole.UserRole)
        set_clipboard(text)
        QMessageBox.information(self, '成功', '已复制到剪贴板')
    
    def clear_history(self):
        self.history.clear()
        self.update_history_display()
    
    def on_key_press(self, key):
        try:
            key_str = key.char if hasattr(key, 'char') and key.char else str(key)
        except Exception:
            key_str = str(key)
        self.signal.key_pressed.emit(key_str)
        
        if key == Key.cmd or key == Key.cmd_r:
            self.cmd_pressed = True
            return
        if key == Key.ctrl or key == Key.ctrl_r:
            self.ctrl_pressed = True
            return
        if key == Key.alt or key == Key.alt_r:
            self.alt_pressed = True
            return
        if key == Key.shift or key == Key.shift_r:
            self.shift_pressed = True
            return
        
        if self.recording_hotkey and hasattr(key, 'char') and key.char:
            modifier = None
            if self.cmd_pressed:
                modifier = 'cmd'
            elif self.ctrl_pressed:
                modifier = 'ctrl'
            elif self.alt_pressed:
                modifier = 'alt'

            if modifier:
                self.pending_hotkey = (modifier, key.char.lower())
                modifier_symbols = {
                    'cmd': '⌘',
                    'ctrl': '⌃',
                    'alt': '⌥',
                    'shift': '⇧'
                }
                self.hotkey_value_label.setText(f"{modifier_symbols.get(modifier, modifier)}+{key.char.upper()}")
            return
        
        if not self.is_enabled:
            return
        
        hotkey = self.config.get('hotkey', DEFAULT_HOTKEY)
        modifier = hotkey.get('modifier', 'cmd' if IS_MACOS else 'ctrl')
        target_key = hotkey.get('key', 'a')
        
        modifier_pressed = False
        if modifier == 'cmd' and self.cmd_pressed:
            modifier_pressed = True
        elif modifier == 'ctrl' and self.ctrl_pressed:
            modifier_pressed = True
        elif modifier == 'alt' and self.alt_pressed:
            modifier_pressed = True
        
        # Only trigger if EXACTLY the configured modifier is pressed (no extra modifiers)
        extra_modifiers = False
        if modifier != 'cmd' and self.cmd_pressed:
            extra_modifiers = True
        if modifier != 'ctrl' and self.ctrl_pressed:
            extra_modifiers = True
        if modifier != 'alt' and self.alt_pressed:
            extra_modifiers = True
        if self.shift_pressed:
            extra_modifiers = True
        
        if modifier_pressed and not extra_modifiers and hasattr(key, 'char') and key.char == target_key:
            Thread(target=self.do_convert_async, daemon=True).start()
    
    def on_key_release(self, key):
        if key == Key.cmd or key == Key.cmd_r:
            self.cmd_pressed = False
        if key == Key.ctrl or key == Key.ctrl_r:
            self.ctrl_pressed = False
        if key == Key.alt or key == Key.alt_r:
            self.alt_pressed = False
        if key == Key.shift or key == Key.shift_r:
            self.shift_pressed = False
    
    def do_convert_async(self):
        if not self.convert_lock.acquire(blocking=False):
            return
        
        try:
            time.sleep(0.1)
            
            mod_key = get_modifier_key()
            self.keyboard_controller.press(mod_key)
            self.keyboard_controller.tap('c')
            self.keyboard_controller.release(mod_key)
            time.sleep(0.05)
            
            original_text = get_clipboard()
            
            if original_text.strip():
                target_lang = self.config.get('target_lang', 'zh-TW')
                lang_config = TARGET_LANGUAGES.get(target_lang, TARGET_LANGUAGES['zh-TW'])
                _, google_lang_code, has_opencc_fallback = lang_config
                
                # 智能双向翻译：自动检测文本语言
                if is_simplified_chinese(original_text):
                    # 简体中文 → 目标语言
                    if has_opencc_fallback:
                        # 繁体中文（TW/HK）：词典替换 + 句式调整 + OpenCC 简转繁
                        if target_lang == 'zh-HK':
                            cur_dict = self.custom_dict_hk
                            cur_converter = self.converter_hk
                        else:
                            cur_dict = self.custom_dict
                            cur_converter = self.converter
                        text_with_custom = original_text
                        for src, dst in cur_dict.items():
                            text_with_custom = text_with_custom.replace(src, dst)
                        text_with_patterns = apply_sentence_patterns(text_with_custom)
                        converted_text = cur_converter.convert(text_with_patterns)
                    else:
                        # 其他语言：直接走 Google 翻译
                        converted_text = google_translate(original_text, google_lang_code, 'zh-CN')
                        if not converted_text:
                            converted_text = original_text
                    
                    # LLM 润色（TW/HK 各用各的 prompt）
                    if target_lang in ('zh-TW', 'zh-HK') and self.config.get('llm_polish', True):
                        hk_prompt = LLM_SYSTEM_PROMPT_HK if target_lang == 'zh-HK' else ''
                        converted_text = llm_polish(converted_text, hk_prompt)
                    # 缓存翻译结果，用于反向精确还原
                    if converted_text != original_text:
                        self.translation_cache[converted_text.strip()] = original_text
                        # 限制缓存大小，保留最近200条
                        if len(self.translation_cache) > 200:
                            oldest_key = next(iter(self.translation_cache))
                            del self.translation_cache[oldest_key]
                else:
                    # 目标语言 → 简体中文：优先查缓存精确还原
                    cached = self.translation_cache.get(original_text.strip())
                    if cached:
                        converted_text = cached
                        # 使用后从缓存移除（一次性还原）
                        del self.translation_cache[original_text.strip()]
                    else:
                        converted_text = google_translate(original_text, 'zh-CN', google_lang_code)
                        if not converted_text:
                            converted_text = original_text
                if converted_text != original_text:
                    set_clipboard(converted_text)
                    
                    self.keyboard_controller.press(mod_key)
                    self.keyboard_controller.tap('v')
                    self.keyboard_controller.release(mod_key)
                    
                    self.signal.conversion_done.emit(original_text, converted_text)
                    
                    chinese_count = sum(1 for c in original_text if '\u4e00' <= c <= '\u9fff')
                    if chinese_count > 0:
                        self.stats.add_chars(chinese_count)
                        self.signal.stats_updated.emit()
                    
                    self.history.add(original_text, converted_text, target_lang)
                    self.signal.history_updated.emit()
                    
        except Exception as e:
            print(f'[转换错误] {e}')
        finally:
            self.convert_lock.release()
    
    def closeEvent(self, a0):
        if a0 is not None:
            a0.ignore()
        self.hide()
        self.tray_icon.showMessage(
            'BB Typer',
            '程序已最小化到系统托盘，继续在后台运行',
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
    
    def quit_app(self):
        self.google_timer.stop()
        self.timezone_timer.stop()
        self.stop_listening()
        self.tray_icon.hide()
        QApplication.quit()


def main():
    # Single instance lock
    import fcntl
    lock_fp = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fp.write(str(os.getpid()))
        lock_fp.flush()
    except IOError:
        print('程序已在运行中，激活现有窗口')
        sys.exit(0)
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setQuitOnLastWindowClosed(False)
    
    font = QFont('PingFang SC', 13)
    app.setFont(font)
    
    window = TaiwanConverterWindow()
    window.show()
    
    ret = app.exec_()
    
    # Release lock
    fcntl.flock(lock_fp, fcntl.LOCK_UN)
    lock_fp.close()
    try:
        LOCK_FILE.unlink()
    except:
        pass
    sys.exit(ret)


if __name__ == '__main__':
    main()
