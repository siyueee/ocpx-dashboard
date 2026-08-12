import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import re
import uuid
import extra_streamlit_components as stx
import requests

# ====================== 全局常量 ======================
TARGET_MAP = {
    "激活": "广告主激活量",
    "唤醒": "唤醒量",
    "新登": "新登量",
    "首唤": "首唤量",
    "下单": "下单量",
    "首购": "首购量",
    "付费": "付费数",
    "页面访问数": "页面访问数"
}

PRESET_RATES = {
    "下单率": ("下单量", "广告主激活量"),
    "次留率": ("次日回访量", "广告主激活量"),
    "三留率": ("3日留存次数", "广告主激活量"),
    "七留率": ("7日留存次数", "广告主激活量"),
    "点击率": ("上报广告主次数", "上报广告主曝光数"),
    "激活率": ("广告主激活量", "上报广告主次数"),
    "唤醒率": ("唤醒量", "上报广告主次数"),
    "首唤率": ("首唤量", "上报广告主次数"),
    "新登率": ("新登量", "广告主激活量"),
    "首购率": ("首购量", "新登量"),
    "付费率": ("付费人数", "广告主激活量")
}

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

BASE_CACHE_DIR = ".streamlit_file_cache"

# ====================== 工具函数 ======================

def clean_name(x, default="未知"):
    """统一的配置名截断函数 — 底表清洗和飞书配置匹配共用，确保两边 key 永远一致"""
    if pd.isna(x): return default
    s = str(x).strip()
    if s == "" or s.lower() == "nan": return default
    return s.split('_', 1)[-1] if '_' in s else s


@st.cache_data(show_spinner=True, ttl=300)
def load_feishu_price_config():
    """读取飞书多维表格配置，缓存5分钟自动刷新"""
    app_id = st.secrets["feishu"]["app_id"]
    app_secret = st.secrets["feishu"]["app_secret"]
    spreadsheet_token = st.secrets["feishu"]["spreadsheet_token"]
    sheet_id = st.secrets["feishu"]["sheet_id"]

    empty_df = pd.DataFrame(columns=["广告主配置", "单价", "回传维度"])

    try:
        token_res = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=30
        )
        token_data = token_res.json()
        if token_data.get("code") != 0:
            st.error(f"飞书鉴权失败: {token_data.get('msg', '未知错误')}")
            return empty_df
        access_token = token_data["tenant_access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        range_url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{sheet_id}"
        data_res = requests.get(range_url, headers=headers, timeout=30)
        data_json = data_res.json()
        if data_json.get("code") != 0:
            st.error(f"飞书表格读取失败: {data_json.get('msg', '未知错误')}")
            return empty_df

        values = data_json["data"]["valueRange"]["values"]
        if not values or len(values) < 2:
            st.warning("飞书表格无数据或只有表头")
            return empty_df

        df_config = pd.DataFrame(values[1:], columns=values[0])
        rename_map = {}
        for col in df_config.columns:
            col_str = str(col).strip()
            if col_str == "None" or col_str == "":
                continue
            if col_str in ("配置号", "广告主配置", "配置名称") or ("广告主" in col_str and "配置" in col_str):
                rename_map[col] = "广告主配置"
            elif col_str in ("合作价格", "单价", "结算单价", "价格") or ("单价" in col_str) or ("价格" in col_str):
                rename_map[col] = "单价"
            elif col_str in ("回传维度", "维度") or ("回传" in col_str):
                rename_map[col] = "回传维度"
        df_config.rename(columns=rename_map, inplace=True)
        df_config = df_config.loc[:, ~df_config.columns.isin([None, "None", ""])]

        missing = [c for c in ["广告主配置", "单价", "回传维度"] if c not in df_config.columns]
        if missing:
            st.error(f"飞书表格缺少必要列: {missing}，实际列: {list(df_config.columns)}")
            return empty_df

        df_config["广告主配置"] = df_config["广告主配置"].apply(lambda x: clean_name(x, default=""))
        df_config["单价"] = pd.to_numeric(df_config["单价"], errors="coerce").fillna(0)
        df_config["回传维度"] = df_config["回传维度"].astype(str).str.strip()
        df_config = df_config[df_config["广告主配置"] != ""]
        df_config = df_config.drop_duplicates(subset=["广告主配置"], keep="first")
        return df_config.reset_index(drop=True)
    except requests.RequestException as e:
        st.error(f"飞书网络请求失败: {e}")
        return empty_df
    except Exception as e:
        st.error(f"飞书配置加载异常: {e}")
        return empty_df


@st.cache_data(show_spinner=False, ttl=300)
def _get_product_config():
    """懒加载：只在第一次使用时读文件"""
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


def extract_faction_and_product(config_name, match_rules, default_faction, default_product):
    """根据广告配置名称自动识别派系、产品名称"""
    config_str = str(config_name).strip()
    cleaned_str = config_str
    if "优酷" in config_str:
        cleaned_str = re.sub(r'^(优酷媒体-|优酷-)', '', config_str).strip()

    for product_name, info in SPECIAL_MAPPING.items():
        if any(keyword in cleaned_str for keyword in info["特征"]):
            return info["派系"], product_name

    for rule in match_rules:
        if rule["product"] in cleaned_str:
            return rule["faction"], rule["product"]

    if "优酷" in config_str:
        pure_product = re.sub(r'[0-9_\-]+', '', cleaned_str).strip()
        if pure_product and pure_product != "优酷" and pure_product != "优酷媒体":
            return "其他派系", pure_product

    return default_faction, default_product


@st.cache_data(show_spinner=False, ttl=300)
def load_and_clean_data_cached(file_contents, file_name):
    """读取上传文件、统一清洗格式，生成标准化底表"""
    import io
    match_rules, default_faction, default_product = _get_product_config()

    if file_name.endswith('.csv'):
        raw_df = None
        for enc in ['utf_8_sig', 'gbk', 'gb18030']:
            try:
                raw_df = pd.read_csv(io.BytesIO(file_contents), encoding=enc)
                break
            except Exception:
                continue
    else:
        try:
            raw_df = pd.read_excel(io.BytesIO(file_contents), engine='calamine')
        except Exception:
            raw_df = pd.read_excel(io.BytesIO(file_contents))

    raw_df.columns = raw_df.columns.str.strip()
    if '广告主平台' in raw_df.columns and '广告主平台名称' not in raw_df.columns:
        raw_df.rename(columns={'广告主平台': '广告主平台名称'}, inplace=True)

    for col in ['广告主平台名称', '媒体平台名称', '广告主平台配置名称']:
        if col in raw_df.columns:
            raw_df[col] = raw_df[col].apply(clean_name)
        else:
            raw_df[col] = "未分类"

    if '广告主平台配置名称' in raw_df.columns:
        extracted = [extract_faction_and_product(val, match_rules, default_faction, default_product)
                     for val in raw_df['广告主平台配置名称']]
        raw_df['派系'] = [e[0] for e in extracted]
        raw_df['产品'] = [e[1] for e in extracted]
    else:
        raw_df['派系'], raw_df['产品'] = default_faction, default_product

    raw_df['调度中心ID'] = (raw_df['调度中心ID']
                            .astype(str).str.replace('.0', '', regex=False).str.strip().fillna("未关联ID")
                            if '调度中心ID' in raw_df.columns else "未关联ID")

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
    cond_others_zero = (raw_df[other_num_cols] == 0).all(axis=1) if other_num_cols else True
    dead_rows_mask = cond_times & cond_exp & cond_others_zero
    raw_df = raw_df[~dead_rows_mask].reset_index(drop=True)

    if '广告主激活量' in raw_df.columns:
        sort_cols = [c for c in ["广告主平台配置名称", "媒体平台名称", "调度中心ID", "日期"] if c in raw_df.columns]
        raw_df = raw_df.sort_values(by=sort_cols)
        group_cols = [c for c in sort_cols if c != '日期']
        raw_df['前日激活'] = raw_df.groupby(group_cols)['广告主激活量'].shift(1).fillna(0)
    else:
        raw_df['前日激活'] = 0

    if "负责人" not in raw_df.columns:
        raw_df["负责人"] = ""
    return raw_df


@st.cache_data(show_spinner=False, ttl=300)
def get_filtered_dataframe(base_df, start_date, end_date,
                           factions: tuple, products: tuple, platforms: tuple,
                           configs: tuple, media: tuple, ids: tuple, owners: tuple):
    """根据侧边栏筛选条件过滤基础数据 — 全参数化，可缓存"""
    mask = (base_df['日期'] >= start_date) & (base_df['日期'] <= end_date)
    if factions: mask &= base_df['派系'].isin(factions)
    if products: mask &= base_df['产品'].isin(products)
    if platforms: mask &= base_df['广告主平台名称'].isin(platforms)
    if configs: mask &= base_df['广告主平台配置名称'].isin(configs)
    if media: mask &= base_df['媒体平台名称'].isin(media)
    if ids: mask &= base_df['调度中心ID'].isin(ids)
    if owners: mask &= base_df['负责人'].isin(owners)
    return base_df[mask]


@st.cache_data(show_spinner=False, ttl=300)
def merge_price_and_calc_settle(df_raw, df_price_config):
    """单价合并 + 结算金额计算 — 独立缓存，单价配置不变时秒返回"""
    work_df = df_raw.copy()
    if "单价" not in work_df.columns:
        work_df["单价"] = 0.0
    if "回传维度" not in work_df.columns:
        work_df["回传维度"] = "未配置"

    pc = df_price_config.copy()
    pc["广告主配置"] = pc["广告主配置"].astype(str).str.strip()
    price_map = dict(pc[["广告主配置", "单价"]].values)
    dimension_map = dict(pc[["广告主配置", "回传维度"]].values)

    cleaned = work_df["广告主平台配置名称"].astype(str).str.strip()
    work_df["单价"] = cleaned.map(price_map).fillna(work_df["单价"])
    work_df["回传维度"] = cleaned.map(dimension_map).fillna(work_df["回传维度"])
    work_df["单价"] = pd.to_numeric(work_df["单价"], errors='coerce').fillna(0)
    work_df["回传维度"] = work_df["回传维度"].astype(str).fillna("未配置")

    work_df["结算金额"] = 0.0
    for dim_name, target_col in TARGET_MAP.items():
        if target_col not in work_df.columns:
            continue
        match_mask = work_df["回传维度"] == dim_name
        work_df.loc[match_mask, "结算金额"] = (work_df.loc[match_mask, target_col]
                                               * work_df.loc[match_mask, "单价"])
    work_df["结算金额"] = pd.to_numeric(work_df["结算金额"], errors='coerce').fillna(0)
    return work_df


@st.cache_data(show_spinner=False, ttl=300)
def process_view(
    dims: tuple,
    src_df: pd.DataFrame,
    show_daily: bool,
    show_cvr: bool,
    c_num: str,
    c_den: str,
    cvr_name: str,
    enable_wow: bool,
    wow_targets: tuple,
    s_metrics: tuple,
):
    """数据聚合核心函数 — 所有配置显式参数化，完整可缓存"""
    if src_df.empty:
        return pd.DataFrame(), []

    all_num_cols_src = src_df.select_dtypes(include=['number']).columns.tolist()
    base_needed = set(all_num_cols_src + ["次日回访量", "3日留存次数", "7日留存次数", "前日激活"])
    for r_name in PRESET_RATES:
        base_needed.update(PRESET_RATES[r_name])
    if show_cvr:
        base_needed.update([c_num, c_den])

    agg_map = {}
    for c in base_needed:
        if c in src_df.columns:
            if c == "单价":
                agg_map[c] = lambda x: x.iloc[0] if len(x) > 0 else 0
            else:
                agg_map[c] = 'sum'
    if "负责人" in src_df.columns and "负责人" not in agg_map:
        agg_map["负责人"] = lambda x: x.iloc[0] if len(x) > 0 else ""

    summary = src_df.groupby(list(dims)).agg(agg_map).reset_index()
    metric_cols = [col for col in base_needed if col in summary.columns]
    for col in metric_cols:
        summary[col] = pd.to_numeric(summary[col], errors='coerce').fillna(0)

    sort_target = [c for c in ["广告主激活量", "新登量"] if c in summary.columns]
    if sort_target:
        summary = summary.sort_values(by=sort_target, ascending=False)
    summary["日期"] = "✨ 汇总"

    if show_daily:
        daily = src_df.groupby(list(dims) + ["日期"]).agg(agg_map).reset_index()
        for col in metric_cols:
            if col in daily.columns:
                daily[col] = pd.to_numeric(daily[col], errors='coerce').fillna(0)

        daily["_tmp_next_stay"] = daily.groupby(list(dims))["次日回访量"].shift(-1).fillna(0)
        daily["_tmp_3d_stay"] = daily.groupby(list(dims))["3日留存次数"].shift(-3).fillna(0)
        daily["_tmp_7d_stay"] = daily.groupby(list(dims))["7日留存次数"].shift(-7).fillna(0)

        if enable_wow and wow_targets:
            for col in wow_targets:
                daily[f"prev_{col}"] = daily.groupby(list(dims))[col].shift(1)

        summary_ordered = summary.copy()
        summary_ordered['_order'] = range(len(summary_ordered))
        daily_ordered = daily.merge(summary_ordered[list(dims) + ['_order']], on=list(dims), how='inner')

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
        if "负责人" in total_row.columns:
            total_row["负责人"] = ""
        final = pd.concat([total_row, final], ignore_index=True)

    for name, (n, d) in PRESET_RATES.items():
        if n in final.columns and d in final.columns:
            raw_num = pd.to_numeric(final[n], errors='coerce').fillna(0)
            raw_den = pd.to_numeric(final[d], errors='coerce').fillna(0)
            calc_num = raw_num.copy()

            mask_daily = final["日期"] != "✨ 汇总" if "日期" in final.columns else pd.Series(False, index=final.index)
            if name == "次留率" and "_tmp_next_stay" in final.columns:
                calc_num.loc[mask_daily] = pd.to_numeric(final.loc[mask_daily, "_tmp_next_stay"],
                                                         errors='coerce').fillna(0)
            elif name == "三留率" and "_tmp_3d_stay" in final.columns:
                calc_num.loc[mask_daily] = pd.to_numeric(final.loc[mask_daily, "_tmp_3d_stay"],
                                                         errors='coerce').fillna(0)
            elif name == "七留率" and "_tmp_7d_stay" in final.columns:
                calc_num.loc[mask_daily] = pd.to_numeric(final.loc[mask_daily, "_tmp_7d_stay"],
                                                         errors='coerce').fillna(0)

            safe_ratio = np.divide(
                calc_num.values, raw_den.values,
                out=np.zeros_like(calc_num.values, dtype=np.float64),
                where=raw_den.values > 1e-9
            )
            final[name] = safe_ratio * 100

    if show_cvr and c_num in final.columns and c_den in final.columns:
        cn = pd.to_numeric(final[c_num], errors='coerce').fillna(0).astype(np.float64)
        cd = pd.to_numeric(final[c_den], errors='coerce').fillna(0).astype(np.float64)
        cvr_res = np.divide(cn, cd, out=np.zeros_like(cn, dtype=np.float64), where=cd > 0)
        final[cvr_name] = cvr_res * 100

    wow_col_names = []
    if enable_wow and wow_targets:
        for col in wow_targets:
            p_col = f"prev_{col}"
            if p_col in final.columns:
                w_col = f"{col}环比"
                curr = pd.to_numeric(final[col], errors='coerce').astype(np.float64)
                prev = pd.to_numeric(final[p_col], errors='coerce').astype(np.float64)
                diff = curr - prev
                wow_res = np.divide(diff, prev.abs(), out=np.zeros_like(diff, dtype=np.float64), where=prev.abs() > 1e-9)
                final[w_col] = np.where(final["日期"] != "✨ 汇总", wow_res * 100, 0.0)
                final[w_col] = final[w_col].replace([np.inf, -np.inf], 0).fillna(0)
                wow_col_names.append(w_col)

    int_skip = {"单价", "结算金额"}
    for c in s_metrics:
        if c in final.columns:
            if c in int_skip:
                final[c] = pd.to_numeric(final[c], errors='coerce').fillna(0).round(4)
            else:
                final[c] = pd.to_numeric(final[c], errors='coerce').fillna(0).astype(int)
    return final, wow_col_names


# ====================== 表格渲染 ======================

def _build_disp_df(res_df, base_dims, wow_cols, table_rates, s_metrics, insert_owner):
    """纯函数：根据配置生成展示列 DataFrame"""
    base_cols = [d for d in base_dims if d in res_df.columns]
    target_metrics = [c for c in s_metrics if c in res_df.columns and c not in ("单价", "结算金额")]
    special_cols = [c for c in ("单价", "结算金额") if c in res_df.columns]

    disp_cols = base_cols.copy()
    if insert_owner and "调度中心ID" in disp_cols and "负责人" in res_df.columns:
        insert_pos = disp_cols.index("调度中心ID") + 1
        disp_cols.insert(insert_pos, "负责人")

    disp_cols = disp_cols + special_cols + target_metrics + [r for r in table_rates if r in res_df.columns]
    return res_df[disp_cols].copy(), disp_cols


@st.cache_data(show_spinner=False, ttl=300)
def _compute_styles(
    disp_cols: tuple,
    n_rows: int,
    total_summary_mask: tuple,
    group_summary_mask: tuple,
    wow_up_mask: tuple,
    wow_down_mask: tuple,
    wow_col_names: tuple,
    enable_alert: bool,
    alert_rules: tuple,
    alert_masks: tuple,
):
    """稀疏存储：只返回有样式的 (row_idx, col_name, css_string) 列表，不缓存空字符串矩阵"""
    styles = {}
    empty_series = pd.Series([], dtype=object)

    def add(row_idx, col_name, css):
        key = (row_idx, col_name)
        if key in styles:
            existing = styles[key]
            if css not in existing:
                styles[key] = existing + " " + css
        else:
            styles[key] = css

    total_mask = pd.Series(total_summary_mask)
    group_mask = pd.Series(group_summary_mask)
    for col in disp_cols:
        rows_t = total_mask[total_mask].index.tolist()
        rows_g = group_mask[group_mask].index.tolist()
        for r in rows_t:
            add(r, col, "background-color: #FFF2CC; font-weight: bold; color: #D68910;")
        for r in rows_g:
            add(r, col, "background-color: #E6F3FF; font-weight: bold; color: #1f77b4;")

    if enable_alert and alert_rules:
        for rule, mask_tuple in zip(alert_rules, alert_masks):
            target = rule['target']
            if target not in disp_cols:
                continue
            alert_mask = pd.Series(mask_tuple)
            for r in alert_mask[alert_mask].index.tolist():
                add(r, target, "color: white; font-weight: bold; background-color: #FF4B4B;")

    wow_up = pd.Series(wow_up_mask)
    wow_down = pd.Series(wow_down_mask)
    for idx, w_col in enumerate(wow_col_names):
        if w_col not in disp_cols:
            continue
        up_rows = wow_up[wow_up].index.tolist()
        down_rows = wow_down[wow_down].index.tolist()
        for r in up_rows:
            add(r, w_col, "color: #d00000; font-weight: bold;")
        for r in down_rows:
            add(r, w_col, "color: #008000; font-weight: bold;")

    return styles


def render_dataframe(res_df, base_dims, wow_cols, table_key="default", insert_owner=False,
                     selected_rate_names=None, show_cvr=False, cvr_name=None,
                     s_metrics=None, enable_alert=False, alert_rules=None):
    """统一表格渲染 — 样式计算稀疏化，避免缓存爆炸"""
    if res_df.empty:
        return st.info("所选筛选条件下无数据")

    selected_rate_names = selected_rate_names or []
    s_metrics = s_metrics or []
    alert_rules = alert_rules or []

    table_rates = selected_rate_names + ([cvr_name] if show_cvr else []) + list(wow_cols)
    disp_df, disp_cols = _build_disp_df(res_df, base_dims, list(wow_cols), table_rates, list(s_metrics), insert_owner)

    disp_df = disp_df.reset_index(drop=True)

    mask_total_summary = pd.Series(False, index=disp_df.index)
    if "广告主平台配置名称" in disp_df.columns:
        mask_total_summary |= disp_df["广告主平台配置名称"].str.contains("【全配置号汇总】", na=False)
    if "派系" in disp_df.columns:
        mask_total_summary |= disp_df["派系"].str.contains("【全大盘派系汇总】", na=False)
    mask_group_summary = pd.Series(False, index=disp_df.index)
    if "日期" in disp_df.columns:
        mask_group_summary = (disp_df["日期"] == "✨ 汇总") & (~mask_total_summary)

    wow_up_mask = pd.Series(False, index=disp_df.index)
    wow_down_mask = pd.Series(False, index=disp_df.index)
    for w_col in wow_cols:
        if w_col not in disp_cols:
            continue
        series = disp_df[w_col].astype(float)
        wow_up_mask |= series > 0
        wow_down_mask |= series < 0
    wow_down_mask &= ~wow_up_mask

    alert_masks = []
    for rule in alert_rules:
        target, logi, threshold = rule['target'], rule['logic'], rule['val']
        if target not in disp_cols:
            alert_masks.append(tuple())
            continue
        series = disp_df[target].astype(float)
        cond = False
        if logi == "<": cond = series < threshold
        elif logi == "<=": cond = series <= threshold
        elif logi == ">": cond = series > threshold
        elif logi == ">=": cond = series >= threshold
        elif logi == "==": cond = np.isclose(series, threshold, atol=1e-6)
        alert_masks.append(tuple(cond))

    styles_map = _compute_styles(
        tuple(disp_cols),
        len(disp_df),
        tuple(mask_total_summary),
        tuple(mask_group_summary),
        tuple(wow_up_mask),
        tuple(wow_down_mask),
        tuple(wow_cols),
        enable_alert,
        tuple(alert_rules),
        tuple(alert_masks),
    )

    empty_row = tuple([""] * len(disp_cols))

    def row_styler(_row):
        styles = list(empty_row)
        for (r_idx, c_name), css in styles_map.items():
            if r_idx == _row.name and c_name in disp_cols:
                c_pos = disp_cols.index(c_name)
                existing = styles[c_pos]
                styles[c_pos] = (existing + " " + css) if existing else css
        return tuple(styles)

    styler = disp_df.style.apply(row_styler, axis=1)

    c_config = {}
    if "日期" in disp_cols:
        c_config["日期"] = st.column_config.TextColumn(width="small")
    if "负责人" in disp_cols:
        c_config["负责人"] = st.column_config.TextColumn(width="small")
    for r_col in [r for r in table_rates if r in disp_df.columns]:
        c_config[r_col] = st.column_config.NumberColumn(format="%.2f%%", width="small")
    for m_col in [c for c in s_metrics if c in disp_df.columns]:
        c_config[m_col] = st.column_config.NumberColumn(format="%d")

    dynamic_height = min(35 * len(disp_df) + 40, 700)
    st.dataframe(
        styler,
        use_container_width=True,
        hide_index=True,
        column_config=c_config,
        height=dynamic_height
    )

    csv_data = disp_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label=f"📥 导出{table_key}",
        data=csv_data,
        file_name=f"OCPX_{table_key}.csv",
        mime="text/csv",
        key=f"dl_{table_key}"
    )
    st.divider()


# ====================== 页面初始化 ======================
st.set_page_config(page_title="OCPX业务数据全维度分析看板", layout="wide", initial_sidebar_state="expanded")
st.markdown("<h2 style='text-align: center; color: #1F77B4;'>🥑 OCPX 业务数据分析看板</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>欢迎提出使用建议~🍦</p>", unsafe_allow_html=True)
st.divider()

cookie_manager = stx.CookieManager()
if cookie_manager.get_all() is None:
    st.stop()

user_uuid = cookie_manager.get("persistent_user_uuid")
if not user_uuid:
    user_uuid = str(uuid.uuid4())
    cookie_manager.set("persistent_user_uuid", user_uuid, max_age=365 * 24 * 60 * 60)

USER_CACHE_DIR = os.path.join(BASE_CACHE_DIR, user_uuid)
os.makedirs(BASE_CACHE_DIR, exist_ok=True)
os.makedirs(USER_CACHE_DIR, exist_ok=True)

CACHE_FILE = os.path.join(USER_CACHE_DIR, "last_processed_data.feather")
META_FILE = os.path.join(USER_CACHE_DIR, "cache_metadata.json")


def load_from_local_cache():
    if os.path.exists(CACHE_FILE) and os.path.exists(META_FILE):
        try:
            with open(META_FILE, "r", encoding="utf-8") as f:
                meta = json.load(f)
            df = pd.read_feather(CACHE_FILE)
            return df, meta.get("file_name")
        except Exception:
            return None, None
    return None, None


def save_to_local_cache(df, file_name):
    try:
        df.to_feather(CACHE_FILE, compression="zstd")
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump({"file_name": file_name}, f)
    except Exception as e:
        st.warning(f"本地硬盘缓存写入失败: {e}")


if "cleaned_data" not in st.session_state:
    cached_df, cached_name = load_from_local_cache()
    if cached_df is not None:
        temp_df = cached_df
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
        st.cache_data.clear()
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
        st.caption(f"💾 当前使用数据源: `{st.session_state['file_name']}` (已启用长效 Cookie 隔离与断线自动恢复缓存)")

        with st.sidebar:
            st.markdown("<h3 style='color: #1F77B4;'>💰 飞书配置</h3>", unsafe_allow_html=True)
            df_price_config = load_feishu_price_config()
            st.caption(f"飞书单价配置已加载 {len(df_price_config)} 条（5分钟自动刷新）")
            if not df_price_config.empty:
                with st.expander("🔍 飞书配置预览（前5条）"):
                    st.dataframe(df_price_config.head(), use_container_width=True, hide_index=True)
            if st.button("🔄 立即刷新飞书配置", key="refresh_feishu"):
                load_feishu_price_config.clear()
                st.success("已清除缓存，重新拉取中...")
                st.rerun()

            st.divider()

        df_raw = st.session_state["cleaned_data"]
        df = merge_price_and_calc_settle(df_raw, df_price_config)
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()

        if not df_price_config.empty and "单价" in df.columns:
            matched_count = int((df["单价"] > 0).sum())
            total_count = len(df)
            match_rate = matched_count / total_count * 100 if total_count > 0 else 0
            st.caption(f"🔗 单价匹配: {matched_count}/{total_count} 行有单价 ({match_rate:.1f}%)")

        # ====================== 侧边栏控件 ======================
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

            sub_df_for_platform = sub_df_for_product[sub_df_for_product["产品"].isin(t_products)] if t_products else sub_df_for_product
            t_platforms = st.multiselect("3. 广告主平台名称筛选", options=sorted(sub_df_for_platform["广告主平台名称"].unique().tolist()))

            sub_df_for_config = sub_df_for_platform[sub_df_for_platform["广告主平台名称"].isin(t_platforms)] if t_platforms else sub_df_for_platform
            t_configs = st.multiselect("4. 配置号筛选", options=sorted(sub_df_for_config["广告主平台配置名称"].unique().tolist()))

            sub_df_for_media = sub_df_for_config[sub_df_for_config["广告主平台配置名称"].isin(t_configs)] if t_configs else sub_df_for_config
            t_media = st.multiselect("5. 媒体筛选", options=sorted(sub_df_for_media["媒体平台名称"].unique().tolist()))

            sub_df_for_id = sub_df_for_media[sub_df_for_media["媒体平台名称"].isin(t_media)] if t_media else sub_df_for_media
            t_ids = st.multiselect("6. 调度中心ID筛选", options=sorted(sub_df_for_id["调度中心ID"].unique().tolist()))

            sub_df_for_owner = sub_df_for_id[sub_df_for_id["调度中心ID"].isin(t_ids)] if t_ids else sub_df_for_id
            t_owners = st.multiselect("7. 负责人筛选", options=sorted(sub_df_for_owner["负责人"].unique().tolist()))

            st.divider()
            st.markdown("<h3 style='color: #1F77B4;'>📈 率指标池</h3>", unsafe_allow_html=True)
            selected_rate_names = []
            col1, col2 = st.columns(2)
            for i, name in enumerate(PRESET_RATES.keys()):
                with col1 if i % 2 == 0 else col2:
                    if st.checkbox(name, value=name in ["下单率", "次留率"]):
                        selected_rate_names.append(name)

            show_cvr = st.checkbox("⚙️ 开启 自定义CVR", value=True)
            cvr_name = None
            c_num, c_den = "", ""
            if show_cvr:
                default_num_idx = numeric_cols.index("广告主激活量") if "广告主激活量" in numeric_cols else 0
                default_den_idx = numeric_cols.index("上报广告主次数") if "上报广告主次数" in numeric_cols else 0
                c_num = st.selectbox("CVR 分子", numeric_cols, index=default_num_idx)
                c_den = st.selectbox("CVR 分母", numeric_cols, index=default_den_idx)
                cvr_name = f"CVR({c_num}/{c_den})"

            enable_wow = st.toggle("开启指标环比 (对比前一日)", value=False)
            wow_targets_list = st.multiselect("选择看环比的数值列", numeric_cols,
                                              default=[f for f in ["广告主激活量"] if f in numeric_cols]) if enable_wow else []

            enable_alert = st.toggle("开启爆红预警高亮", value=False)
            alert_rules = []
            if enable_alert:
                alert_targets_pool = selected_rate_names + ([cvr_name] if cvr_name else [])
                chosen_targets = st.multiselect("选择需要预警的指标", alert_targets_pool)
                for target in chosen_targets:
                    st.markdown(f"**{target} 预警配置**")
                    c_logic, c_val = st.columns([1, 2])
                    with c_logic:
                        logic = st.selectbox("逻辑", ["<", "<=", ">", ">=", "=="], key=f"lg_{target}")
                    with c_val:
                        val = st.number_input("阈值(%)", value=5.0, step=0.1, key=f"val_{target}")
                    alert_rules.append({"target": target, "logic": logic, "val": val})

            s_metrics = st.multiselect("表内显示指标", options=numeric_cols,
                                       default=[f for f in ["广告主激活量", "新登量", "下单量", "单价", "结算金额"] if f in numeric_cols])
            show_daily = st.checkbox("开启下钻分日", value=True)

        if not isinstance(selected_date_range, (list, tuple)) or len(selected_date_range) < 2:
            st.info("⏳ 请在左侧边栏选择完整的【开始日期】和【结束日期】...")
            st.stop()

        f_df_global = get_filtered_dataframe(
            df,
            selected_date_range[0],
            selected_date_range[1],
            tuple(t_factions), tuple(t_products), tuple(t_platforms),
            tuple(t_configs), tuple(t_media), tuple(t_ids), tuple(t_owners)
        )

        res1, w1 = process_view(
            ("派系", "产品", "广告主平台名称", "广告主平台配置名称"),
            f_df_global,
            show_daily, show_cvr, c_num, c_den, cvr_name,
            enable_wow, tuple(wow_targets_list), tuple(s_metrics)
        )

        # KPI顶部卡片
        if not f_df_global.empty:
            active_kpi_pool = (
                [{"name": "结算金额", "type": "number"}] if "结算金额" in f_df_global.columns else []
            ) + (
                [{"name": m, "type": "number"} for m in s_metrics if m in f_df_global.columns and m not in ("单价", "结算金额")] +
                [{"name": r, "type": "rate"} for r in selected_rate_names if r in PRESET_RATES]
            )
            if show_cvr and cvr_name:
                active_kpi_pool.append({"name": cvr_name, "type": "rate"})
            if not active_kpi_pool:
                active_kpi_pool = [{"name": c, "type": "number"}
                                   for c in ["广告主激活量", "下单量", "新登量"] if c in f_df_global.columns]

            kpi_cols = st.columns(min(len(active_kpi_pool), 4))
            for idx, kpi in enumerate(active_kpi_pool[:4]):
                name, kpi_type = kpi["name"], kpi["type"]
                with kpi_cols[idx]:
                    if kpi_type == "number":
                        label = "总结算金额" if name == "结算金额" else f"周期总 {name}"
                        if name in ("单价",):
                            val = f"{f_df_global[name].mean():.4f}" if f_df_global[name].sum() > 0 else "0"
                        elif name == "结算金额":
                            val = f"{pd.to_numeric(f_df_global[name], errors='coerce').sum():,.2f}"
                        else:
                            val = f"{int(f_df_global[name].sum()):,}"
                        st.metric(label=f"📊 {label}", value=val)
                    else:
                        if name in PRESET_RATES:
                            n_col, d_col = PRESET_RATES[name]
                            if n_col in f_df_global.columns and d_col in f_df_global.columns:
                                raw_n = pd.to_numeric(f_df_global[n_col], errors='coerce').sum()
                                raw_d = pd.to_numeric(f_df_global[d_col], errors='coerce').sum()
                                rate_val = (raw_n / raw_d * 100) if raw_d > 1e-9 else 0.0
                            else:
                                rate_val = 0.0
                        elif show_cvr and name == cvr_name and c_num in f_df_global.columns and c_den in f_df_global.columns:
                            raw_n = pd.to_numeric(f_df_global[c_num], errors='coerce').sum()
                            raw_d = pd.to_numeric(f_df_global[c_den], errors='coerce').sum()
                            rate_val = (raw_n / raw_d * 100) if raw_d > 1e-9 else 0.0
                        else:
                            rate_val = res1[name].iloc[0] if not res1.empty and name in res1.columns else 0.0
                        st.metric(label=f"📈 大盘综合 {name}", value=f"{rate_val:.2f}%")
            st.write("")

        # ===================== Tab视图 =====================
        tab1, tab2, tab3 = st.tabs(["1️⃣ 配置号明细", "2️⃣ 媒体平台明细", "3️⃣ 调度ID明细"])

        render_kwargs = dict(
            selected_rate_names=selected_rate_names,
            show_cvr=show_cvr, cvr_name=cvr_name,
            s_metrics=s_metrics,
            enable_alert=enable_alert, alert_rules=alert_rules,
        )

        MAX_ROWS = 700

        with tab1:
            st.subheader("配置号分析视角")
            render_dataframe(
                res1.head(MAX_ROWS) if not res1.empty else res1,
                ["派系", "产品", "广告主平台名称", "广告主平台配置名称"] + (["日期"] if show_daily else []),
                w1,
                table_key="配置号明细",
                insert_owner=False,
                **render_kwargs,
            )

        with tab2:
            st.subheader("媒体平台分析视角")
            res2, w2 = process_view(
                ("产品", "广告主平台配置名称", "媒体平台名称"),
                f_df_global,
                show_daily, show_cvr, c_num, c_den, cvr_name,
                enable_wow, tuple(wow_targets_list), tuple(s_metrics)
            )
            render_dataframe(
                res2.head(MAX_ROWS) if not res2.empty else res2,
                ["产品", "广告主平台配置名称", "媒体平台名称"] + (["日期"] if show_daily else []),
                w2,
                table_key="媒体平台明细",
                insert_owner=False,
                **render_kwargs,
            )

        with tab3:
            st.subheader("调度ID分析视角")
            res3, w3 = process_view(
                ("产品", "广告主平台配置名称", "媒体平台名称", "调度中心ID"),
                f_df_global,
                show_daily, show_cvr, c_num, c_den, cvr_name,
                enable_wow, tuple(wow_targets_list), tuple(s_metrics)
            )
            render_dataframe(
                res3.head(MAX_ROWS) if not res3.empty else res3,
                ["产品", "广告主平台配置名称", "媒体平台名称", "调度中心ID"] + (["日期"] if show_daily else []),
                w3,
                table_key="调度ID明细",
                insert_owner=True,
                **render_kwargs,
            )

    except Exception as e:
        st.error(f"处理出现技术错误: {e}")
else:
    st.info("👋 欢迎使用！请在上方上传 OCPX 业务数据报表!\nps：可上传完整底表，无需筛选字段～")
