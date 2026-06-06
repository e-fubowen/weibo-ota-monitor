"""
llm_summarizer.py — 调用 LLM 对 OTA 内容进行结构化总结

可独立运行测试：
    python llm_summarizer.py
"""
import logging
from openai import OpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_MAX_WEIBO_LENGTH, LLM_MAX_OCR_LENGTH

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    return _client


def summarize_ota(brand: str, weibo_text: str, ocr_text: str) -> str:
    if not weibo_text.strip() and not ocr_text.strip():
        return ""

    prompt = f"""你是汽车行业竞品分析师。以下是从竞品微博图片OCR识别的OTA更新内容，可能有少量错别字或断行，请自动纠错理解。

品牌：{brand}
微博正文：{weibo_text[:LLM_MAX_WEIBO_LENGTH]}

图片OCR内容：
{ocr_text[:LLM_MAX_OCR_LENGTH]}

请输出以下结构，没有的字段填"未提及"：

【OTA版本号】：
【支持车型】：
【更新亮点（Top3）】：
- 
- 
- 
【智能驾驶】：
【智能座舱/车机】：
【能耗/续航】：
【其他功能】：
【一句话总结】：（20字以内，突出最大亮点）"""

    try:
        resp = _get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error("LLM 总结失败: %s", e)
        return ""


# ─────────────────────────────────────────────
# 独立测试入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    TEST_BRAND = "小米汽车"
    TEST_WEIBO_TEXT = ""
    TEST_OCR_TEXT = """
[图1]
小米SU7&YU7车主的建议
新增了超级玩具箱-萌宠，多种萌宠上车
新增了个性音效，可选锁车、插枪的音效，支持自定义上传
新增了手机端查看哨兵高危事件
新增了城市车道级导航，准确定位车道，变道提醒更精准
优化了寻位泊车辅助，提升了停车场内通行能力
---
[图5]
商场地库车位级领航
小米汽车OTA1.16
重大版本更新功能体验拉齐
支持SU7 Pro/Max/Ultra/YU7车型
---
[图6]
收费站通行辅助
小米汽车OTA1.16
支持SU7Pro/Max/Ultra/YU7车型
---
[图9]
米家上线车机应用商店
小米汽车OTA1.16
支持全系车型
"""

    logger.info("品牌：%s  模型：%s", TEST_BRAND, LLM_MODEL)
    print("=" * 55)
    result = summarize_ota(TEST_BRAND, TEST_WEIBO_TEXT, TEST_OCR_TEXT)
    print(result if result else "未获得结果，请检查 API Key 和网络")
