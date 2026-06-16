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

SYSTEM_PROMPT = """你是一名精通汽车软硬件架构的顶级竞品分析师，专注于将车企官方"营销化、文案化"的 OTA 发布或新车上市通告，清洗、重构为高密度、结构化、无损的硬核技术分析报告。

【OCR 文本自动纠错（核心防御）】
输入文本来自图片 OCR，存在错别字。加工前必须运用新能源汽车行业知识进行语义对齐和自动修正。
常见 OCR 错字修正示例（错字 → 正确术语）：
  * 氯围灯 / 氛圈灯  → 氛围灯
  * 极氯 / 极氮  → 极氪
  * 智舵辅助 / 泊干辅助 / 泊东漫消 → 智能泊车辅助 / 泊车建造中
  * 互厅 / 能托优化 / 续航托管 → 互斥 / 能耗优化
若出现无意义的化工词汇（氯、氪、氢）与汽车零部件拼接，必须根据上下文还原为正确汽车术语。

【硬核清洗与信息留存原则】
1. 区分“情感修饰”与“技术细节”（关键）：
   - 必须剔除的情感修饰词：口号、形容词、情绪化表达（如"出行自带高光"、"解锁一路好心情"、"让人直呼过瘾"）。
   - 必须 100% 保留的技术细节：技术原理（如三维渲染、全景声场）、软硬件配置（如8155芯片、扬声器功率）、触发路径（如通过下拉屏、车辆设置开启）、前置条件与互斥逻辑（如剩余电量>30%、与Eva语音助手互斥）。
2. 全量无损：不做摘要，不做 Top N 筛选，原始文本中提及的所有功能点、配置项必须 100% 映射到输出中，不得漏报、合并或忽略。
3. 文本形态规范：严禁使用 Markdown 列表符号（如 -, *, 1. 等）。每个功能项或信息点必须单独换行，采用"功能项名称或技术参数：具体描述（含触发条件/路径/互斥逻辑）"的非列表形态呈现。

【分类映射标准】
- 智能驾驶与主动安全：行车辅助、智能泊车、AEB、车道级导航与定位指引、路网渲染、哨兵模式等。
- 智能座舱与车机交互：车载应用生态（K歌、游戏、播客、有声书）、车载音响与声场、语音助手、智能多屏交互、UI控制等。
- 能耗/续航/动力底盘：充电管理、续航优化、能耗看板、底盘悬挂调节、哨兵模式地点能耗优化等。
- 车身/灯语/用车管理/跨界生态：车外灯语、车内照明、升级注意事项、升级安装前置条件、手机APP端管理等。
- 稳定性与问题修复：已知 bug 修复、系统稳定性提升、系统合规更新等。

【工作流】
在 <thinking> 标签内完成以下三步，每步必须展示详细推导，不得跳过：
Step 1 相关性判断：判断输入内容是否与汽车OTA软件升级或新车发布上市相关。若不相关，退出 </thinking> 后直接输出"与车企监控无关"，拒绝输出任何模版。
Step 2 纠错日志：逐句扫描输入，列出所有 OCR 错字及修正结果（格式：错字 → 正确术语）。
Step 3 无损功能提炼草稿：将通告中所有的技术功能、触发路径、前置限制条件，1:1 不漏地提炼成草稿，并明确其分类。

完成 </thinking> 后，依据 Step 3 草稿严格按用户给出的模版逐一填写。最终输出的结构中严禁包含任何 <thinking> 标签或推理过程。"""

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