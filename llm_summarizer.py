"""
llm_summarizer.py — 调用 LLM 对 OTA 内容进行结构化总结（生产级防御优化版）

可独立运行测试：
    python llm_summarizer.py
"""
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from openai import OpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MAX_OCR_LENGTH, LLM_MAX_WEIBO_LENGTH, LLM_MODEL

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────

REQUIRED_FIELDS = [
    "【OTA版本号】",
    "【支持车型】",
    "【智能驾驶与主动安全】",
    "【智能座舱与车机交互】",
    "【能耗/续航/动力底盘】",
    "【车身/灯语/用车管理/跨界生态】",
    "【稳定性与问题修复】",
    "【一句话总结】",
]

NOT_OTA_SIGNAL = "与OTA升级无关"

SYSTEM_PROMPT = """你是一名精通汽车软硬件架构的顶级竞品分析师，专注于将车企官方"营销化、文案化"的 OTA 发布通告，清洗、重构为高密度、结构化、无损的硬核技术分析报告。

【OCR 文本自动纠错（核心防御）】
输入文本来自图片 OCR，存在因字形相近、断行导致的错别字。加工前必须运用新能源汽车行业知识进行语义对齐和自动修正。
常见 OCR 错字修正示例（错字 → 正确术语）：
  * 氯围灯 / 氛圈灯 / 氪围灯 → 氛围灯
  * 智舵辅助 / 泊干辅助 → 智能泊车辅助
  * 能托优化 / 续航托管 → 能耗优化
  * 刹停距托 → 制动距离
若出现无意义的化工词汇（氯、氪、氢）与汽车零部件拼接，必须根据上下文（灯语、内饰、座椅等）还原为正确汽车术语。

【清洗与转化原则】
1. 剔除修饰性文案，保留功能实体：
   删除：情绪化形容词、类比句、口号（如"出行自带高光"、"少急刹更平顺"、"解锁一路好心情"）
   保留：所有功能名称、技术参数、适用车型、触发条件、生效范围
2. 全量无损：不做 Top N 筛选，所有功能项必须 100% 出现在输出中，不得合并或省略
3. 严禁使用任何 Markdown 列表符号（如 -, *, 1. 等）。每个功能项单独换行，采用"功能项名称：具体描述"格式，1:1 还原原始文本流形态

【分类映射标准】
- 智能驾驶与主动安全：行车辅助、智能泊车(RPA/APA)、AEB、红绿灯预判、主动避让等
- 智能座舱与车机交互：语音大模型、车载屏幕控制、音效、多语言、UI交互、导航出行、HUD显示等
- 能耗/续航/动力底盘：充电管理、续航优化、能耗查看、底盘悬挂调节等
- 车身/灯语/用车管理/跨界生态：车外灯语、氛围灯、车内照明、壁纸皮肤、行车报告、APP端管理、第三方生态联动等
- 稳定性与问题修复：已知 bug 修复、系统稳定性提升、安全合规更新等

【工作流】
在 <thinking> 标签内完成以下三步，每步必须有实质内容，不得跳过：
Step 1 相关性判断：判断输入的微博正文和OCR内容是否与汽车OTA软件升级相关。
  判断标准：必须包含以下任意一项：版本号（如OTA x.xx）、功能新增/优化/修复的描述、支持车型说明。
  若不相关，在 <thinking> 内写明原因，并在退出 </thinking> 标签后【直接输出"与OTA升级无关"】，拒绝输出任何模版结构。
Step 2 纠错：逐句扫描输入，列出所有 OCR 错字及修正结果（格式：错字 → 正确）。若无错字，显式写"未发现错字"。
Step 3 归类：将纠错后的全量功能项按分类映射标准归入对应技术域，以"域名：功能项"格式列出草稿。

完成 </thinking> 后，依据 Step 3 草稿严格按 User 消息中的模版逐一填写。最终输出的结构中严禁包含任何 <thinking> 标签或推理过程。"""

USER_PROMPT_TEMPLATE = """\
品牌：{brand}
微博正文：{weibo_text}

图片OCR内容：
{ocr_text}

请严格按以下模版输出，字段名称不得修改，无内容填"未提及"：

【OTA版本号】：
【支持车型】：
【智能驾驶与主动安全】：
【智能座舱与车机交互】：
【能耗/续航/动力底盘】：
【车身/灯语/用车管理/跨界生态】：
【稳定性与问题修复】：
【一句话总结】：（20字以内，突出最大技术亮点）"""


# ─────────────────────────────────────────────
# 返回值
# ─────────────────────────────────────────────

@dataclass
class SummaryResult:
    """LLM 总结结果"""
    content: str
    success: bool
    brand: str = ""
    attempts: int = 1
    error: str | None = None
    missing_fields: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.success


# ─────────────────────────────────────────────
# 客户端（线程安全单例）
# ─────────────────────────────────────────────

_client: OpenAI | None = None
_client_lock = threading.Lock()


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    return _client


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def _safe_truncate(text: str, max_len: int) -> str:
    """按字符数截断，追加省略提示"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n…（内容已截断）"


def _validate_output(text: str) -> list[str]:
    """返回缺失的必填字段列表，为空则表示校验通过"""
    return [f for f in REQUIRED_FIELDS if f not in text]


def _build_prompt(brand: str, weibo_text: str, ocr_text: str) -> str:
    return USER_PROMPT_TEMPLATE.format(
        brand=brand,
        weibo_text=_safe_truncate(weibo_text, LLM_MAX_WEIBO_LENGTH),
        ocr_text=_safe_truncate(ocr_text, LLM_MAX_OCR_LENGTH),
    )


def _extract_final_content(raw_text: str) -> str:
    """剥离 <thinking>...</thinking> 标签及内部草稿，返回纯净输出"""
    clean = re.sub(r'<thinking>.*?</thinking>', '', raw_text, flags=re.DOTALL)
    return clean.strip()


# ─────────────────────────────────────────────
# 核心函数
# ─────────────────────────────────────────────

def summarize_ota(
    brand: str,
    weibo_text: str,
    ocr_text: str,
    *,
    retries: int = 2,
    retry_delay: float = 1.0,
) -> SummaryResult:
    """
    调用 LLM 对 OTA 内容进行结构化总结。

    Args:
        brand:       车辆品牌名称
        weibo_text:  微博正文
        ocr_text:    图片 OCR 识别文本
        retries:     失败后最多重试次数（默认 2）
        retry_delay: 首次重试等待秒数，后续按指数退避（默认 1.0s）

    Returns:
        SummaryResult，通过 .success 判断是否成功，.content 取结果文本
        error == NOT_OTA_SIGNAL 表示模型判定内容与OTA无关（非接口故障）
    """
    if not weibo_text.strip() and not ocr_text.strip():
        logger.warning("[%s] 输入内容为空，跳过总结", brand)
        return SummaryResult(content="", success=False, brand=brand, error="输入内容为空")

    prompt = _build_prompt(brand, weibo_text, ocr_text)
    last_error: str = ""

    for attempt in range(retries + 1):
        try:
            resp = _get_client().chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=3000,
                temperature=0.1,
            )
            raw_content = resp.choices[0].message.content.strip()

            # 先剥离 thinking，再做所有判断，避免 thinking 草稿干扰
            content = _extract_final_content(raw_content)

            # 相关性拦截：模型判定与 OTA 无关
            if content.strip() == NOT_OTA_SIGNAL:
                logger.info("[%s] 模型判定内容与OTA升级无关，跳过", brand)
                return SummaryResult(
                    content="",
                    success=False,
                    brand=brand,
                    attempts=attempt + 1,
                    error=NOT_OTA_SIGNAL,
                )

            # 字段校验：缺字段记录警告，但不重试（模型已回复，重试改善不了结构）
            missing = _validate_output(content)
            if missing:
                logger.warning("[%s] 输出缺少字段: %s", brand, missing)

            logger.info("[%s] 总结完成（第 %d 次尝试）", brand, attempt + 1)
            return SummaryResult(
                content=content,
                success=True,
                brand=brand,
                attempts=attempt + 1,
                missing_fields=missing,
            )

        except Exception as e:
            last_error = str(e)
            if attempt < retries:
                wait = retry_delay * (2 ** attempt)
                logger.warning("[%s] 第 %d 次请求失败，%.1fs 后重试: %s", brand, attempt + 1, wait, e)
                time.sleep(wait)
            else:
                logger.error("[%s] LLM 总结失败（已重试 %d 次）: %s", brand, retries, e)

    return SummaryResult(
        content="",
        success=False,
        brand=brand,
        attempts=retries + 1,
        error=last_error,
    )


def summarize_batch(
    items: list[dict],
    *,
    retries: int = 2,
) -> list[SummaryResult]:
    """
    批量总结多条 OTA 内容。

    Args:
        items:   列表，每项包含 brand / weibo_text / ocr_text 键
        retries: 同 summarize_ota

    Returns:
        与 items 等长的 SummaryResult 列表
    """
    results = []
    for i, item in enumerate(items, 1):
        brand = item.get("brand", "未知品牌")
        logger.info("批量处理 [%d/%d]: %s", i, len(items), brand)
        result = summarize_ota(
            brand=brand,
            weibo_text=item.get("weibo_text", ""),
            ocr_text=item.get("ocr_text", ""),
            retries=retries,
        )
        results.append(result)
    return results


# ─────────────────────────────────────────────
# 独立测试入口
# ─────────────────────────────────────────────

def _print_result(label: str, result: SummaryResult) -> None:
    print(f"\n{'=' * 60}")
    print(f"▶️  {label}")
    print("=" * 60)
    if result:
        print(result.content)
        if result.missing_fields:
            print(f"\n⚠️  缺失字段：{result.missing_fields}")
    elif result.error == NOT_OTA_SIGNAL:
        print("⏭️  内容与OTA升级无关，已跳过")
    else:
        print(f"❌ 总结失败：{result.error}")
        print("请检查 API Key 和网络配置")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 测试 1：正常 OTA 数据 + OCR 错别字（氯围灯 → 氛围灯）
    _print_result(
        "测试 1：验证正常 OTA 提取及 OCR 自动纠错",
        summarize_ota(
            "广汽传祺",
            "全新传祺智能大模型升级来袭！",
            """
【5月20日】【OTA 5.0】
车载语音大模型
语音点咖啡：语音选定品类、糖度、冰量手机一键支付
车内外氛围
充电灯语+潮酷新款灯语全新上线，灯频实时律动
新增自定义氯围灯控制与氛围调节
智能预判，出行护航
大车智能主动避让
红绿灯智能预判，少急刹更平顺
更多新增优化
驾驶辅助
    AEB对通用障碍物进行预警及辅助制动
    车机偶遇bug一键反馈功能上线
""",
        ),
    )

    # 测试 2：非 OTA 噪声数据（验证相关性拦截）
    _print_result(
        "测试 2：验证非 OTA 相关内容的智能拦截过滤",
        summarize_ota(
            "某车企",
            "恭喜我司5月交付量突破3万台！感谢全体车主的支持，点击链接参与抽奖！",
            "海报内容：5月大捷，蝉联销冠。点击即刻下订。",
        ),
    )