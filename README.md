# 小说爬虫程序
 已测试网站如下
 
 网站：https://www.tvbts4.com/
 
 网站：https://www.biziqu.cc/

这是一个功能强大的小说爬虫程序，可以自动爬取网络小说的章节内容，并支持断点续传、并发下载等功能。（未测试其他网站）

## 功能特点

- 支持从目录页或章节页开始爬取
- 自动识别章节顺序和内容
- 支持断点续传，中断后可继续爬取
- 并发下载，提高爬取效率
- 自动监控系统资源使用情况
- 支持自定义爬取章节数量
- 自动合并章节为完整小说文件
- 支持多种小说网站格式

*结合以下电子书阅读器使用更佳*

电脑：[Koodo Reader](https://www.koodoreader.com/zh)、[Readest](https://github.com/readest/readest)

手机：[Kindle](https://apps.apple.com/us/app/amazon-kindle/id302584613)、[Apple Books](https://www.apple.com/apple-books/)、[Moon+ Reader](https://moondownload.com/chinese.html)、<del>
微信读书</del>（2024.4 更新后，非付费会员每月最多导 3 本书）

## 环境要求

- Python 3.7+
- 操作系统：Windows/Linux/MacOS

## 安装步骤

1. 克隆或下载本项目到本地

2. 安装依赖包：
```bash
pip install -r requirements.txt
playwright install 或者playwright install chromium
```

## 使用方法

### 基本用法

```bash
python novel_crawler.py <小说URL> [选项]
```

### 命令行参数

- `url`：必需参数，小说的URL地址（可以是目录页或章节页）
- `-n, --num_chapters`：要爬取的章节数量，默认为0（爬取所有章节）
- `-o, --output_dir`：输出目录，默认为"novels"
- `-d, --delay`：请求延迟范围（秒），格式为"最小值 最大值"，默认为"1.0 3.0"
- `-c, --chapter`：指定URL是章节页而不是目录页
- `-r, --resume`：启用断点续传，从上次中断的地方继续爬取
- `-l, --log_level`：日志级别，可选值：DEBUG/INFO/WARNING/ERROR/CRITICAL，默认为INFO
- `-p, --concurrency`：并发数量，默认为8

### 使用示例

1. 从目录页爬取所有章节：
```bash
python novel_crawler.py https://example.com/novel/123/
```

2. 从章节页开始爬取，限制爬取10章：
```bash
python novel_crawler.py https://example.com/novel/123/456.html -c -n 10
```

3. 启用断点续传，自定义输出目录：
```bash
python novel_crawler.py https://example.com/novel/123/ -r -o my_novels
```

4. 调整爬取速度和并发数：
```bash
python novel_crawler.py https://example.com/novel/123/ -d 2.0 5.0 -p 4
```

## 输出文件

程序会在指定的输出目录下创建以下文件：

1. 每个章节的单独文件（.md格式）
2. 完整的小说文件（_完整版.md）
3. 进度文件（progress.json）

## 注意事项

1. 请合理设置爬取间隔，避免对目标网站造成过大压力
2. 建议使用代理IP进行爬取，避免IP被封禁
3. 部分网站可能有反爬虫机制，可能需要调整爬取策略
4. 请遵守网站的使用条款和版权规定

## 常见问题

1. 如果遇到爬取失败，可以：
   - 检查网络连接
   - 调整请求延迟时间
   - 降低并发数量
   - 查看日志文件了解详细错误信息

2. 如果章节顺序混乱，可以：
   - 检查日志中的章节排序信息
   - 调整章节识别规则
   - 手动修改章节顺序

## 更新日志

### v1.0.0
- 初始版本发布
- 支持基本的爬取功能
- 支持断点续传
- 支持并发下载

## 贡献指南

欢迎提交问题和改进建议！如果您想贡献代码：1145981448@qq.com
