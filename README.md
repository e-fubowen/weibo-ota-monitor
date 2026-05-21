# 竞品OTA微博监控

定时抓取指定车企官方微博的OTA升级公告，并利用OCR识别图片中的升级内容。

## 功能
- 支持批量监控数十个竞品官微
- 按关键词精准搜索OTA相关微博
- 自动下载并OCR识别图片中的版本号、功能点
- 结果输出为CSV表格

## 使用方法
1. 安装依赖：`pip install -r requirements.txt`
2. 设置环境变量 `WEIBO_COOKIE`（从浏览器复制你的微博Cookie）
3. 修改 `COMPETITOR_UIDS` 列表，填入竞品微博UID
4. 运行：`python 竞品OTA微博爬取.py`

## 注意事项
- 请遵守微博的robots.txt和服务条款
- 仅用于个人竞品分析，请勿大规模高频爬取