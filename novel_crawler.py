import logging
import os
import re
import json
import asyncio
import random
import argparse
import time
import psutil
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from pathlib import Path

# 获取程序所在目录
SCRIPT_DIR = Path(__file__).parent.absolute()

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 系统资源监控标志
monitor_running = True

async def monitor_system_resources():
    """监控系统资源使用情况"""
    while monitor_running:
        try:
            # 获取CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            # 获取内存使用率
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # 输出资源使用情况
            logger.info(f"系统资源使用情况 - CPU: {cpu_percent}%, 内存: {memory_percent}%")
            
            # 等待10秒
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"监控系统资源时出错: {str(e)}")
            await asyncio.sleep(10)

def setup_logger(level_str="INFO"):
    """设置日志级别"""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    level = level_map.get(level_str.upper(), logging.INFO)
    
    # 清除已有的处理器
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)
    
    logger.setLevel(level)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    # 设置日志格式
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # 添加处理器到日志记录器
    logger.addHandler(console_handler)
    
    return logger

# 默认配置日志级别为INFO
setup_logger("INFO")

# 默认设置
DEFAULT_DELAY = (1, 3)  # 请求间隔随机秒数范围
MAX_RETRIES = 3  # 最大重试次数

def sanitize_filename(filename):
    """清理文件名，移除非法字符"""
    if not filename:
        return "unknown"
    
    # 移除Windows文件名中不允许的字符
    invalid_chars = r'[\\/*?:"<>|]'
    return re.sub(invalid_chars, '_', filename)

def clean_content(content):
    """清理章节内容,去除HTML标签和特殊字符"""
    # 替换HTML实体字符
    content = content.replace("&nbsp;", " ")
    content = content.replace("&ldquo;", "'")
    content = content.replace("&rdquo;", "'")
    content = content.replace("&lsquo;", "'")
    content = content.replace("&rsquo;", "'")
    content = content.replace("&mdash;", "—")
    content = content.replace("&ndash;", "–")
    content = content.replace("&hellip;", "…")
    
    # 处理换行和段落
    content = re.sub(r'\s*<br\s*/?\s*>\s*', '\n', content)
    content = re.sub(r'\s*<p\s*.*?>\s*(.*?)\s*</p>\s*', r'\1\n\n', content)
    
    # 去除其他HTML标签
    content = re.sub(r'<[^>]+>', '', content)
    
    # 广告清理
    ad_patterns = [
        r'新书推荐：.*',
        r'请记住本[站书].*?。',
        r'[一此本][书站]首发',
        r'天才一秒记住.*?。',
        r'热门推荐.*',
        r'\(https?://[^)]+\)',
        r'手机用户请浏览.*',
        r'txt下载.*',
        r'本章未完.*',
        r'未完待续.*',
        r'（.*?未完.*?）',
        r'（.*?请到.*?）',
        r'（.*?记住网址.*?）',
        r'请到.*?阅读',
        r'本书来自.*',
        r'本作品来自.*',
        r'本小说.*?更新最快',
        r'喜欢本书请收藏.*',
        r'章节报错.*',
        r'加入书架.*',
        r'求收藏.*',
        r'求月票.*',
        r'感谢.*?打赏',
        r'【.*?】',
        r'\[.*?\]',
        r'\s*\n{2,}',
    ]
    for pat in ad_patterns:
        content = re.sub(pat, '', content, flags=re.MULTILINE)
    
    # 处理连续空行
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    # 简单格式化
    paragraphs = content.split('\n')
    formatted_content = ""
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if paragraph:
            # 对每个段落添加换行
            formatted_content += paragraph + "\n\n"
    
    return formatted_content.strip()

def save_chapter(chapter_data, output_dir):
    """保存章节到文件"""
    try:
        # 确保输出目录在程序所在目录下
        output_dir = os.path.join(SCRIPT_DIR, output_dir)
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 创建小说专属目录
        novel_dir = os.path.join(output_dir, chapter_data["novel_name"])
        os.makedirs(novel_dir, exist_ok=True)
        
        # 构建文件名，添加序号前缀以便排序
        chapter_index = len(os.listdir(novel_dir)) + 1
        safe_title = sanitize_filename(chapter_data["title"])
        
        filename = f"{chapter_index:03d}_{safe_title}.md"
        file_path = os.path.join(novel_dir, filename)
        
        # 准备章节内容
        content = f"# {chapter_data['title']}\n\n{chapter_data['content']}"
        
        # 保存文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 更新章节数据，添加文件名
        chapter_data["filename"] = filename
        
        logger.debug(f"已保存: {file_path}")
        return True
    
    except Exception as e:
        logger.error(f"保存章节时出错: {str(e)}", exc_info=True)
        return False

def save_progress(output_dir, novel_name, author, chapters, last_url):
    """保存爬取进度到JSON文件"""
    try:
        # 确保输出目录在程序所在目录下
        output_dir = os.path.join(SCRIPT_DIR, output_dir)
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 为每个章节添加排序索引
        for i, chapter in enumerate(chapters):
            chapter["index"] = i
        
        # 构建进度数据
        progress_data = {
            "novel_name": novel_name,
            "author": author,
            "chapters": chapters,
            "last_url": last_url,
            "timestamp": datetime.now().timestamp()
        }
        
        # 保存进度文件到程序所在目录
        progress_file = os.path.join(SCRIPT_DIR, "progress.json")
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"进度已保存到 {progress_file}")
        return True
    
    except Exception as e:
        logger.error(f"保存进度时出错: {str(e)}", exc_info=True)
        return False

def merge_chapters(output_dir, novel_name, chapters_data):
    """将所有章节合并为一个Markdown文件"""
    try:
        # 确保输出目录在程序所在目录下
        output_dir = os.path.join(SCRIPT_DIR, output_dir)
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 构建合并文件路径
        merged_file = os.path.join(output_dir, f"{novel_name}_完整版.md")
        
        # 对章节进行排序
        sorted_chapters = process_and_sort_chapters(chapters_data)
        logger.debug(f"合并前重新排序章节，共 {len(sorted_chapters)} 章")
        
        # 合并章节内容
        with open(merged_file, 'w', encoding='utf-8') as f:
            # 写入小说信息
            f.write(f"# {novel_name}\n\n")
            if chapters_data and "author" in chapters_data[0]:
                f.write(f"作者: {chapters_data[0]['author']}\n\n")
            
            # 写入目录
            f.write("## 目录\n\n")
            for i, chapter in enumerate(sorted_chapters):
                f.write(f"{i+1}. [{chapter.get('title', '')}](#chapter-{i+1})\n")
            
            f.write("\n---\n\n")
            
            # 写入正文
            for i, chapter in enumerate(sorted_chapters):
                f.write(f"<a id=\"chapter-{i+1}\"></a>\n\n")
                f.write(f"## {chapter.get('title', '')}\n\n")
                f.write(f"{chapter.get('content', '')}\n\n")
                f.write("---\n\n")
        
        logger.info(f"已合并 {len(sorted_chapters)} 章为一个文件: {merged_file}")
        return merged_file
    
    except Exception as e:
        logger.error(f"合并章节时出错: {str(e)}", exc_info=True)
        return None

def extract_chapter_number(title):
    """从章节标题中提取章节号"""
    # 匹配"第X章"格式
    match = re.search(r'第([一二三四五六七八九十百千万零\d]+)章', title)
    if match:
        num_str = match.group(1)
        
        # 如果是数字
        if num_str.isdigit():
            return int(num_str)
        
        # 如果是中文数字
        ch_num_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
            '百': 100, '千': 1000, '万': 10000, '零': 0
        }
        
        if len(num_str) == 1 and num_str in ch_num_map:
            return ch_num_map[num_str]
        
        # 简单处理"十x"的情况
        if len(num_str) == 2 and num_str[0] == '十' and num_str[1] in ch_num_map:
            return 10 + ch_num_map[num_str[1]]
        
        # 其他复杂中文数字暂不处理
        return 999  # 给一个较大值但不是最大，让它排在后面但不是最后
    
    # 匹配"x章"格式
    match = re.search(r'(\d+)[章节]', title)
    if match:
        return int(match.group(1))
    
    # 匹配纯数字章节 (如: "1. xxxx" 或 "1 xxxx")
    match = re.search(r'^[\s\d\.]*(\d+)[\s\.\:]', title)
    if match:
        return int(match.group(1))
    
    return None

def process_and_sort_chapters(chapters):
    """处理并按照正确顺序排序章节列表"""
    if not chapters:
        return []
    
    logger.debug(f"开始排序 {len(chapters)} 个章节")
    
    # 创建排序信息数组，增加调试信息
    chapters_with_info = []
    
    # 记录章节号统计
    chapter_numbers = {}
    
    # 遍历所有章节，提取关键排序信息
    for i, chapter in enumerate(chapters):
        # 第一步: 提取基本信息
        title = chapter.get("title", "").strip()
        url = chapter.get("url", "")
        
        # 第二步: 从URL中提取数字（优先）
        url_num = None
        url_match = re.search(r'/(\d+)\.html$', url)
        if url_match:
            try:
                url_num = int(url_match.group(1))
            except ValueError:
                url_num = None
        
        # 第三步: 从标题提取章节号（次要）
        chapter_num = extract_chapter_number(title)
        
        # 记录章节号统计
        if chapter_num is not None:
            chapter_numbers[chapter_num] = chapter_numbers.get(chapter_num, 0) + 1
        
        # 第四步: 计算特殊序列号（用于次要排序）
        # 为特定的章节类型分配序列号
        sequence = 0
        if "序" in title or "前言" in title or "楔子" in title or "简介" in title:
            sequence = 0  # 序言放在最前面
        elif url_num == 1 or chapter_num == 1 or "第一章" in title:
            sequence = 1
        elif url_num == 2 or chapter_num == 2 or "第二章" in title:
            sequence = 2
        elif url_num == 3 or chapter_num == 3 or "第三章" in title:
            sequence = 3
        
        # 第五步: 计算优先级
        priority = 0
        
        # 特殊章节优先级 - 优先URL数字
        if url_num == 1 or ("第一章" in title and url_num is None):
            priority = 1000
        elif url_num == 2 or ("第二章" in title and url_num is None):
            priority = 900
        elif url_num == 3 or ("第三章" in title and url_num is None):
            priority = 800
        elif url_num and url_num < 10:
            priority = 700 - url_num  # 优先较小URL号
        elif "序" in title or "前言" in title or "楔子" in title or "简介" in title:
            priority = 500  # 序言等特殊章节
        elif url_num and url_num < 100:
            priority = 400 - url_num  # 较低优先级
        elif chapter_num and chapter_num < 100:
            priority = 300 - chapter_num  # 标题章节号优先级更低
        else:
            priority = 0  # 默认优先级
        
        # 将所有信息添加到排序数组
        chapters_with_info.append({
            "original_index": i,
            "title": title,
            "url": url,
            "chapter_num": chapter_num,
            "url_num": url_num,
            "sequence": sequence,
            "priority": priority,
            "original": chapter  # 保存原始章节信息
        })
    
    # 统计并记录章节号分布情况
    logger.debug(f"章节号统计: {sorted([(k, v) for k, v in chapter_numbers.items() if k is not None])}")
    
    # 判断是否有连续章节号
    has_sequential_chapters = False
    chapter_nums = sorted([k for k in chapter_numbers.keys() if k is not None])
    if len(chapter_nums) >= 3:
        # 查找至少3个连续的章节号
        consecutive_count = 1
        for i in range(1, len(chapter_nums)):
            if chapter_nums[i] == chapter_nums[i-1] + 1:
                consecutive_count += 1
                if consecutive_count >= 3:
                    has_sequential_chapters = True
                    break
            else:
                consecutive_count = 1
    
    logger.debug(f"是否有连续章节号序列: {has_sequential_chapters}")
    
    # 优先按URL数字排序，确保第1章在最前面
    logger.debug("使用URL数字优先排序策略")
    chapters_with_info.sort(key=lambda x: (
        x["url_num"] if x["url_num"] is not None else 999999,  # 优先按URL数字排序（小的在前面）
        x["chapter_num"] if x["chapter_num"] is not None else 999999,  # 然后按章节号排序
        -x["priority"],  # 然后按优先级（高的优先）
        x["sequence"],   # 然后按序列号（序言在前）
        x["original_index"]  # 最后保持原顺序
    ))
    
    # 记录排序结果的前几章和最后几章
    logger.debug("排序结果:")
    for i in range(min(5, len(chapters_with_info))):
        chapter = chapters_with_info[i]
        logger.debug(f"{i+1}. {chapter['title']} - URL号:{chapter['url_num']}, 章节号:{chapter['chapter_num']}, 优先级:{chapter['priority']}")
    
    if len(chapters_with_info) > 10:
        logger.debug("...")
        for i in range(max(5, len(chapters_with_info)-3), len(chapters_with_info)):
            chapter = chapters_with_info[i]
            logger.debug(f"{i+1}. {chapter['title']} - URL号:{chapter['url_num']}, 章节号:{chapter['chapter_num']}, 优先级:{chapter['priority']}")
    
    # 转换回原始格式
    return [chapter["original"] for chapter in chapters_with_info]

async def crawl_chapter(crawler, chapter_url, novel_name=None, author=None, max_chapter=None, **kwargs):
    """爬取单个章节"""
    logger.info(f"正在爬取章节: {chapter_url}")
    
    try:
        result = await crawler.arun(url=chapter_url)
        html = result.html
        # 使用 BeautifulSoup 提取正文
        soup = BeautifulSoup(html, 'html.parser')
        content = ''
        # 优先 <div id="content">
        content_div = soup.find('div', id='content')
        if not content_div:
            # 其次 <div class="content">
            content_div = soup.find('div', class_='content')
        if content_div:
            content = content_div.get_text(separator='\n', strip=True)
        # fallback 到原正则
        if not content:
            content_patterns = [
                r'<div[^>]*id="content"[^>]*>(.*?)</div>',
                r'<div[^>]*class="content"[^>]*>(.*?)</div>',
                r'<div[^>]*class="chapter-content"[^>]*>(.*?)</div>',
                r'<div[^>]*class="article-content"[^>]*>(.*?)</div>',
                r'<article[^>]*>(.*?)</article>'
            ]
            for pattern in content_patterns:
                content_match = re.search(pattern, html, re.DOTALL)
                if content_match:
                    content = content_match.group(1)
                    break
        # 内容为空报警
        if not content or len(content.strip()) < 20:
            logger.warning(f"未能从 {chapter_url} 提取到有效正文内容！")
            return None
        # 清理广告和格式化
        content = clean_content(content)
        
        # 提取章节标题 - 尝试多种匹配模式
        title_patterns = [
            r'<h1[^>]*>(.*?)</h1>',
            r'<title>(.*?)[-_|].*?</title>',
            r'<div[^>]*class="bookname"[^>]*>[^<]*<h1[^>]*>(.*?)</h1>',
            r'<div[^>]*class="chapter-title"[^>]*>.*?<span[^>]*>(.*?)</span>'
        ]
        
        title = os.path.basename(chapter_url)
        for pattern in title_patterns:
            title_match = re.search(pattern, html)
            if title_match:
                title = title_match.group(1).strip()
                logger.debug(f"使用模式 '{pattern}' 提取到标题: {title}")
                break
        
        # 提取上一章/下一章链接 - 尝试多种匹配模式
        prev_patterns = [
            r'<a[^>]*href="([^"]*)"[^>]*>上一[章页]</a>',
            r'<a[^>]*href="([^"]*)"[^>]*>上一[章页]</a>',
            r'<a[^>]*href="([^"]*)"[^>]*>上[一章]</a>',
            r'<a[^>]*href="([^"]*)"[^>]*>\s*&lt;\s*上[一章]\s*</a>'
        ]
        
        next_patterns = [
            r'<a[^>]*href="([^"]*)"[^>]*>下一[章页]</a>',
            r'<a[^>]*href="([^"]*)"[^>]*>下一[章页]</a>',
            r'<a[^>]*href="([^"]*)"[^>]*>下[一章]</a>',
            r'<a[^>]*href="([^"]*)"[^>]*>\s*下[一章]\s*&gt;\s*</a>'
        ]
        
        index_patterns = [
            r'<a[^>]*href="([^"]*)"[^>]*>目录</a>',
            r'<a[^>]*href="([^"]*)"[^>]*>章节目录</a>',
            r'<a[^>]*href="([^"]*)"[^>]*>回目录</a>',
            r'<a[^>]*href="([^"]*)"[^>]*>返回目录</a>'
        ]
        
        prev_url = ""
        for pattern in prev_patterns:
            prev_match = re.search(pattern, html)
            if prev_match:
                prev_url = urljoin(chapter_url, prev_match.group(1))
                logger.debug(f"找到上一章链接: {prev_url}")
                break
        
        next_url = ""
        for pattern in next_patterns:
            next_match = re.search(pattern, html)
            if next_match:
                next_url = urljoin(chapter_url, next_match.group(1))
                logger.debug(f"找到下一章链接: {next_url}")
                break
        
        index_url = ""
        for pattern in index_patterns:
            index_match = re.search(pattern, html)
            if index_match:
                index_url = urljoin(chapter_url, index_match.group(1))
                logger.debug(f"找到目录链接: {index_url}")
                break
        
        # 提取或使用传入的小说信息
        meta_novel_name = None
        meta_author = None
        
        # 尝试从meta标签提取小说名
        novel_name_patterns = [
            r'<meta property="og:novel:book_name" content="([^"]+)"',
            r'<meta name="book" content="([^"]+)"',
            r'<meta property="og:title" content="([^"]+)[-_|]'
        ]
        
        for pattern in novel_name_patterns:
            meta_match = re.search(pattern, html)
            if meta_match:
                meta_novel_name = meta_match.group(1).strip()
                break
        
        # 尝试从meta标签提取作者
        author_patterns = [
            r'<meta property="og:novel:author" content="([^"]+)"',
            r'<meta name="author" content="([^"]+)"'
        ]
        
        for pattern in author_patterns:
            author_match = re.search(pattern, html)
            if author_match:
                meta_author = author_match.group(1).strip()
                break
        
        # 使用传入的值或元数据中提取的值
        novel_name = novel_name or meta_novel_name or "未知小说"
        author = author or meta_author or "未知作者"
        
        # 提取分类
        category = "未知分类"
        category_match = re.search(r'<meta property="og:novel:category" content="([^"]+)"', html)
        if category_match:
            category = category_match.group(1)
        
        # 返回章节信息
        return {
            "title": title,
            "content": content,
            "prev_url": prev_url,
            "next_url": next_url,
            "index_url": index_url,
            "novel_name": novel_name,
            "category": category,
            "author": author,
            "url": chapter_url
        }
    
    except Exception as e:
        logger.error(f"爬取章节 {chapter_url} 时出错: {str(e)}", exc_info=True)
        return None

async def crawl_index_page(crawler, url):
    """爬取小说目录页，返回章节列表"""
    logger.info(f"正在爬取目录页: {url}")
    
    try:
        # 获取HTML
        result = await crawler.arun(url=url)
        html = result.html
        
        # 调试输出
        logger.debug(f"获取到的HTML长度: {len(html)}")
        
        # 保存HTML用于调试，确保在程序所在目录下
        debug_html_file = os.path.join(SCRIPT_DIR, "debug_html.txt")
        with open(debug_html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        logger.debug(f"保存HTML到 {debug_html_file} 用于调试")
        
        # 提取小说信息 - 尝试多种通用模式
        title_patterns = [
            r'<meta property="og:novel:book_name" content="([^"]+)"',
            r'<meta property="og:title" content="([^"]+)"',
            r'<h1[^>]*>(.*?)</h1>',
            r'<div[^>]*class="bookname"[^>]*>(.*?)</div>',
            r'<title>(.*?)最新章节|全文阅读|无弹窗',
            r'<title>(.*?)[_|-]'
        ]
        
        author_patterns = [
            r'<meta property="og:novel:author" content="([^"]+)"',
            r'<meta name="author" content="([^"]+)"',
            r'作\s*者[：:]\s*<a[^>]*>([^<]+)</a>',
            r'作\s*者[：:]\s*([^<>\s]+)',
            r'作\s*者：</span>\s*([^<]+)',
            r'<p>作\s*者：([^<]+)</p>'
        ]
        
        # 尝试每个模式来匹配标题
        novel_name = "未知小说"
        for pattern in title_patterns:
            title_match = re.search(pattern, html)
            if title_match:
                novel_name = title_match.group(1).strip()
                novel_name = re.sub(r'[_\-].*$', '', novel_name)  # 移除副标题
                break
        
        # 尝试每个模式来匹配作者
        author = "未知作者"
        for pattern in author_patterns:
            author_match = re.search(pattern, html)
            if author_match:
                author = author_match.group(1).strip()
                break
        
        logger.debug(f"提取到的小说名: {novel_name}, 作者: {author}")
        
        # 1. 针对性地寻找包含"正文"关键字的区域
        text_content_matches = []
        
        # 寻找包含"正文"关键字的区域
        text_content_patterns = [
            (re.search(r'正文</dt>(.*?)</dl>', html, re.DOTALL), "正文dt-dl区域"),
            (re.search(r'正文</h\d>(.*?)(?:<h\d>|</div>)', html, re.DOTALL), "正文h标签区域"),
            (re.search(r'正文</span>(.*?)(?:</div>|<div)', html, re.DOTALL), "正文span区域"),
            (re.search(r'<dt[^>]*>正文</dt>(.*?)</dl>', html, re.DOTALL), "正文dt-dl完整区域"),
            (re.search(r'正文(?:</[^>]+>)(.*?)(?:<h\d>|<div[^>]*id=|</section>)', html, re.DOTALL), "正文通用区域1"),
            (re.search(r'《[^》]+》正文(.*?)(?:最新章节|新书推荐|</div>)', html, re.DOTALL), "书名+正文区域"),
            (re.search(r'正文卷(.*?)(?:完结感言|<h\d>|</div>)', html, re.DOTALL), "正文卷区域"),
        ]
        
        for match, source in text_content_patterns:
            if match:
                text_content_matches.append((match.group(1), source))
                logger.debug(f"找到可能的正文区域: {source}, 长度: {len(match.group(1))}")
        
        # 2. 查找章节列表区域
        content_sections = [
            # 尝试匹配常见的章节列表容器
            (re.search(r'<div[^>]*id="list"[^>]*>(.*?)</div>', html, re.DOTALL), "div#list容器"),
            (re.search(r'<div[^>]*class="listmain"[^>]*>(.*?)</div>', html, re.DOTALL), "div.listmain容器"),
            (re.search(r'<dl[^>]*id="chapterlist"[^>]*>(.*?)</dl>', html, re.DOTALL), "dl#chapterlist容器"),
            (re.search(r'<ul[^>]*class="chapter"[^>]*>(.*?)</ul>', html, re.DOTALL), "ul.chapter容器"),
            (re.search(r'<div[^>]*class="box_con"[^>]*>.*?<div[^>]*id="list"[^>]*>(.*?)</div>', html, re.DOTALL), "box_con+list容器"),
            (re.search(r'<div[^>]*id="content_1"[^>]*>(.*?)</div>', html, re.DOTALL), "content_1容器"),
            (re.search(r'最新章节列表.*?<ul>(.*?)</ul>', html, re.DOTALL), "最新章节列表区域"),
            (re.search(r'章节列表.*?<ul[^>]*>(.*?)</ul>', html, re.DOTALL), "章节列表区域")
        ]
        
        # 3. 合并所有找到的内容区域，优先使用包含"正文"关键字的区域
        content_html = ""
        content_source = ""
        
        # 首先检查正文区域
        if text_content_matches:
            # 选择文本最长的区域，通常包含更多章节
            text_content_matches.sort(key=lambda x: len(x[0]), reverse=True)
            content_html = text_content_matches[0][0]
            content_source = text_content_matches[0][1]
            logger.debug(f"使用正文匹配区域: {content_source}, 长度: {len(content_html)}")
        
        # 如果没有正文区域，再尝试其他章节容器
        if not content_html:
            for content_match, source in content_sections:
                if content_match:
                    content_html = content_match.group(1)
                    content_source = source
                    logger.debug(f"使用章节容器区域: {source}, 长度: {len(content_html)}")
                    break
        
        # 如果仍未找到，尝试识别有大量链接的区域
        if not content_html:
            logger.debug('没有找到明确的章节区域，尝试识别包含大量章节链接的区域')
            
            # 寻找包含多个连续链接的区域
            link_clusters = []
            chunks = re.findall(r'(<div[^>]*>.*?</div>)', html, re.DOTALL)
            
            for chunk in chunks:
                links = re.findall(r'<a[^>]*href="[^"]*"[^>]*>[^<]*</a>', chunk)
                if len(links) > 10:  # 至少有10个链接
                    link_ratio = len(''.join(links)) / (len(chunk) + 0.1)
                    if link_ratio > 0.3:  # 链接占比超过30%
                        link_clusters.append((chunk, len(links), link_ratio))
            
            if link_clusters:
                # 按链接数量排序
                link_clusters.sort(key=lambda x: x[1], reverse=True)
                content_html = link_clusters[0][0]
                content_source = f"链接密集区域(包含{link_clusters[0][1]}个链接)"
                logger.debug(f"使用链接密集区域: {content_source}")
        
        # 收集所有可能的章节链接
        all_chapters = []
        chapter_link_patterns = []  # 记录从哪些链接模式找到章节
        
        # 1. 从正文区域提取章节
        if content_html:
            # 定义一个函数来判断链接是否可能是章节链接
            def is_likely_chapter_link(title, href):
                title = title.strip()
                
                # 过滤常见的非章节链接
                if any(x in title for x in ["登录", "注册", "首页", "登陆", "帮助", "设置"]):
                    return False, "非章节关键词"
                
                if len(title) < 2:  # 标题过短
                    return False, "标题过短"
                
                # 明确的章节标记
                if re.search(r'第.+[章节回]', title):
                    return True, "包含'第x章'格式"
                
                # 数字开头可能是章节
                if re.search(r'^\d+\.?\s*\D+', title):
                    return True, "数字开头"
                
                # 特殊章节名
                if any(x in title for x in ["序言", "序章", "前言", "引言", "楔子", "尾声", "后记", "番外"]):
                    return True, "特殊章节名"
                
                # URL模式判断
                if re.search(r'/\d+\.html$', href):
                    return True, "URL格式为数字.html"
                
                return False, "无匹配模式"
            
            # 直接提取所有链接
            all_links = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', content_html)
            total_links = len(all_links)
            valid_chapters = 0
            rejected_chapters = 0
            
            for href, title in all_links:
                title = title.strip()
                is_chapter, reason = is_likely_chapter_link(title, href)
                
                if is_chapter:
                    chapter_url = urljoin(url, href)
                    all_chapters.append({
                        "title": title,
                        "url": chapter_url
                    })
                    valid_chapters += 1
                    # 记录找到章节的链接模式
                    chapter_link_patterns.append(reason)
                else:
                    rejected_chapters += 1
            
            chapter_patterns_count = {}
            for pattern in chapter_link_patterns:
                chapter_patterns_count[pattern] = chapter_patterns_count.get(pattern, 0) + 1
            
            logger.debug(f"章节链接识别结果 - 总链接数:{total_links}, 有效章节:{valid_chapters}, 拒绝链接:{rejected_chapters}")
            logger.debug(f"章节链接模式分布: {chapter_patterns_count}")
        
        # 2. 如果找到的章节太少，尝试全页面扫描
        if len(all_chapters) < 10:
            logger.debug("章节数量不足(<10)，进行全页面扫描")
            
            # 扫描所有链接
            all_page_links = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html)
            
            existing_urls = {c["url"] for c in all_chapters}
            
            for href, title in all_page_links:
                # 去除HTML标签
                title = re.sub(r'<[^>]+>', '', title).strip()
                
                # 检查是否已存在
                chapter_url = urljoin(url, href)
                if chapter_url in existing_urls:
                    continue
                
                # 判断是否可能是章节链接
                is_chapter, reason = is_likely_chapter_link(title, href)
                if is_chapter:
                    all_chapters.append({
                        "title": title,
                        "url": chapter_url
                    })
            
            logger.debug(f"全页面扫描后总共找到 {len(all_chapters)} 个可能的章节链接")
        
        # 3. 查找第一章链接
        first_chapter_candidates = []
        
        # 在现有链接中找第一章
        for chapter in all_chapters:
            title = chapter["title"]
            if "第一章" in title or "第1章" in title or "第１章" in title:
                first_chapter_candidates.append(chapter)
                logger.debug(f"找到可能的第一章: {title} -> {chapter['url']}")
        
        # 4. 如果没有找到第一章，尝试构造URL或在原始HTML中查找更多线索
        if not first_chapter_candidates:
            logger.debug("在现有链接中未找到第一章，尝试其他方法")
            
            # 查找可能的第一章链接（文本包含"第一章"但可能不在已提取的章节区域）
            first_chapter_matches = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>([^<]*第一章[^<]*)</a>', html)
            for href, title in first_chapter_matches:
                chapter_url = urljoin(url, href)
                if not any(c["url"] == chapter_url for c in all_chapters):
                    first_chapter_candidates.append({
                        "title": title.strip(),
                        "url": chapter_url
                    })
                    logger.debug(f"从原始HTML找到第一章: {title.strip()} -> {chapter_url}")
            
            # 如果仍未找到，尝试构造URL
            if not first_chapter_candidates:
                logger.debug("尝试构造第一章URL")
                # 提取一个章节URL的模式
                url_patterns = set()
                for chapter in all_chapters:
                    url_match = re.search(r'(.*/)(\d+)(\.html)$', chapter["url"])
                    if url_match:
                        url_patterns.add((url_match.group(1), url_match.group(3)))
                
                # 对于每个URL模式，尝试常见的第一章ID
                for prefix, suffix in url_patterns:
                    for chapter_id in [1, 1000, 10000, 100000, 1000000]:
                        candidate_url = f"{prefix}{chapter_id}{suffix}"
                        logger.debug(f"尝试第一章URL: {candidate_url}")
                        
                        try:
                            # 检查URL是否可访问
                            result = await crawler.arun(url=candidate_url)
                            chapter_html = result.html
                            
                            # 检查是否是有效章节页面
                            if '<div id="content"' in chapter_html or '<div class="content"' in chapter_html:
                                # 提取标题
                                title_match = re.search(r'<h1[^>]*>(.*?)</h1>', chapter_html)
                                if title_match:
                                    title = title_match.group(1).strip()
                                    
                                    # 判断是否是第一章
                                    if "第一章" in title or "第1章" in title or extract_chapter_number(title) == 1:
                                        first_chapter_candidates.append({
                                            "title": title,
                                            "url": candidate_url
                                        })
                                        logger.info(f"成功找到第一章: {title} -> {candidate_url}")
                                        break
                        except Exception as e:
                            logger.debug(f"尝试URL失败: {str(e)}")
        
        # 6. 将找到的第一章添加到章节列表
        if first_chapter_candidates:
            # 按章节号排序，取最可能是第一章的
            first_chapter_candidates.sort(key=lambda x: extract_chapter_number(x["title"]) or 9999)
            first_chapter = first_chapter_candidates[0]
            
            # 检查是否已存在
            if not any(c["url"] == first_chapter["url"] for c in all_chapters):
                # 添加到列表开头
                all_chapters.insert(0, first_chapter)
                logger.info(f"已将找到的第一章添加到列表开头: {first_chapter['title']}")
        
        # 7. 去除重复URL并排序章节
        unique_urls = set()
        unique_chapters = []
        
        for chapter in all_chapters:
            if chapter["url"] not in unique_urls:
                unique_urls.add(chapter["url"])
                unique_chapters.append(chapter)
        
        # 按章节号和顺序排序
        sorted_chapters = process_and_sort_chapters(unique_chapters)
        
        # 记录排序后的章节信息
        logger.info(f"排序后总共有 {len(sorted_chapters)} 个章节")
        if sorted_chapters:
            # 记录前5章
            for i in range(min(5, len(sorted_chapters))):
                logger.debug(f"排序后章节 {i+1}: {sorted_chapters[i]['title']} -> {sorted_chapters[i]['url']}")
            
            # 如果章节多于5个，也记录最后一章
            if len(sorted_chapters) > 5:
                logger.debug(f"排序后最后章节: {sorted_chapters[-1]['title']} -> {sorted_chapters[-1]['url']}")
        
        return {
            "novel_name": novel_name,
            "author": author,
            "chapters": sorted_chapters
        }
    
    except Exception as e:
        logger.error(f"爬取目录页 {url} 时出错: {str(e)}", exc_info=True)
        return None

def is_directory_page(url):
    """检测URL是否为目录页"""
    # 目录页的特征：不以 .html 结尾，或者以 / 结尾
    if url.endswith('/') or not url.endswith('.html'):
        return True
    
    # 检查URL模式，目录页通常不包含章节数字
    if re.search(r'/\d+\.html$', url):
        return False
    
    return True

async def crawl_multiple_chapters(url, output_dir="novels", num_chapters=10, is_chapter=False, 
                                 pause_range=(1.0, 3.0), resume=False, logger_level="INFO",
                                 concurrency=8):
    """爬取多个章节"""
    # 设置日志级别
    setup_logger(logger_level)
    
    logger.info(f"开始爬取小说，起始URL: {url}")
    logger.info(f"爬取章节数: {num_chapters}")
    logger.info(f"输出目录: {output_dir}")
    logger.info(f"是否合并章节: 是")
    logger.info(f"请求延迟范围: {pause_range[0]}~{pause_range[1]}秒")
    logger.info(f"是否断点续传: {'是' if resume else '否'}")
    logger.info(f"URL类型: {'章节页' if is_chapter else '目录页'}")
    logger.info(f"并发数: {concurrency}")
    
    # 创建爬虫配置
    browser_config = BrowserConfig(headless=True, java_script_enabled=True)
    
    # 章节列表
    chapters_data = []
    
    # 进度文件路径
    progress_file = os.path.join(SCRIPT_DIR, "progress.json")
    
    # 如果需要续传，检查进度文件
    last_url = None
    if resume and os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
                loaded_chapters = progress_data.get('chapters', [])
                
                # 根据索引排序章节
                if loaded_chapters and 'index' in loaded_chapters[0]:
                    loaded_chapters.sort(key=lambda x: x.get('index', 9999))
                else:
                    # 如果没有索引，使用章节排序函数
                    loaded_chapters = process_and_sort_chapters(loaded_chapters)
                
                chapters_data = loaded_chapters
                last_url = progress_data.get('last_url')
                logger.info(f"从进度文件中读取到 {len(chapters_data)} 个已爬取的章节")
                
                # 记录前几章信息
                for i in range(min(3, len(chapters_data))):
                    logger.debug(f"恢复章节 {i+1}: {chapters_data[i]['title']}")
                
                # 如果有多于3章，也记录最后一章
                if len(chapters_data) > 3:
                    logger.debug(f"恢复最后章节: {chapters_data[-1]['title']}")
        except Exception as e:
            logger.error(f"读取进度文件时出错: {str(e)}")
    
    novel_info = None
    total_chapters = []
    
    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            # 如果是目录页，先爬取目录
            if not is_chapter:
                novel_info = await crawl_index_page(crawler, url)
                if novel_info:
                    total_chapters = novel_info.get('chapters', [])
                    
                    # 确保章节是按顺序排列的
                    total_chapters = process_and_sort_chapters(total_chapters)
                    
                    logger.info(f"将爬取 {min(num_chapters, len(total_chapters)) if num_chapters > 0 else len(total_chapters)} 个章节")
            
            # 如果是从章节页开始
            elif is_chapter:
                # 先爬取当前章节，获取小说信息
                current_chapter = await crawl_chapter(crawler, url)
                if current_chapter:
                    novel_name = current_chapter.get('novel_name')
                    author = current_chapter.get('author')
                    index_url = current_chapter.get('index_url')
                    
                    # 尝试爬取目录页获取完整章节列表
                    if index_url:
                        logger.info(f"尝试从目录页获取完整章节列表: {index_url}")
                        novel_info = await crawl_index_page(crawler, index_url)
                        if novel_info:
                            total_chapters = novel_info.get('chapters', [])
                            
                            # 确保章节是按顺序排列的
                            total_chapters = process_and_sort_chapters(total_chapters)
                            
                            # 找到用户指定的章节在排序后列表中的位置
                            start_index = 0
                            for i, chapter in enumerate(total_chapters):
                                if chapter.get('url') == url:
                                    start_index = i
                                    logger.info(f"找到指定章节在目录中的位置: 第 {start_index + 1} 个")
                                    break
                            
                            # 如果找到了指定章节，只取从该位置开始到末尾的章节
                            if start_index > 0:
                                # 只取从指定章节开始到末尾的章节，不重新排列
                                total_chapters = total_chapters[start_index:]
                                logger.info(f"已截取章节列表，从指定章节开始，共 {len(total_chapters)} 章")
                    
                    # 如果没有获取到目录，或者章节列表为空，就只爬当前章节及其后续章节
                    if not total_chapters:
                        logger.info("无法获取完整目录，将从当前章节开始爬取")
                        # 创建一个只包含当前章节的列表
                        total_chapters = [{
                            "title": current_chapter.get('title', "当前章节"),
                            "url": url
                        }]
            
            # 去重，创建已爬取URL集合
            crawled_urls = {chapter.get('url', '') for chapter in chapters_data}
            logger.debug(f"已爬取的URL数量: {len(crawled_urls)}")
            
            # 如果有章节列表，按顺序爬取
            if total_chapters:
                novel_name = novel_info.get('novel_name') if novel_info else None
                author = novel_info.get('author') if novel_info else None
                
                # 如果是续传，且已有章节数据，则使用已有的小说名和作者
                if resume and chapters_data:
                    first_chapter = chapters_data[0]
                    novel_name = novel_name or first_chapter.get('novel_name')
                    author = author or first_chapter.get('author')
                
                # 确定要爬取的章节数量
                chapters_to_crawl = min(num_chapters, len(total_chapters)) if num_chapters > 0 else len(total_chapters)
                
                # 记录爬取范围
                if is_chapter:
                    logger.info(f"从指定章节开始，将爬取 {chapters_to_crawl} 个章节")
                    if total_chapters:
                        logger.info(f"起始章节: {total_chapters[0]['title']} ({total_chapters[0]['url']})")
                else:
                    logger.info(f"从第1章开始，将爬取 {chapters_to_crawl} 个章节")
                
                # 创建信号量来控制并发
                semaphore = asyncio.Semaphore(concurrency)
                
                async def crawl_chapter_with_semaphore(chapter_info):
                    async with semaphore:
                        chapter_url = chapter_info['url']
                        
                        # 如果已经爬取过，跳过
                        if chapter_url in crawled_urls:
                            logger.debug(f"已爬取过章节: {chapter_info['title']}, 跳过")
                            return None
                        
                        # 爬取章节
                        chapter_data = await crawl_chapter(crawler, chapter_url, novel_name, author)
                        if chapter_data:
                            # 保存章节
                            save_chapter(chapter_data, output_dir)
                            return chapter_data
                        
                        # 随机暂停，避免频繁请求
                        pause_time = random.uniform(pause_range[0], pause_range[1])
                        logger.debug(f"等待 {pause_time:.2f} 秒...")
                        await asyncio.sleep(pause_time)
                        return None
                
                # 创建任务列表
                tasks = []
                for chapter_info in total_chapters[:chapters_to_crawl]:
                    if chapter_info['url'] not in crawled_urls:
                        tasks.append(crawl_chapter_with_semaphore(chapter_info))
                
                # 启动系统资源监控
                monitor_task = asyncio.create_task(monitor_system_resources())
                
                # 并发执行任务
                results = await asyncio.gather(*tasks)
                
                # 停止系统资源监控
                global monitor_running
                monitor_running = False
                await monitor_task
                
                # 处理结果
                for result in results:
                    if result:
                        chapters_data.append(result)
                        crawled_urls.add(result['url'])
                
                # 保存最终进度
                save_progress(output_dir, novel_name, author, chapters_data, total_chapters[-1]['url'] if total_chapters else None)
            
            # 如果没有章节列表，就从当前章节开始，按"下一章"链接爬取
            else:
                current_url = url
                if last_url and resume:
                    current_url = last_url
                
                chapters_to_crawl = num_chapters if num_chapters > 0 else 999
                novel_name = None
                author = None
                count = 0
                
                # 如果是续传，且已有章节数据，则使用已有的小说名和作者
                if resume and chapters_data:
                    first_chapter = chapters_data[0]
                    novel_name = first_chapter.get('novel_name')
                    author = first_chapter.get('author')
                
                # 创建信号量来控制并发
                semaphore = asyncio.Semaphore(concurrency)
                
                # 启动系统资源监控
                monitor_task = asyncio.create_task(monitor_system_resources())
                
                # 循环爬取后续章节
                while count < chapters_to_crawl:
                    # 如果已经爬取过，跳过
                    if current_url in crawled_urls:
                        # 尝试获取下一章的URL
                        next_url = next((chapter['next_url'] for chapter in chapters_data if chapter['url'] == current_url), None)
                        if next_url and next_url != current_url:
                            current_url = next_url
                            continue
                        else:
                            break
                    
                    async with semaphore:
                        # 爬取章节
                        chapter_data = await crawl_chapter(crawler, current_url, novel_name, author)
                        if not chapter_data:
                            logger.error(f"爬取章节失败: {current_url}")
                            break
                        
                        # 第一次爬取时，获取小说名和作者
                        if not novel_name:
                            novel_name = chapter_data.get('novel_name')
                            author = chapter_data.get('author')
                        
                        # 保存章节
                        save_chapter(chapter_data, output_dir)
                        chapters_data.append(chapter_data)
                        crawled_urls.add(current_url)
                        count += 1
                        logger.info(f"已爬取 {count}/{chapters_to_crawl} 章: {chapter_data['title']}")
                        
                        # 每爬取3章保存一次进度
                        if count % 3 == 0:
                            save_progress(output_dir, novel_name, author, chapters_data, current_url)
                        
                        # 获取下一章的URL
                        next_url = chapter_data.get('next_url')
                        if not next_url or next_url == current_url:
                            logger.info("没有找到下一章链接，爬取结束")
                            break
                        
                        # 检查下一章URL是否为目录页
                        if is_directory_page(next_url):
                            logger.info(f"下一章链接指向目录页: {next_url}，爬取结束")
                            break
                        
                        current_url = next_url
                        
                        # 随机暂停，避免频繁请求
                        pause_time = random.uniform(pause_range[0], pause_range[1])
                        logger.debug(f"等待 {pause_time:.2f} 秒...")
                        await asyncio.sleep(pause_time)
                
                # 停止系统资源监控
                monitor_running = False
                await monitor_task
                
                # 保存最终进度
                save_progress(output_dir, novel_name, author, chapters_data, current_url)
        
        # 将所有章节合并为一个文件
        if chapters_data:
            # 再次按章节号排序
            sorted_chapters = process_and_sort_chapters(chapters_data)
            
            # 合并章节
            merged_file = merge_chapters(output_dir, novel_name, sorted_chapters)
            logger.info(f"已将所有章节合并为: {merged_file}")
        
        # 统计信息
        logger.info(f"共爬取了 {len(chapters_data)} 章小说内容")
        
    except Exception as e:
        logger.error(f"爬取过程中出错: {str(e)}", exc_info=True)

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="小说爬虫：爬取指定URL的小说内容，从第一章开始")
    
    parser.add_argument("url", help="小说URL，可以是目录页或章节页")
    parser.add_argument("-n", "--num_chapters", type=int, default=0, help="要爬取的章节数量，0表示爬取所有章节")
    parser.add_argument("-o", "--output_dir", default="novels", help="输出目录，默认为'novels'")
    parser.add_argument("-d", "--delay", nargs=2, type=float, default=(1.0, 3.0), 
                        metavar=('MIN', 'MAX'), help="请求延迟范围（秒），默认为1-3秒")
    parser.add_argument("-c", "--chapter", action="store_true", help="指定URL是章节页而不是目录页")
    parser.add_argument("-r", "--resume", action="store_true", help="断点续传，从上次中断的地方继续爬取")
    parser.add_argument("-l", "--log_level", default="INFO", 
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="日志级别，默认为INFO")
    parser.add_argument("-p", "--concurrency", type=int, default=8,
                        help="并发数量，默认为8")
    
    return parser.parse_args()

async def main():
    """主程序入口"""
    try:
        # 解析命令行参数
        args = parse_args()
        
        # 爬取小说章节
        await crawl_multiple_chapters(
            url=args.url,
            output_dir=args.output_dir,
            num_chapters=args.num_chapters,
            is_chapter=args.chapter,
            pause_range=args.delay,
            resume=args.resume,
            logger_level=args.log_level,
            concurrency=args.concurrency
        )
        
    except Exception as e:
        logger.error(f"运行时发生错误: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 