import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import re
import uuid
import extra_streamlit_components as stx

import requests
from io import BytesIO


@st.cache_data(show_spinner=False)
def load_feishu_price_config():
    """读取飞书配置表，返回广告主配置→单价、回传维度的映射（增强容错版）"""
    app_id = st.secrets["feishu"]["app_id"]
    app_secret = st.secrets["feishu"]["app_secret"]
    spreadsheet_token = st.secrets["feishu"]["spreadsheet_token"]
    sheet_id = st.secrets["feishu"]["sheet_id"]

    token_res = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=30
    )
    token_data = token_res.json()
    if token_data.get("code") != 0:
        return pd.DataFrame(columns=["广告主配置", "单价", "回传维度"])
    access_token = token_data["tenant_access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    range_url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{sheet_id}"
    data_res = requests.get(range_url, headers=headers, timeout=30)
    data_json = data_res.json()
    if data_json.get("code") != 0:
        return pd.DataFrame(columns=["广告主配置", "单价", "回传维度"])

    values = data_json["data"]["valueRange"]["values"]
    if not values or len(values) < 2:
        return pd.DataFrame(columns=["广告主配置", "单价", "回传维度"])

    # 兼容处理：寻找真正包含表头的行（防止第一行是说明文字）
    header_idx = 0
    for idx, row in enumerate(values[:5]):
        row_str = " ".join([str(cell) for cell in row])
        if "广告主配置" in row_str or "单价" in row_str or "回传维度" in row_str:
            header_idx = idx
            break

    df_config = pd.DataFrame(values[header_idx + 1:], columns=values[header_idx])

    # 清理列名空格
    df_config.columns = [str(c).strip() for c in df_config.columns]

    # 统一列名映射
    rename_map = {}
    for col in df_config.columns:
        if "广告主配置" in col or "配置名称" in col:
            rename_map[col] = "广告主配置"
        elif "单价" in col:
            rename_map[col] = "单价"
        elif "回传维度" in col:
            rename_map[col] = "回传维度"
    df_config.rename(columns=rename_map, inplace=True)

    # 确保核心列存在
    for required_col in ["广告主配置", "单价", "回传维度"]:
        if required_col not in df_config.columns:
            df_config[required_col] = "未配置" if required_col != "单价" else 0

    # 清洗关键字段
    df_config["广告主配置"] = df_config["广告主配置"].astype(str).str.strip()

    # 清洗单价字段
    if "单价" in df_config.columns:
        price_series = df_config["单价"].astype(str).str.replace(r'[^\d.-]', '', regex=True)
        df_config["单价"] = pd.to_numeric(price_series, errors="coerce").fillna(0)
    else:
        df_config["单价"] = 0.0

    # 统一回传维度列文本格式
    df_config["回传维度"] = df_config["回传维度"].astype(str).str.strip()

    df_config = df_config.drop_duplicates(subset=["广告主配置"], keep="last")
    return df_config[["广告主配置", "单价", "回传维度"]]


# ==========================================
# 0. 核心配置与新版 JSON 树驱动架构引擎
# ==========================================

@st.cache_data
def load_product_config():
    config_path = "products_config.json"
    config = {"factions": {}}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    factions_dict = config.get("factions", {})
    all_products_flat = [
        {"product": prod_name, "faction": fac_name}
        for fac_name, fac_data in factions_dict.items()
        for prod_name in fac_data.get("products", [])
    ]
    sorted_match_list = sorted(all_products_flat, key=lambda x: len(x["product"]), reverse=True)
    return sorted_match_list, config.get("default_faction", "其他派系"), config.get("default_product", "其他产品")


MATCH_RULE_LIST, DEFAULT_FACTION, DEFAULT_PRODUCT = load_product_config()

SPECIAL_MAPPING = {
    "抖音商城": {"派系": "字节系", "特征": ["乘风", "独立端", "dy_"]},
    "番茄免费小说": {"派系": "字节系", "特征": ["番茄小说"]},
    "悟空浏览器": {"派系": "字节系", "特征": ["悟空"]},
    "抖音": {"派系": "字节系", "特征": ["抖音拉新", "抖音卸载召回"]},
    "淘宝闪购": {"派系": "阿里系", "特征": ["淘宝闪购", "tbsg", "饿了么", "高比单", "高笔单", "闪购夜宵"]},
    "淘宝": {"派系": "阿里系", "特征": ["大航海", "淘宝"]},
    "淘宝联盟": {"派系": "阿里系", "特征": ["淘联"]},
    "uc浏览器": {"派系": "阿里系", "特征": ["ucpl", "UC普拉", "UC拉新", "uc浏览器"]},
    "夸克": {"派系": "阿里系", "特征": ["kk@", "夸克"]},
    "千问": {"派系": "阿里系", "特征": ["tongyi", "通义", "typl", "tydx"]},
    "闲鱼": {"派系": "阿里系", "特征": ["闲鱼付费", "闲鱼U1"]},
    "快手极速版": {"派系": "快手系", "特征": ["快接包-极速版", "快接包极速版", "极速版-ANDROID", "快接包-极速板"]},
    "快手": {"派系": "快手系", "特征": ["快接包-主板", "快接包主站", "主板拉回"]},
    "喜番免费短剧": {"派系": "快手系", "特征": ["喜番"]},
    "腾讯元宝": {"派系": "腾讯系", "特征": ["元宝"]},
    "七猫免费小说": {"派系": "其他派系", "特征": ["七猫", "七猫免费小说"]},
    "soul": {"派系": "其他派系", "特征": ["Soul", "soul"]}
}


def extract_faction_and_product(config_name):
    config_str = str(config_name).strip()
    cleaned_str = config_str
    if "优酷" in config_str:
        cleaned_str = re.sub(r'^(优酷媒体-|优酷-)', '', config_str).strip()

    for product_name, info in SPECIAL_MAPPING.items():
        if any(keyword in cleaned_str for keyword in info["特征"]):
            return info["派系"], product_name

    for rule in MATCH_RULE_LIST:
        if rule["product"] in cleaned_str:
            return rule["faction"], rule["product"]

    if "优酷" in config_str:
        pure_product = re.sub(r'[0-9_\-]+', '', cleaned_str).strip()
        if pure_product and pure_product != "优酷" and pure_product != "优酷媒体":
            return "其他派系", pure_product

    return DEFAULT_FACTION, DEFAULT_PRODUCT


st.set_page_config(page_title="OCPX业务数据全维度分析看板", layout="wide", initial_sidebar_state="expanded")
st.markdown("<h2 style='text-align: center; color: #1F77B4;'>🥑 OCPX 业务数据分析看板</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>欢迎提出使用建议~🍦</p>", unsafe_allow_html=True)
st.divider()

PRESET_RATES = {
    "下单率": ("下单量", "广告主激活量"),
    "次留率": ("次日回访量", "广告主激活量"),
    "三留率": ("3日留存次数", "广告主激活量"),
    "七留率": ("7日留存次数", "广告主激活量"),
    "激活率": ("广告主激活量", "上报广告主次数"),
    "唤醒率": ("唤醒量", "上报广告主次数"),
    "首唤率": ("首唤量", "上报广告主次数"),
    "新登率": ("新登量", "广告主激活量"),
    "首购率": ("首购量", "新登量"),
    "付费率": ("付费人数", "广告主激活量")
}


@st.cache_data(show_spinner=False)
def load_and_clean_data_cached(file_contents, file_name):
    import io
    if file_name.endswith('.csv'):
        for enc in ['utf_8_sig', 'gbk', 'gb18030']:
            try:
                raw_df = pd.read_csv(io.BytesIO(file_contents), encoding=enc)
                break
            except:
                pass
    else:
        try:
            raw_df = pd.read_excel(io.BytesIO(file_contents), engine='calamine')
        except:
            raw_df = pd.read_excel(io.BytesIO(file_contents))

    raw_df.columns = raw_df.columns.str.strip()
    if '广告主平台' in raw_df.columns and '广告主平台名称' not in raw_df.columns:
        raw_df.rename(columns={'广告主平台': '广告主平台名称'}, inplace=True)

    def clean_name(x):
        if pd.isna(x): return "未知"
        s = str(x).strip()
        if s == "" or s.lower() == "nan": return "未知"
        return s.split('_', 1)[-1] if '_' in s else s

    for col in ['广告主平台名称', '媒体平台名称', '广告主平台配置名称']:
        raw_df[col] = raw_df[col].apply(clean_name) if col in raw_df.columns else "未分类"

    if '广告主平台配置名称' in raw_df.columns:
        extracted = [extract_faction_and_product(val) for val in raw_df['广告主平台配置名称']]
        raw_df['派系'] = [e[0] for e in extracted]
        raw_df['产品'] = [e[1] for e in extracted]
    else:
        raw_df['派系'], raw_df['产品'] = DEFAULT_FACTION, DEFAULT_PRODUCT

    raw_df['调度中心ID'] = raw_df['调度中心ID'].astype(str).str.replace('.0', '', regex=False).str.strip().fillna(
        "未关联ID") if '调度中心ID' in raw_df.columns else "未关联ID"

    raw_df['日期'] = pd.to_datetime(raw_df['日期'], errors='coerce').dt.date
    if '小时' in raw_df.columns:
        temp_hours = pd.to_numeric(raw_df['小时'], errors='coerce')
        if temp_hours.notna().any() and ((temp_hours >= 0) & (temp_hours <= 23)).any():
            raw_df['小时'] = temp_hours
        else:
            raw_df['小时'] = np.nan
    else:
        raw_df['小时'] = np.nan

    num_cols = raw_df.select_dtypes(include=['number']).columns.tolist()
    for col in num_cols:
        raw_df[col] = pd.to_numeric(raw_df[col], errors='coerce').fillna(0)

    cond_times = raw_df['媒体上报次数'] < 20 if '媒体上报次数' in raw_df.columns else True
    cond_exp = raw_df['媒体上报曝光数'] < 20 if '媒体上报曝光数' in raw_df.columns else True

    exclude_cols = {'媒体上报次数', '媒体上报曝光数', '调度中心ID', '渠道ID', '小时'}
    other_num_cols = [c for c in num_cols if c not in exclude_cols]

    if other_num_cols:
        cond_others_zero = (raw_df[other_num_cols] == 0).all(axis=1)
    else:
        cond_others_zero = True

    dead_rows_mask = cond_times & cond_exp & cond_others_zero
    raw_df = raw_df[~dead_rows_mask].reset_index(drop=True)

    if '广告主激活量' in raw_df.columns:
        sort_cols = [c for c in ["广告主平台配置名称", "媒体平台名称", "调度中心ID", "日期"] if c in raw_df.columns]
        raw_df = raw_df.sort_values(by=sort_cols)
        group_cols = [c for c in sort_cols if c != '日期']
        raw_df['前日激活'] = raw_df.groupby(group_cols)['广告主激活量'].shift(1).fillna(0)
    else:
        raw_df['前日激活'] = 0
    return raw_df


@st.cache_data(show_spinner=False)
def get_filtered_dataframe(base_df, start_date, end_date, factions, products, platforms, configs, media, ids):
    mask = (base_df['日期'] >= start_date) & (base_df['日期'] <= end_date)
    if factions: mask &= base_df['派系'].isin(factions)
    if products: mask &= base_df['产品'].isin(products)
    if platforms: mask &= base_df['广告主平台名称'].isin(platforms)
    if configs: mask &= base_df['广告主平台配置名称'].isin(configs)
    if media: mask &= base_df['媒体平台名称'].isin(media)
    if ids: mask &= base_df['调度中心ID'].isin(ids)
    return base_df[mask]


BASE_CACHE_DIR = ".streamlit_file_cache"
os.makedirs(BASE_CACHE_DIR, exist_ok=True)

cookie_manager = stx.CookieManager()
if cookie_manager.get_all() is None:
    st.stop()

user_uuid = cookie_manager.get("persistent_user_uuid")
if not user_uuid:
    user_uuid = str(uuid.uuid4())
    cookie_manager.set("persistent_user_uuid", user_uuid, max_age=365 * 24 * 60 * 60)

USER_CACHE_DIR = os.path.join(BASE_CACHE_DIR, user_uuid)
if not os.path.exists(USER_CACHE_DIR):
    os.makedirs(USER_CACHE_DIR)

CACHE_FILE = os.path.join(USER_CACHE_DIR, "last_processed_data.feather")
META_FILE = os.path.join(USER_CACHE_DIR, "cache_metadata.json")


def save_to_local_cache(df, file_name):
    try:
        df.to_feather(CACHE_FILE)
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump({"file_name": file_name}, f)
    except Exception as e:
        st.warning(f"本地硬盘缓存写入失败: {e}")


def load_from_local_cache():
    if os.path.exists(CACHE_FILE) and os.path.exists(META_FILE):
        try:
            with open(META_FILE, "r", encoding="utf-8") as f:
                meta = json.load(f)
            df = pd.read_feather(CACHE_FILE)
            return df, meta.get("file_name")
        except:
            return None, None
    return None, None


if "cleaned_data" not in st.session_state:
    cached_df, cached_name = load_from_local_cache()
    if cached_df is not None:
        import copy

        temp_df = copy.deepcopy(cached_df)
        for col_name in ["单价", "回传维度", "结算金额"]:
            if col_name not in temp_df.columns:
                if col_name == "单价":
                    temp_df["单价"] = 0
                elif col_name == "回传维度":
                    temp_df["回传维度"] = "未配置"
                else:
                    temp_df["结算金额"] = 0
        st.session_state["cleaned_data"] = temp_df
        st.session_state["file_name"] = cached_name
    else:
        st.session_state["cleaned_data"] = None
        st.session_state["file_name"] = None

col_upload, col_clear = st.columns([4, 1])
with col_upload:
    uploaded_file = st.file_uploader("📥 上传原始报表数据 (支持 .xlsx / .csv)", type=["csv", "xlsx"])
with col_clear:
    st.write("#")
    if st.button("🗑️ 清除缓存数据", use_container_width=True):
        if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
        if os.path.exists(META_FILE): os.remove(META_FILE)
        st.session_state["cleaned_data"] = None
        st.session_state["file_name"] = None
        st.rerun()

if uploaded_file:
    if st.session_state["file_name"] != uploaded_file.name:
        with st.status("🚀 正在清洗大盘数据...", expanded=True) as status:
            file_bytes = uploaded_file.read()
            df_cleaned = load_and_clean_data_cached(file_bytes, uploaded_file.name)
            st.session_state["cleaned_data"] = df_cleaned
            st.session_state["file_name"] = uploaded_file.name
            save_to_local_cache(df_cleaned, uploaded_file.name)
            status.update(label="✅ 数据分析加载完成", state="complete", expanded=False)
        st.toast(f"成功加载文件: {uploaded_file.name}", icon="🔥")

if st.session_state["cleaned_data"] is not None:
    try:
        import copy

        df_raw = copy.deepcopy(st.session_state["cleaned_data"])
        st.caption(f"💾 当前使用数据源: `{st.session_state['file_name']}` (已启用长效 Cookie 隔离与断线自动恢复缓存)")

        # 读取飞书配置表合并匹配
        # 读取飞书配置表合并匹配
        df_price_config = load_feishu_price_config()

        df_raw["广告主平台配置名称"] = df_raw["广告主平台配置名称"].astype(str).str.strip()
        df_price_config["广告主配置"] = df_price_config["广告主配置"].astype(str).str.strip()

        # 【核心修复】先清理底表中可能已经存在的旧配置列，避免 merge 时出现重名后缀冲突
        for col_to_drop in ["单价", "回传维度", "广告主配置"]:
            if col_to_drop in df_raw.columns:
                df_raw.drop(columns=[col_to_drop], inplace=True)

        df_merged = df_raw.merge(
            df_price_config[["广告主配置", "单价", "回传维度"]],
            left_on="广告主平台配置名称",
            right_on="广告主配置",
            how="left"
        )

        if "单价" in df_merged.columns:
            df_merged["单价"] = pd.to_numeric(df_merged["单价"], errors="coerce").fillna(0)
        else:
            df_merged["单价"] = 0.0

        if "回传维度" in df_merged.columns:
            df_merged["回传维度"] = df_merged["回传维度"].fillna("未配置").astype(str)
        else:
            df_merged["回传维度"] = "未配置"

        df_merged.drop(columns=["广告主配置"], errors="ignore", inplace=True)


        # 核心映射逻辑：根据飞书配置里的“回传维度”字段，动态决定结算所依据的量级指标
        # 兼容匹配常见回传维度名称：激活、广告主激活量、唤醒、唤醒量、新登、新登量、首唤、首唤量、下单、下单量、首购、首购量、付费、付费数、页面访问数等
        def get_settlement_quantity(row):
            dim = str(row.get("回传维度", "")).strip()
            # 如果配置为具体维度，映射到对应的列
            if any(k in dim for k in ["激活", "广告主激活"]):
                col_name = "广告主激活量"
            elif any(k in dim for k in ["唤醒"]):
                col_name = "唤醒量" if "唤醒量" in row else "唤醒"
            elif any(k in dim for k in ["新登"]):
                col_name = "新登量" if "新登量" in row else "新登"
            elif any(k in dim for k in ["首唤"]):
                col_name = "首唤量" if "首唤量" in row else "首唤"
            elif any(k in dim for k in ["下单"]):
                col_name = "下单量" if "下单量" in row else "下单"
            elif any(k in dim for k in ["首购"]):
                col_name = "首购量" if "首购量" in row else "首购"
            elif any(k in dim for k in ["付费"]):
                col_name = "付费人数" if "付费人数" in row else ("付费量" if "付费量" in row else "付费")
            elif any(k in dim for k in ["页面访问", "访问"]):
                col_name = "页面访问数" if "页面访问数" in row else "页面访问"
            else:
                # 默认兜底使用广告主激活量
                col_name = "广告主激活量"

            val = row.get(col_name, 0)
            return pd.to_numeric(val, errors="coerce") if pd.notna(val) else 0.0


        if "广告主激活量" in df_merged.columns:
            # 计算结算金额 = 动态回传维度对应的数据量 × 单价
            quantities = df_merged.apply(get_settlement_quantity, axis=1)
            df_merged["结算金额"] = quantities * df_merged["单价"]
        else:
            df_merged["结算金额"] = 0

        st.session_state["cleaned_data"] = df_merged
        df = df_merged

        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()

        with st.sidebar:
            st.markdown("<h3 style='color: #1F77B4;'>📅 时间周期</h3>", unsafe_allow_html=True)
            valid_dates = df['日期'].dropna()
            min_d, max_d = (valid_dates.min(), valid_dates.max()) if not valid_dates.empty else (None, None)
            selected_date_range = st.date_input("选择周期范围", value=(min_d, max_d))
            st.divider()

            st.markdown("<h3 style='color: #1F77B4;'>🔍 漏斗筛选</h3>", unsafe_allow_html=True)

            faction_options = sorted(df["派系"].unique().tolist())
            select_all_factions = st.checkbox("🔗 全选所有派系", value=False)
            t_factions = st.multiselect("1. 派系筛选", options=faction_options,
                                        default=faction_options if select_all_factions else [])

            sub_df_for_product = df[df["派系"].isin(t_factions)] if t_factions else df
            product_options = sorted(sub_df_for_product["产品"].unique().tolist())
            select_all_products = st.checkbox("🔗 全选当前派系下产品", value=False)
            t_products = st.multiselect("2. product筛选", options=product_options,
                                        default=product_options if select_all_products else [])

            sub_df_for_platform = sub_df_for_product[
                sub_df_for_product["产品"].isin(t_products)] if t_products else sub_df_for_product
            t_platforms = st.multiselect("3. 广告主平台名称筛选",
                                         options=sorted(sub_df_for_platform["广告主平台名称"].unique().tolist()))

            sub_df_for_config = sub_df_for_platform[
                sub_df_for_platform["广告主平台名称"].isin(t_platforms)] if t_platforms else sub_df_for_platform
            t_configs = st.multiselect("4. 配置号筛选",
                                       options=sorted(sub_df_for_config["广告主平台配置名称"].unique().tolist()))

            sub_df_for_media = sub_df_for_config[
                sub_df_for_config["广告主平台配置名称"].isin(t_configs)] if t_configs else sub_df_for_config
            t_media = st.multiselect("5. 媒体筛选", options=sorted(sub_df_for_media["媒体平台名称"].unique().tolist()))

            sub_df_for_id = sub_df_for_media[
                sub_df_for_media["媒体平台名称"].isin(t_media)] if t_media else sub_df_for_media
            t_ids = st.multiselect("6. 调度中心ID筛选", options=sorted(sub_df_for_id["调度中心ID"].unique().tolist()))

            st.divider()
            st.markdown("<h3 style='color: #1F77B4;'>📈 率指标池</h3>", unsafe_allow_html=True)
            selected_rate_names = []
            col1, col2 = st.columns(2)
            for i, name in enumerate(PRESET_RATES.keys()):
                with col1 if i % 2 == 0 else col2:
                    if st.checkbox(name, value=name in ["下单率", "次留率"]): selected_rate_names.append(name)

            show_cvr = st.checkbox("⚙️ 开启 自定义CVR", value=True)
            cvr_name = f"CVR({c_num}/{c_den})" if show_cvr and (c_num := st.selectbox("CVR 分子", numeric_cols,
                                                                                      index=numeric_cols.index(
                                                                                          '广告主激活量') if '广告主激活量' in numeric_cols else 0)) and (
                                                      c_den := st.selectbox("CVR 分分母", numeric_cols,
                                                                            index=numeric_cols.index(
                                                                                '上报广告主次数') if '上报广告主次数' in numeric_cols else 0)) else None

            enable_wow = st.toggle("开启指标环比 (对比前一日)", value=False)
            wow_targets = st.multiselect("选择看环比的数值列", numeric_cols, default=[f for f in ["广告主激活量"] if
                                                                                      f in numeric_cols]) if enable_wow else []

            enable_alert = st.toggle("开启爆红预警高亮", value=False)
            alert_rules = []
            if enable_alert:
                alert_targets_pool = selected_rate_names + ([cvr_name] if cvr_name else [])
                chosen_targets = st.multiselect("选择需要预警的指标", alert_targets_pool)
                for target in chosen_targets:
                    st.markdown(f"**{target} 预警配置**")
                    c_logic, c_val = st.columns([1, 2])
                    with c_logic: logic = st.selectbox("逻辑", ["<", "<=", ">", ">=", "=="], key=f"lg_{target}")
                    with c_val: val = st.number_input("阈值(%)", value=5.0, step=0.1, key=f"val_{target}")
                    alert_rules.append({"target": target, "logic": logic, "val": val})

            s_metrics = st.multiselect("表内显示指标", options=numeric_cols,
                                       default=[f for f in ["广告主激活量", "新登量", "下单量", "单价", "结算金额"] if
                                                f in numeric_cols])
            show_daily = st.checkbox("开启下钻分日", value=True)

        if not isinstance(selected_date_range, (list, tuple)) or len(selected_date_range) < 2:
            st.info("⏳ 请在左侧边栏选择完整的【开始日期】和【结束日期】...")
            st.stop()

        f_df_global = get_filtered_dataframe(
            df,
            selected_date_range[0],
            selected_date_range[1],
            tuple(t_factions),
            tuple(t_products),
            tuple(t_platforms),
            tuple(t_configs),
            tuple(t_media),
            tuple(t_ids)
        )


        def process_view(dims, src_df):
            if src_df.empty: return pd.DataFrame(), []

            base_needed = set(
                list(s_metrics) + ["次日回访量", "3日留存次数", "7日留存次数", "前日激活", "结算金额", "广告主激活量"])
            for r_name in PRESET_RATES: base_needed.update(PRESET_RATES[r_name])
            if show_cvr: base_needed.update([c_num, c_den])

            agg_map = {}
            for c in base_needed:
                if c in src_df.columns:
                    if c == "单价":
                        agg_map[c] = lambda x: x.iloc[0] if not x.empty else 0
                    else:
                        agg_map[c] = 'sum'

            for c in agg_map:
                if c != "单价":
                    src_df[c] = pd.to_numeric(src_df[c], errors='coerce').fillna(0)

            summary = src_df.groupby(dims).agg(agg_map).reset_index()

            if "结算金额" in summary.columns and "广告主激活量" in summary.columns and "单价" in summary.columns:
                summary["单价"] = np.where(
                    summary["广告主激活量"] > 0,
                    summary["结算金额"] / summary["广告主激活量"],
                    summary["单价"]
                )

            sort_target = [c for c in ["广告主激活量", "新登量"] if c in summary.columns]
            if sort_target: summary = summary.sort_values(by=sort_target, ascending=False)
            summary["日期"] = "✨ 汇总"

            if show_daily:
                daily = src_df.groupby(dims + ["日期"]).agg(agg_map).reset_index()

                daily["_tmp_next_stay"] = daily.groupby(dims)["次日回访量"].shift(-1).fillna(0)
                daily["_tmp_3d_stay"] = daily.groupby(dims)["3日留存次数"].shift(-3).fillna(0)
                daily["_tmp_7d_stay"] = daily.groupby(dims)["7日留存次数"].shift(-7).fillna(0)

                if enable_wow and wow_targets:
                    for col in wow_targets: daily[f"prev_{col}"] = daily.groupby(dims)[col].shift(1)

                summary_ordered = summary.copy()
                summary_ordered['_order'] = range(len(summary_ordered))
                daily_ordered = daily.merge(summary_ordered[dims + ['_order']], on=dims, how='inner')

                summary_ordered['日期'] = "✨ 汇总"
                final = pd.concat([summary_ordered, daily_ordered], ignore_index=True)
                final = final.sort_values(by=['_order', '日期'], ascending=[True, False]).drop(columns=['_order'])
            else:
                final = summary

            if "广告主平台配置名称" in dims and "媒体平台名称" not in dims:
                total_row = src_df.agg(agg_map).to_frame().T
                if "派系" in dims: total_row["派系"] = "【全大盘派系汇总】"
                if "产品" in dims: total_row["产品"] = "【全大盘产品汇总】"
                if "广告主平台名称" in dims: total_row["广告主平台名称"] = "【全平台名称汇总】"
                total_row["广告主平台配置名称"], total_row["日期"] = "【全配置号汇总】", "✨ 汇总"

                if "结算金额" in total_row.columns and "广告主激活量" in total_row.columns:
                    tot_act = float(total_row["广告主激活量"].iloc[0])
                    tot_amt = float(total_row["结算金额"].iloc[0])
                    total_row["单价"] = (tot_amt / tot_act) if tot_act > 0 else 0.0

                final = pd.concat([total_row, final], ignore_index=True)

            for name, (n, d) in PRESET_RATES.items():
                if n in final.columns and d in final.columns:
                    num = pd.to_numeric(final[n], errors='coerce').fillna(0)
                    den = pd.to_numeric(final[d], errors='coerce').fillna(0)

                    if name == "次留率" and "_tmp_next_stay" in final.columns:
                        num = np.where(final["日期"] != "✨ 汇总", final["_tmp_next_stay"], num)
                    elif name == "三留率" and "_tmp_3d_stay" in final.columns:
                        num = np.where(final["日期"] != "✨ 汇总", final["_tmp_3d_stay"], num)
                    elif name == "七留率" and "_tmp_7d_stay" in final.columns:
                        num = np.where(final["日期"] != "✨ 汇总", final["_tmp_7d_stay"], num)

                    final[name] = np.where(den > 0, (num / den) * 100, 0.0)

            if show_cvr and c_num in final.columns and c_den in final.columns:
                final[cvr_name] = np.where(final[c_den] != 0, (final[c_num] / final[c_den]) * 100, 0.0)

            wow_col_names = []
            if enable_wow and wow_targets:
                for col in wow_targets:
                    p_col = f"prev_{col}"
                    if p_col in final.columns:
                        w_col = f"{col}环比"
                        final[w_col] = np.where((final["日期"] != "✨ 汇总") & (final[p_col] != 0),
                                                ((final[col] - final[p_col]) / final[p_col].abs()) * 100, 0.0)
                        final[w_col] = final[w_col].replace([np.inf, -np.inf], 0).fillna(0)
                        wow_col_names.append(w_col)

            for c in s_metrics:
                if c in final.columns and c != "单价":
                    final[c] = final[c].fillna(0).astype(int)
            return final, wow_col_names


        res1, w1 = process_view(["派系", "产品", "广告主平台名称", "广告主平台配置名称"], f_df_global)

        if not f_df_global.empty:
            active_kpi_pool = [{"name": m, "type": "number"} for m in s_metrics if m in f_df_global.columns] + \
                              [{"name": r, "type": "rate"} for r in selected_rate_names if r in PRESET_RATES]
            if show_cvr and cvr_name: active_kpi_pool.append({"name": cvr_name, "type": "rate"})
            if not active_kpi_pool: active_kpi_pool = [{"name": c, "type": "number"} for c in
                                                       ["广告主激活量", "下单量", "新登量"] if f_df_global.columns]

            kpi_cols = st.columns(min(len(active_kpi_pool), 4))
            card_colors = ["#1F77B4", "#FF7F0E", "#2CA02C", "#9467BD"]

            for idx, kpi in enumerate(active_kpi_pool[:4]):
                name, kpi_type = kpi["name"], kpi["type"]
                color = card_colors[idx % 4]
                with kpi_cols[idx]:
                    if kpi_type == "number":
                        if name == "单价":
                            avg_p = f_df_global["单价"].mean() if not f_df_global.empty else 0
                            st.markdown(
                                f'<div style="background-color: #F8F9FA; padding: 15px; border-radius: 8px; border-left: 5px solid {color}; box-shadow: 2px 2px 8px rgba(0,0,0,0.04);"> <span style="font-size: 13px; color: #666; font-weight: 500;">📊 周期平 {name}</span> <h3 style="margin: 3px 0 0 0; color: #2C3E50; font-size: 24px;">{avg_p:.2f}</h3></div>',
                                unsafe_allow_html=True)
                        else:
                            st.markdown(
                                f'<div style="background-color: #F8F9FA; padding: 15px; border-radius: 8px; border-left: 5px solid {color}; box-shadow: 2px 2px 8px rgba(0,0,0,0.04);"> <span style="font-size: 13px; color: #666; font-weight: 500;">📊 周期总 {name}</span> <h3 style="margin: 3px 0 0 0; color: #2C3E50; font-size: 24px;">{int(f_df_global[name].sum()):,}</h3></div>',
                                unsafe_allow_html=True)
                    else:
                        rate_val = res1[name].iloc[
                            0] if 'res1' in locals() and not res1.empty and name in res1.columns else 0.0
                        st.markdown(
                            f'<div style="background-color: #F8F9FA; padding: 15px; border-radius: 8px; border-left: 5px solid {color}; box-shadow: 2px 2px 8px rgba(0,0,0,0.04);"> <span style="font-size: 13px; color: #666; font-weight: 500;">📈 大盘综合 {name}</span> <h3 style="margin: 3px 0 0 0; color: #2C3E50; font-size: 24px;">{rate_val:.2f}%</h3></div>',
                            unsafe_allow_html=True)
            st.write("")
            st.divider()
        else:
            st.warning("⚠️ 当前筛选组合下无数据，请检查侧边栏多选框是否勾选。")


        def style_and_display(res_df, base_dims, wow_cols, table_key="default"):
            if res_df.empty: return st.info("所选筛选条件下无数据")
            table_rates = selected_rate_names + ([cvr_name] if show_cvr else []) + wow_cols

            base_cols = [d for d in base_dims if d in res_df.columns]
            target_metrics = [c for c in s_metrics if c in res_df.columns and c not in ["单价", "结算金额"]]
            special_cols = [c for c in ["单价", "结算金额"] if c in res_df.columns]

            if "广告主平台配置名称" in base_cols:
                idx = base_cols.index("广告主平台配置名称")
                disp_cols = base_cols[:idx + 1] + special_cols + base_cols[idx + 1:] + target_metrics + [r for r in
                                                                                                         table_rates if
                                                                                                         r in res_df.columns]
            else:
                disp_cols = base_cols + special_cols + target_metrics + [r for r in table_rates if r in res_df.columns]

            def apply_style(row):
                styles = ['' for _ in row]
                conf_name = str(row.get('广告主平台配置名称', ''))
                fac_name = str(row.get('派系', ''))
                date_val = str(row.get('日期', ''))

                if '【全配置号汇总】' in conf_name or '【全大盘派系汇总】' in fac_name:
                    styles = ['background-color: #FFF2CC; font-weight: bold; color: #D68910' for _ in styles]
                elif '✨ 汇总' in date_val:
                    styles = ['background-color: #E6F3FF; font-weight: bold; color: #1f77b4' for _ in styles]

                if enable_alert:
                    for rule in alert_rules:
                        target, logi, threshold = rule['target'], rule['logic'], rule['val']
                        if target in disp_cols and (val := float(row[target])) is not None:
                            if (logi == "<" and val < threshold) or (logi == "<=" and val <= threshold) or \
                                    (logi == ">" and val > threshold) or (logi == ">=" and val >= threshold) or \
                                    (logi == "==" and abs(val - threshold) < 0.01):
                                styles[disp_cols.index(
                                    target)] = 'color: white; font-weight: bold; background-color: #FF4B4B;'

                for w_col in wow_cols:
                    if w_col in disp_cols:
                        val = float(row[w_col])
                        if val > 0:
                            styles[disp_cols.index(w_col)] += '; color: #d00000; font-weight: bold;'
                        elif val < 0:
                            styles[disp_cols.index(w_col)] += '; color: #008000; font-weight: bold;'
                return styles

            c_config = {"日期": st.column_config.TextColumn(width="small")} if "日期" in disp_cols else {}
            for col in [r for r in table_rates if r in res_df.columns]: c_config[col] = st.column_config.NumberColumn(
                format="%.2f%%", width="small")
            for col in [c for c in s_metrics if c in res_df.columns]:
                if col == "单价":
                    c_config[col] = st.column_config.NumberColumn(format="%.2f")
                else:
                    c_config[col] = st.column_config.NumberColumn(format="%d")

            dynamic_height = min(35 * len(res_df) + 40, 700)

            st.dataframe(
                res_df[disp_cols].style.apply(apply_style, axis=1),
                use_container_width=True,
                hide_index=True,
                column_config=c_config,
                height=dynamic_height
            )

            csv_data = res_df[disp_cols].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label=f"📥 导出此分析数据",
                data=csv_data,
                file_name=f"OCPX_导出_{table_key}.csv",
                mime="text/csv",
                key=f"download_{table_key}"
            )
            st.divider()


        tab1, tab2, tab3 = st.tabs(["1️⃣ 配置号明细", "2️⃣ 媒体平台明细", "3️⃣ 调度ID明细"])

        # --- Tab 1: 配置号明细 ---
        with tab1:
            st.subheader("配置号分析视角")
            style_and_display(
                res1.head(700) if not res1.empty else res1,
                ["派系", "产品", "广告主平台名称", "广告主平台配置名称"] + (["日期"] if show_daily else []),
                w1,
                table_key="配置号明细"
            )

        # --- Tab 2: 媒体平台明细（无专属筛选，完整保留配置号与覆盖文案） ---
        with tab2:
            st.subheader("媒体平台分析视角")

            # 直接使用全局数据集计算，不加 multiselect 过滤
            res2, w2 = process_view(["产品", "广告主平台配置名称", "媒体平台名称"], f_df_global)

            if not res2.empty and "媒体平台名称" in res2.columns:
                summary_rows2 = res2[res2["日期"] == "✨ 汇总"] if "日期" in res2.columns else res2
                active_media = summary_rows2[summary_rows2["媒体平台名称"] != "✨ 汇总"][
                    "媒体平台名称"].unique().tolist()
                media_str = " / ".join(active_media) if active_media else "无"
                st.markdown(f"💡 当前筛选组合内共覆盖 **{len(active_media)}** 个媒体：`{media_str}`")
            else:
                st.markdown("💡 当前筛选组合内无匹配媒体数据")

            style_and_display(
                res2,
                ["产品", "广告主平台配置名称", "媒体平台名称"] + (["日期"] if show_daily else []),
                w2,
                table_key="媒体平台明细"
            )

        # --- Tab 3: 调度ID明细（无专属筛选，完整保留配置号与ID统计） ---
        with tab3:
            st.subheader("调度ID分析视角")

            # 直接使用全局数据集计算，不加 multiselect 过滤
            res3, w3 = process_view(["产品", "广告主平台配置名称", "媒体平台名称", "调度中心ID"], f_df_global)

            if not res3.empty and "调度中心ID" in res3.columns and "媒体平台名称" in res3.columns:
                sub_t3 = res3[res3["日期"] == "✨ 汇总"] if "日期" in res3.columns else res3
                sub_t3_filtered = sub_t3[(sub_t3["媒体平台名称"] != "✨ 汇总") & (sub_t3["调度中心ID"] != "✨ 汇总")]
                if not sub_t3_filtered.empty:
                    media_id_count = sub_t3_filtered.groupby("媒体平台名称")["调度中心ID"].nunique().reset_index()
                    id_detail = " ｜ ".join([f"**{row['媒体平台名称']}** ({row['调度中心ID']}个ID)" for _, row in
                                            media_id_count.iterrows()])
                else:
                    id_detail = "当前组合无关联调度ID"
            else:
                id_detail = "无数据"

            st.markdown(f"🆔 **调度ID全量统计**：{id_detail}")

            style_and_display(
                res3,
                ["产品", "广告主平台配置名称", "媒体平台名称", "调度中心ID"] + (["日期"] if show_daily else []),
                w3,
                table_key="调度ID明细"
            )

    except Exception as e:
        st.error(f"处理出现技术错误: {e}")
else:
    st.info("👋 欢迎使用！请在上方上传 OCPX 业务数据报表!\nps：可上传完整底表，无需筛选字段～")
