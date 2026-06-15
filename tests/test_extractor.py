from extractor import extract_ota_info


def test_extract_version_with_v_prefix():
    result = extract_ota_info("OTA v2.1.0 发布")
    assert result.get("版本号") == "v2.1.0"


def test_extract_version_without_prefix():
    result = extract_ota_info("版本更新 1.16.0")
    assert result.get("版本号") == "1.16.0"


def test_extract_version_multi_digit():
    result = extract_ota_info("V10.2.30 版本")
    assert result.get("版本号") == "V10.2.30"


def test_extract_no_version():
    result = extract_ota_info("无版本号信息")
    assert "版本号" not in result


def test_extract_date():
    result = extract_ota_info("2026年3月15日更新")
    assert "日期" in result


def test_extract_date_dash():
    result = extract_ota_info("2026-03-15 更新")
    assert "日期" in result


def test_extract_functions():
    result = extract_ota_info("新增哨兵模式、智能驾驶和语音控制")
    funcs = result.get("功能点", "")
    assert "哨兵模式" in funcs
    assert "智能驾驶" in funcs
    assert "语音" in funcs


def test_extract_no_functions():
    result = extract_ota_info("常规优化")
    assert "功能点" not in result


def test_extract_empty_text():
    result = extract_ota_info("")
    assert result == {}


def test_extract_version_and_functions():
    result = extract_ota_info("OTA 1.5.0 新增高速NOA和自动泊车")
    assert result.get("版本号") == "1.5.0"
    assert "高速NOA" in result.get("功能点", "")
    assert "自动泊车" in result.get("功能点", "")
