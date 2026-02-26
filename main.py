#!/usr/bin/env python3
"""
海外社区运营小助理 - 选中文字后按快捷键自动转换为目标语言
Overseas Community Assistant - Auto-convert selected text to target language via hotkey
"""

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
    QListWidget, QListWidgetItem, QFileDialog, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPainter, QColor

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
    user32 = ctypes.windll.user32

# Cross-platform clipboard
try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


# Data files
DATA_FILE = Path(__file__).parent / 'stats.json'
CUSTOM_DICT_FILE = Path(__file__).parent / 'custom_dict.txt'
CONFIG_FILE = Path(__file__).parent / 'config.json'
HISTORY_FILE = Path(__file__).parent / 'history.json'
LOCK_FILE = Path(__file__).parent / '.app.lock'
SENSITIVE_WORDS_CACHE_FILE = Path(__file__).parent / 'sensitive_words_cache.json'

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
    'zh-TW': ('🇹🇼 台湾繁体', 'zh-TW', True),
    'zh-HK': ('🇭🇰 香港繁体', 'zh-TW', False),  # Google Translate 不支持 zh-HK，使用 zh-TW 近似
    'en': ('🇬🇧 英语', 'en', False),
    'ja': ('🇯🇵 日语', 'ja', False),
    'ko': ('🇰🇷 韩语', 'ko', False),
    'fr': ('🇫🇷 法语', 'fr', False),
    'de': ('🇩🇪 德语', 'de', False),
    'it': ('🇮🇹 意大利语', 'it', False),
    'pt': ('🇧🇷 葡萄牙语', 'pt', False),
    'ru': ('🇷🇺 俄语', 'ru', False),
    'ar': ('🇸🇦 阿拉伯语', 'ar', False),
    'th': ('🇹🇭 泰语', 'th', False),
    'vi': ('🇻🇳 越南语', 'vi', False),
    'id': ('🇮🇩 印尼语', 'id', False),
    'ms': ('🇲🇾 马来语', 'ms', False),
    'tl': ('🇵🇭 菲律宾语', 'tl', False),
    'my': ('🇲🇲 缅甸语', 'my', False),
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

SENSITIVE_WORDS = {
    'political': ['习近平', '天安门', '六四', '法轮功', '台独', '藏独'],
    'religious': ['真主', '穆罕默德', '清真'],
    'cultural': ['支那', '鬼子', '棒子'],
}

SENSITIVE_WORDS_URLS = [
    ('political', 'https://raw.githubusercontent.com/fwwdn/sensitive-stop-words/master/政治类.txt'),
    ('sexual', 'https://raw.githubusercontent.com/fwwdn/sensitive-stop-words/master/色情类.txt'),
    ('political2', 'https://raw.githubusercontent.com/selfcs/stop-and-sensitive-words/main/%E6%94%BF%E6%B2%BB%E6%95%8F%E6%84%9F%E8%AF%8D.txt'),
    ('sexual2', 'https://raw.githubusercontent.com/selfcs/stop-and-sensitive-words/main/%E8%89%B2%E6%83%85%E6%95%8F%E6%84%9F%E8%AF%8D.txt'),
    ('illegal', 'https://raw.githubusercontent.com/selfcs/stop-and-sensitive-words/main/%E8%BF%9D%E6%B3%95%E6%95%8F%E6%84%9F%E8%AF%8D.txt'),
]

# Language -> timezone city mapping
LANG_TIMEZONE_MAP = {
    'zh-TW': ('台北', 'Asia/Taipei', '🇹🇼'),
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

PLATFORM_LIMITS = {
    'Discord': 2000,
    'Twitter': 280,
    'WeChat': 500,
    'LINE': 5000,
}

THEMES = {
    'light': {
        'bg': '#EDEDED',
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
    },
    'dark': {
        'bg': '#1E1E1E',
        'card': '#2D2D2D',
        'card_alt': '#363636',
        'text': '#E0E0E0',
        'text_secondary': '#888888',
        'border': '#404040',
        'hover': '#3A3A3A',
        'accent': '#07C160',
        'accent_hover': '#06AD56',
        'link': '#7A9EC7',
        'danger': '#FA5151',
        'danger_hover': '#FF6B6B',
        'tab_bg': '#252525',
        'tab_selected_bg': '#2D2D2D',
        'input_bg': '#363636',
        'disabled_bg': '#555555',
        'disabled_hover': '#666666',
    }
}
PIE_BASE_URL = os.environ.get('PIE_BASE_URL', 'http://8.222.169.8:3000')
PIE_TOKEN = os.environ.get('PIE_TOKEN', '')
LLM_MODEL = 'gemini-2.5-flash-lite'

LLM_SYSTEM_PROMPT = '''你是一個台灣繁體中文潤色助手。你的任務是將已經初步轉換的繁體中文文字，潤色成更自然、更道地的台灣口語表達。

規則：
1. 保持原意不變，只調整用詞和語氣
2. 使用台灣人日常說話的方式
3. 適當加入台灣語氣詞（喔、啦、欸、齁、蛤）
4. 不要過度修改，保持自然
5. 不要加引號、不要解釋、不要加任何前綴後綴
6. 直接輸出潤色後的文字，不要輸出其他任何內容
7. 如果原文已經很自然，就直接輸出原文'''


# Global sensitive words list
LOADED_SENSITIVE_WORDS = []
SENSITIVE_WORDS_LOCK = Lock()

def load_sensitive_words():
    """Load sensitive words from cache or fetch from online sources"""
    # Check cache first
    if SENSITIVE_WORDS_CACHE_FILE.exists():
        try:
            with open(SENSITIVE_WORDS_CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                cache_time = cache_data.get('timestamp', 0)
                # Check if cache is less than 7 days old
                if time.time() - cache_time < 7 * 24 * 3600:
                    return cache_data.get('words', [])
        except Exception as e:
            print(f'[Cache read error] {e}')
    
    # Fetch from online sources
    all_words = set()
    
    # Add hardcoded base words
    for words_list in SENSITIVE_WORDS.values():
        all_words.update(words_list)
    
    # Fetch from URLs
    for category, url in SENSITIVE_WORDS_URLS:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8')
                for line in content.split('\n'):
                    word = line.strip().rstrip(',')
                    if word:
                        all_words.add(word)
            print(f'[Sensitive words] Loaded {category} from online')
        except Exception as e:
            print(f'[Sensitive words] Failed to load {category}: {e}')
    
    # Convert to list
    words_list = list(all_words)
    
    # Save to cache
    try:
        cache_data = {
            'timestamp': time.time(),
            'words': words_list
        }
        with open(SENSITIVE_WORDS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False)
        print(f'[Sensitive words] Cached {len(words_list)} words')
    except Exception as e:
        print(f'[Cache write error] {e}')
    
    return words_list


def fetch_sensitive_words_async(callback=None):
    """Fetch sensitive words in background thread"""
    def _fetch():
        words = load_sensitive_words()
        if callback:
            callback(words)
    
    thread = Thread(target=_fetch, daemon=True)
    thread.start()

def apply_sentence_patterns(text: str) -> str:
    for pattern, replacement in SENTENCE_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


def llm_polish(text: str) -> str:
    if not PIE_TOKEN:
        return text
    
    try:
        url = f'{PIE_BASE_URL}/v1/app/chat/completions'
        payload = json.dumps({
            'model': LLM_MODEL,
            'messages': [
                {'role': 'system', 'content': LLM_SYSTEM_PROMPT},
                {'role': 'user', 'content': text}
            ],
            'max_tokens': 500,
            'temperature': 0.3
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Authorization', f'Bearer {PIE_TOKEN}')
        
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            polished = result['choices'][0]['message']['content'].strip()
            if len(polished) > len(text) * 3 or len(polished) < len(text) * 0.3:
                return text
            return polished
    except Exception:
        return text


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
    if HAS_PYPERCLIP:
        return pyperclip.paste()
    elif IS_MACOS:
        result = subprocess.run(['pbpaste'], capture_output=True, text=True, timeout=1)
        return result.stdout
    elif IS_WINDOWS:
        result = subprocess.run(['powershell', '-command', 'Get-Clipboard'], capture_output=True, text=True, timeout=1)
        return result.stdout.rstrip('\r\n')
    return ""


def set_clipboard(text: str):
    if HAS_PYPERCLIP:
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
        'translate_direction': 'cn_to_foreign',
        'llm_polish': True,
        'platform': 'Discord',
        'sensitive_words': SENSITIVE_WORDS,
        'theme': 'light'
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


def load_custom_dict() -> dict:
    mappings = {}
    if CUSTOM_DICT_FILE.exists():
        for line in CUSTOM_DICT_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split('\t')
                if len(parts) == 2:
                    mappings[parts[0]] = parts[1]
    sorted_mappings = dict(sorted(mappings.items(), key=lambda x: len(x[0]), reverse=True))
    return sorted_mappings


def detect_sensitive_words(text: str, sensitive_dict: dict) -> list:
    found = []
    
    # Use loaded online words if available
    global LOADED_SENSITIVE_WORDS
    with SENSITIVE_WORDS_LOCK:
        words_to_check = LOADED_SENSITIVE_WORDS if LOADED_SENSITIVE_WORDS else []
    
    # Also check custom words from config
    for category, words in sensitive_dict.items():
        words_to_check.extend(words)
    
    # Check all words
    for word in words_to_check:
        if word and word in text:
            found.append(word)
    
    return found


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
    sensitive_warning = pyqtSignal(list)
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


class SettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.config = config
        self.parent_window = parent
        self.setWindowTitle('设置')
        self.setFixedSize(500, 600)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        tabs = QTabWidget()
        tabs.addTab(self.create_hotkey_tab(), '快捷键')
        tabs.addTab(self.create_appearance_tab(), '外观')
        tabs.addTab(self.create_ai_tab(), 'AI 润色')
        # timezone tab removed - timezone now auto-follows language selection
        tabs.addTab(self.create_platform_tab(), '平台限制')
        tabs.addTab(self.create_sensitive_tab(), '敏感词')
        
        layout.addWidget(tabs)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def create_hotkey_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        label = QLabel('当前快捷键: ' + self.parent_window.format_hotkey())
        layout.addWidget(label)
        
        btn = QPushButton('点击设置新快捷键')
        btn.clicked.connect(self.parent_window.start_recording_hotkey)
        layout.addWidget(btn)
        
        layout.addStretch()
        return widget
    
    def create_appearance_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        label = QLabel('主题设置:')
        layout.addWidget(label)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItem('浅色模式', 'light')
        self.theme_combo.addItem('深色模式', 'dark')
        
        # Pre-select based on current theme
        current_theme = self.parent_window.current_theme
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == current_theme:
                self.theme_combo.setCurrentIndex(i)
                break
        
        layout.addWidget(self.theme_combo)
        layout.addStretch()
        return widget
    
    def create_ai_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        self.ai_checkbox = QCheckBox('AI 润色开启 (仅适用于台湾繁体)')
        self.ai_checkbox.setChecked(self.config.get('llm_polish', True))
        layout.addWidget(self.ai_checkbox)
        
        layout.addStretch()
        return widget
    
    # create_timezone_tab removed - timezone now auto-follows language selection
    
    def create_platform_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        label = QLabel('选择平台字数限制:')
        layout.addWidget(label)
        
        self.platform_combo = QComboBox()
        for platform, limit in PLATFORM_LIMITS.items():
            self.platform_combo.addItem(f'{platform} ({limit} 字)', platform)
        
        current_platform = self.config.get('platform', 'Discord')
        for i in range(self.platform_combo.count()):
            if self.platform_combo.itemData(i) == current_platform:
                self.platform_combo.setCurrentIndex(i)
                break
        
        layout.addWidget(self.platform_combo)
        layout.addStretch()
        return widget
    
    def create_sensitive_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        label = QLabel('敏感词管理 (每行一个):')
        layout.addWidget(label)
        
        self.sensitive_text = QTextEdit()
        sensitive_dict = self.config.get('sensitive_words', SENSITIVE_WORDS)
        all_words = []
        for words in sensitive_dict.values():
            all_words.extend(words)
        self.sensitive_text.setPlainText('\n'.join(all_words))
        layout.addWidget(self.sensitive_text)
        
        # Add refresh button
        refresh_btn = QPushButton('🔄 更新词库')
        refresh_btn.clicked.connect(self.refresh_sensitive_words)
        layout.addWidget(refresh_btn)
        
        layout.addStretch()
        return widget
    
    def refresh_sensitive_words(self):
        """Refresh sensitive words from online sources"""
        from PyQt5.QtWidgets import QMessageBox
        
        # Delete cache to force refresh
        if SENSITIVE_WORDS_CACHE_FILE.exists():
            SENSITIVE_WORDS_CACHE_FILE.unlink()
        
        # Show loading message
        QMessageBox.information(self, '更新词库', '正在从在线源更新敏感词库，请稍候...')
        
        # Fetch in background
        def on_loaded(words):
            self.parent_window.on_sensitive_words_loaded(words)
            QMessageBox.information(self, '更新完成', f'已更新 {len(words)} 个敏感词')
        
        fetch_sensitive_words_async(on_loaded)
    
    def accept(self):
        self.config['llm_polish'] = self.ai_checkbox.isChecked()

        self.config['platform'] = self.platform_combo.currentData()
        
        # Handle theme change
        new_theme = self.theme_combo.currentData()
        if new_theme != self.parent_window.current_theme:
            self.parent_window.current_theme = new_theme
            self.config['theme'] = new_theme
            self.parent_window.apply_theme()
            self.parent_window.load_templates_ui()
        
        words_text = self.sensitive_text.toPlainText().strip()
        if words_text:
            words = [w.strip() for w in words_text.split('\n') if w.strip()]
            self.config['sensitive_words'] = {'custom': words}
        
        save_config(self.config)
        super().accept()


class TaiwanConverterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.converter = OpenCC('s2twp')
        self.custom_dict = load_custom_dict()
        self.keyboard_controller = Controller()
        self.stats = StatsManager()
        self.config = load_config()
        self.current_theme = self.config.get('theme', 'light')
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
        
        self.signal = KeyboardSignal()
        self.signal.stats_updated.connect(self.update_stats_display)
        self.signal.key_pressed.connect(self.update_key_display)
        self.signal.conversion_done.connect(self.update_conversion_display)
        self.signal.google_status.connect(self.update_google_status)
        self.signal.sensitive_warning.connect(self.show_sensitive_warning)
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
        
        # Fetch sensitive words on startup
        fetch_sensitive_words_async(self.on_sensitive_words_loaded)
        
        # Timer to refresh sensitive words every 24 hours
        self.sensitive_words_timer = QTimer()
        self.sensitive_words_timer.timeout.connect(lambda: fetch_sensitive_words_async(self.on_sensitive_words_loaded))
        self.sensitive_words_timer.start(24 * 3600 * 1000)  # 24 hours in milliseconds
    
    def init_ui(self):
        self.setWindowTitle('🔧 海外社区运营小助理')
        self.setFixedSize(420, 700)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.top_bar = self.create_top_bar()
        main_layout.addWidget(self.top_bar)
        
        self.action_row = self.create_action_row()
        main_layout.addWidget(self.action_row)
        
        self.timezone_bar = self.create_timezone_bar()
        main_layout.addWidget(self.timezone_bar)
        
        self.settings_row = self.create_settings_button()
        main_layout.addWidget(self.settings_row)
        
        content_tabs = self.create_content_tabs()
        main_layout.addWidget(content_tabs, 1)
        self.status_bar_frame = self.create_status_bar()
        main_layout.addWidget(self.status_bar_frame)
    
        self.apply_theme()
    def create_top_bar(self):
        bar = QFrame()
        bar.setFixedHeight(48)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 0, 15, 0)
        
        title = QLabel('🔧 海外社区运营小助理')
        title.setFont(QFont('PingFang SC', 16, QFont.Bold))
        layout.addWidget(title)
        
        layout.addStretch()
        
        
        self.google_status_label = QLabel('🟢 Google已连接')
        self.google_status_label.setFont(QFont('PingFang SC', 12))
        layout.addWidget(self.google_status_label)
        
        return bar
    
    def create_action_row(self):
        row = QFrame()
        row.setFixedHeight(56)
        
        layout = QHBoxLayout(row)
        layout.setContentsMargins(15, 0, 15, 0)
        
        globe_label = QLabel('🌐')
        globe_label.setFont(QFont('PingFang SC', 18))
        layout.addWidget(globe_label)
        
        self.lang_combo = QComboBox()
        self.lang_combo.setFixedWidth(150)
        
        for key, (display_name, _, _) in TARGET_LANGUAGES.items():
            self.lang_combo.addItem(display_name, key)
        
        current_lang = self.config.get('target_lang', 'zh-TW')
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == current_lang:
                self.lang_combo.setCurrentIndex(i)
                break
        
        self.lang_combo.currentIndexChanged.connect(self.on_lang_changed)
        layout.addWidget(self.lang_combo)
        
        convert_label = QLabel(self.format_hotkey() + ' 转换')
        convert_label.setFont(QFont('PingFang SC', 13))
        convert_label.setStyleSheet('color: #999999; margin-left: 10px;')
        layout.addWidget(convert_label)
        
        layout.addStretch()
        
        self.direction_btn = QPushButton('🔄 双向')
        self.direction_btn.setCheckable(True)
        self.direction_btn.setChecked(self.config.get('translate_direction') == 'foreign_to_cn')
        self.direction_btn.clicked.connect(self.toggle_direction)
        layout.addWidget(self.direction_btn)
        
        help_btn = QPushButton('?')
        help_btn.setFixedSize(22, 22)
        help_btn.setStyleSheet('''
            QPushButton {
                font-size: 13px;
                background-color: #D9D9D9;
                color: #999999;
                border: none;
                border-radius: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #07C160;
                color: white;
            }
        ''')
        help_btn.clicked.connect(lambda: QMessageBox.information(self, '双向翻译',
            '默认模式：中文 → 目标语言\n'
            '点击「🔄 双向」按钮开启反向模式：\n'
            '目标语言 → 中文\n\n'
            '例如选择日语时：\n'
            '· 默认：中文输入 → 日语输出\n'
            '· 双向：日语输入 → 中文输出'))
        layout.addWidget(help_btn)
        
        return row
    
    def create_timezone_bar(self):
        bar = QFrame()
        bar.setFixedHeight(36)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 0, 15, 0)
        
        clock_label = QLabel('🕐')
        layout.addWidget(clock_label)
        
        self.timezone_label = QLabel('')
        self.timezone_label.setFont(QFont('PingFang SC', 12))
        layout.addWidget(self.timezone_label)
        
        layout.addStretch()
        
        return bar
    
    def create_settings_button(self):
        bar = QFrame()
        bar.setFixedHeight(44)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 6, 15, 6)
        
        settings_btn = QPushButton('设  置')
        settings_btn.setFixedHeight(32)
        settings_btn.setFixedWidth(390)
        settings_btn.setFont(QFont('PingFang SC', 14))
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.clicked.connect(self.open_settings)
        layout.addWidget(settings_btn)
        
        self.settings_row = bar
        return bar
    
    def create_content_tabs(self):
        """Create main content area with '快速回复' and '翻译历史' tabs"""
        self.content_tabs = QTabWidget()
        self.content_tabs.setStyleSheet('''
            QTabWidget::pane {
                background-color: #FFFFFF;
                border: none;
                border-top: 1px solid #D9D9D9;
            }
            QTabBar::tab {
                background-color: #EDEDED;
                color: #999999;
                padding: 8px 20px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 14px;
            }
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #07C160;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background-color: #D8D8D8;
            }
        ''')
        
        # Tab 1: 快速回复
        templates_widget = self._create_templates_tab()
        self.content_tabs.addTab(templates_widget, '💬 快速回复')
        
        # Tab 2: 翻译历史
        history_widget = self._create_history_tab()
        self.content_tabs.addTab(history_widget, '📋 翻译历史')
        
        return self.content_tabs
    
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

    def create_status_bar(self):
        bar = QFrame()
        bar.setFixedHeight(36)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 0, 15, 0)
        
        # Preview labels (hidden by default)
        self.preview_original = QLabel('')
        self.preview_original.setFont(QFont('PingFang SC', 12))
        self.preview_original.setVisible(False)
        layout.addWidget(self.preview_original)
        
        self.preview_converted = QLabel('')
        self.preview_converted.setFont(QFont('PingFang SC', 12))
        self.preview_converted.setVisible(False)
        layout.addWidget(self.preview_converted)
        
        self.char_count_label = QLabel('')
        self.char_count_label.setFont(QFont('PingFang SC', 12))
        self.char_count_label.setVisible(False)
        layout.addWidget(self.char_count_label)
        
        self.sensitive_warning_label = QLabel('')
        self.sensitive_warning_label.setFont(QFont('PingFang SC', 12))
        self.sensitive_warning_label.setVisible(False)
        layout.addWidget(self.sensitive_warning_label)
        
        self.stats_label = QLabel('今日 0 字 | 累计 0 字')
        self.stats_label.setFont(QFont('PingFang SC', 12))
        layout.addWidget(self.stats_label)
        
        layout.addStretch()
        
        self.toggle_btn = QPushButton('⏸ 暂停')
        self.toggle_btn.clicked.connect(self.toggle_enabled)
        layout.addWidget(self.toggle_btn)
        
        self.update_stats_display()
        
        return bar
    
    
    def apply_theme(self):
        t = THEMES[self.current_theme]
        
        # Main window
        self.setStyleSheet(f'''
            QMainWindow {{
                background-color: {t['bg']};
            }}
            QLabel {{
                color: {t['text']};
            }}
        ''')
        
        # Top bar
        self.top_bar.setStyleSheet(f'background-color: {t["bg"]}; border-bottom: 1px solid {t["border"]};')
        
        
        # Google status label
        if '已连接' in self.google_status_label.text():
            self.google_status_label.setStyleSheet(f'color: {t["accent"]};')
        else:
            self.google_status_label.setStyleSheet(f'color: {t["danger"]};')
        
        # Action row
        self.action_row.setStyleSheet(f'background-color: {t["card"]}; border-bottom: 1px solid {t["border"]};')
        
        # Language combo
        self.lang_combo.setStyleSheet(f'''
            QComboBox {{
                background-color: {t['input_bg']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 14px;
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
        
        # Direction button
        self.direction_btn.setStyleSheet(f'''
            QPushButton {{
                background-color: {t['input_bg']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 5px 15px;
                font-size: 13px;
                color: {t['text']};
            }}
            QPushButton:checked {{
                background-color: {t['accent']};
                color: white;
                border-color: {t['accent']};
            }}
            QPushButton:hover {{
                border-color: {t['accent']};
            }}
        ''')
        
        # Timezone bar
        self.timezone_bar.setStyleSheet(f'background-color: {t["card_alt"]}; border-bottom: 1px solid {t["border"]};')
        self.timezone_label.setStyleSheet(f'color: {t["link"]};')
        
        # Settings row
        self.settings_row.setStyleSheet(f'background-color: {t["card_alt"]}; border-bottom: 1px solid {t["border"]};')
        # Style the settings button inside settings_row
        for btn in self.settings_row.findChildren(QPushButton):
            btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {t['card']};
                    border: 1px solid {t['border']};
                    border-radius: 8px;
                    padding: 6px 16px;
                    font-size: 14px;
                    font-weight: bold;
                    color: {t['text']};
                }}
                QPushButton:hover {{
                    background-color: {t['accent']};
                    color: white;
                    border-color: {t['accent']};
                }}
            ''')
        
        # Content tabs
        self.content_tabs.setStyleSheet(f'''
            QTabWidget::pane {{
                background-color: {t['card']};
                border: none;
                border-top: 1px solid {t['border']};
            }}
            QTabBar::tab {{
                background-color: {t['tab_bg']};
                color: {t['text_secondary']};
                padding: 8px 20px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 14px;
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
        
        # Templates tab
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
        
        # Template search
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
        
        # History list
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
        
        # Status bar
        self.status_bar_frame.setStyleSheet(f'background-color: {t["bg"]};')
        self.stats_label.setStyleSheet(f'color: {t["text_secondary"]};')
        self.preview_original.setStyleSheet(f'color: {t["text_secondary"]};')
        self.preview_converted.setStyleSheet(f'color: {t["text_secondary"]};')
        self.char_count_label.setStyleSheet(f'color: {t["text_secondary"]};')
        self.sensitive_warning_label.setStyleSheet(f'color: {t["danger"]};')
        
        # Toggle button (will be updated by toggle_enabled)
        if self.is_enabled:
            self.toggle_btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {t['accent']};
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 5px 15px;
                    font-size: 13px;
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
                    border-radius: 8px;
                    padding: 5px 15px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: {t['disabled_hover']};
                }}
            ''')
    
    def toggle_theme(self):
        self.current_theme = 'dark' if self.current_theme == 'light' else 'light'
        self.config['theme'] = self.current_theme
        save_config(self.config)
        self.apply_theme()
        self.load_templates_ui()
    
    def init_tray(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QColor('#07C160'))
        painter.setPen(Qt.NoPen)
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
        if reason == QSystemTrayIcon.DoubleClick:
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
        t = THEMES[self.current_theme]
        self.is_enabled = not self.is_enabled
        if self.is_enabled:
            self.toggle_btn.setText('⏸ 暂停')
            self.toggle_btn.setStyleSheet(f'''
                QPushButton {{
                    background-color: {t['accent']};
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 5px 15px;
                    font-size: 13px;
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
                    border-radius: 8px;
                    padding: 5px 15px;
                    font-size: 13px;
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
        QMessageBox.information(self, '设置快捷键', '请按下新的快捷键组合...')
    
    def finish_recording_hotkey(self, modifier: str, key: str):
        self.recording_hotkey = False
        self.config['hotkey'] = {'modifier': modifier, 'key': key}
        save_config(self.config)
        QMessageBox.information(self, '成功', f'快捷键已设置为: {self.format_hotkey()}')
    
    def on_lang_changed(self, index):
        lang_key = self.lang_combo.itemData(index)
        self.config['target_lang'] = lang_key
        save_config(self.config)
        self.update_timezone_display()

    def toggle_direction(self):
        if self.direction_btn.isChecked():
            self.config['translate_direction'] = 'foreign_to_cn'
        else:
            self.config['translate_direction'] = 'cn_to_foreign'
        save_config(self.config)
    
    def open_settings(self):
        dialog = SettingsDialog(self, self.config)
        if dialog.exec_() == QDialog.Accepted:
            self.config = load_config()
            self.update_timezone_display()
    
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
        t = THEMES[self.current_theme]
        try:
            orig_display = original[:50] + '...' if len(original) > 50 else original
            conv_display = converted[:50] + '...' if len(converted) > 50 else converted
            self.preview_original.setText(f'原文: {orig_display}')
            self.preview_converted.setText(f'转换: {conv_display}')
            
            platform = self.config.get('platform', 'Discord')
            limit = PLATFORM_LIMITS.get(platform, 2000)
            char_count = len(converted)
            
            if char_count > limit:
                self.char_count_label.setText(f'📋 {char_count}/{limit}')
                self.char_count_label.setStyleSheet(f'color: {t["danger"]};')
            else:
                self.char_count_label.setText(f'📋 {char_count}/{limit}')
                self.char_count_label.setStyleSheet(f'color: {t["text_secondary"]};')
            
            # Detect sensitive words - direct call since we're already on main thread
            sensitive_dict = self.config.get('sensitive_words', SENSITIVE_WORDS)
            sensitive_words = detect_sensitive_words(converted, sensitive_dict)
            self.show_sensitive_warning(sensitive_words)
        except Exception as e:
            print(f'[显示错误] {e}')
    
    def show_sensitive_warning(self, words):
        try:
            if words:
                warning_text = ', '.join(str(w) for w in words)
                self.sensitive_warning_label.setText(f'⚠️ 检测到敏感词: {warning_text}')
                self.sensitive_warning_label.show()
            else:
                self.sensitive_warning_label.hide()
        except Exception as e:
            print(f'[敏感词警告错误] {e}')

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
        t = THEMES[self.current_theme]
        try:
            if connected:
                self.google_status_label.setText('🟢 Google已连接')
                self.google_status_label.setStyleSheet(f'color: {t["accent"]};')
            else:
                self.google_status_label.setText('🔴 Google未连接')
                self.google_status_label.setStyleSheet(f'color: {t["danger"]};')
        except Exception as e:
            print(f'[Google状态错误] {e}')

    def on_sensitive_words_loaded(self, words):
        """Callback when sensitive words are loaded"""
        global LOADED_SENSITIVE_WORDS
        with SENSITIVE_WORDS_LOCK:
            LOADED_SENSITIVE_WORDS = words
        print(f'[Sensitive words] Loaded {len(words)} words')

    def load_templates_ui(self):
        t = THEMES[self.current_theme]
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
                btn = QPushButton(template['name'])
                btn.setToolTip(template['text'][:80] + '...' if len(template['text']) > 80 else template['text'])
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
            container = scroll.widget()
            if container:
                grid = container.layout()
                if grid:
                    for i in range(grid.count()):
                        widget = grid.itemAt(i).widget()
                        if widget:
                            if not search_text:
                                widget.show()
                            else:
                                name = widget.text().lower()
                                tip = (widget.toolTip() or '').lower()
                                widget.setVisible(search_text in name or search_text in tip)
    
    def use_template(self, template_text: str):
        target_lang = self.config.get('target_lang', 'zh-TW')
        lang_config = TARGET_LANGUAGES.get(target_lang, TARGET_LANGUAGES['zh-TW'])
        _, google_lang_code, has_opencc_fallback = lang_config
        
        direction = self.config.get('translate_direction', 'cn_to_foreign')
        
        if direction == 'cn_to_foreign':
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
        else:
            converted = google_translate(template_text, 'zh-CN', google_lang_code)
            if not converted:
                converted = template_text
        
        set_clipboard(converted)
        
        self.signal.conversion_done.emit(template_text, converted)
        
        chinese_count = sum(1 for c in template_text if '\u4e00' <= c <= '\u9fff')
        if chinese_count > 0:
            self.stats.add_chars(chinese_count)
            self.signal.stats_updated.emit()
        
        self.history.add(template_text, converted, target_lang)
        self.update_history_display()
    
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
                list_item.setData(Qt.UserRole, item.get('translated', ''))
                self.history_list.addItem(list_item)
        except Exception as e:
            print(f'[历史显示错误] {e}')
    def copy_history_item(self, item):
        text = item.data(Qt.UserRole)
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
                self.finish_recording_hotkey(modifier, key.char)
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
                
                direction = self.config.get('translate_direction', 'cn_to_foreign')
                
                if direction == 'cn_to_foreign':
                    converted_text = google_translate(original_text, google_lang_code, 'zh-CN')
                    if not converted_text and has_opencc_fallback:
                        text_with_custom = original_text
                        for simplified, taiwan in self.custom_dict.items():
                            text_with_custom = text_with_custom.replace(simplified, taiwan)
                        text_with_patterns = apply_sentence_patterns(text_with_custom)
                        converted_text = self.converter.convert(text_with_patterns)
                    elif not converted_text:
                        converted_text = original_text
                    
                    if target_lang == 'zh-TW' and self.config.get('llm_polish', True):
                        converted_text = llm_polish(converted_text)
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
    
    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            '海外社区运营小助理',
            '程序已最小化到系统托盘，继续在后台运行',
            QSystemTrayIcon.Information,
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
