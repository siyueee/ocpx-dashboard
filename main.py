import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import re  # 💡 正则模块用于清洗数字尾缀
import altair as alt  # ✨ 用于绘制高交互性大盘图表
import uuid  # ✨ 新增：用于生成用户专属的隔离会话标识
import extra_streamlit_components as stx  # ✨ 新增：用于实现浏览器 Cookie 长期持久化凭证


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
    # 从长到短排序，防止名字截断 Bug
    sorted_match_list = sorted(all_products_flat, key=lambda x: len(x["product"]), reverse=True)
    return sorted_match_list, config.get("default_faction", "其他派系"), config.get("default_product", "其他产品")


MATCH_RULE_LIST, DEFAULT_FACTION, DEFAULT_PRODUCT = load_product_config()

# 特例拦截映射表
SPECIAL_MAPPING = {
    # 1. 字节系
    "抖音商城": {"派系": "字节系", "特征": ["乘风", "独立端", "dy_"]},
    "番茄免费小说": {"派系": "字节系", "特征": ["番茄小说"]},
    "悟空浏览器": {"派系": "字节系", "特征": ["悟空"]},
    "抖音": {"派系": "字节系", "特征": ["抖音拉新", "抖音卸载召回"]},

    # 2. 阿里系
    "淘宝闪购": {"派系": "阿里系", "特征": ["淘宝闪购", "tbsg", "饿了么", "高比单", "高笔单", "闪购夜宵"]},
    "淘宝": {"派系": "阿里系", "特征": ["大航海", "淘宝"]},
    "淘宝联盟": {"派系": "阿里系", "特征": ["淘联"]},
    "uc浏览器": {"派系": "阿里系", "特征": ["ucpl", "UC普拉", "UC拉新", "uc浏览器"]},
    "夸克": {"派系": "阿里系", "特征": ["kk@", "夸克"]},
    "千问": {"派系": "阿里系", "特征": ["tongyi", "通义", "typl", "tydx"]},
    "闲鱼": {"派系": "阿里系", "特征": ["闲鱼付费", "闲鱼U1"]},

    # 3. 快手系
    "快手极速版": {"派系": "快手系", "特征": ["快接包-极速版", "快接包极速版", "极速版-ANDROID", "快接包-极速板"]},
    "快手": {"派系": "快手系", "特征": ["快接包-主板", "快接包主站", "主板拉回"]},
    "喜番免费短剧": {"派系": "快手系", "特征": ["喜番"]},

    # 4. 腾讯系
    "腾讯元宝": {"派系": "腾讯系", "特征": ["元宝"]},

    # 5. 其他派系
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


# 将数据载入与文本挖掘用 Streamlit 原生 Cache 锁死
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

    # ----------------------------------------------------
    # 🔥 过滤网：过滤掉媒体上报次数和曝光数<20且其他业务数值列皆为0的极小行
    # ----------------------------------------------------
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
    # ----------------------------------------------------

    if '广告主激活量' in raw_df.columns:
        sort_cols = [c for c in ["广告主平台配置名称", "媒体平台名称", "调度中心ID", "日期"] if c in raw_df.columns]
        raw_df = raw_df.sort_values(by=sort_cols)
        group_cols = [c for c in sort_cols if c != '日期']
        raw_df['前日激活'] = raw_df.groupby(group_cols)['广告主激活量'].shift(1).fillna(0)
    else:
        raw_df['前日激活'] = 0
    return raw_df


# ==========================================
# ⚡ 高性能内存级联过滤引擎（向量化加速，完美支撑百万行）
# ==========================================
@st.cache_data(show_spinner=False)
def get_filtered_dataframe(base_df, start_date, end_date, factions, products, platforms, configs, media, ids):
    """
    将所有筛选条件作为不可变类型（Tuple）传入，触发底层内存缓存
    """
    mask = (base_df['日期'] >= start_date) & (base_df['日期'] <= end_date)

    if factions:
        mask &= base_df['派系'].isin(factions)
    if products:
        mask &= base_df['产品'].isin(products)
    if platforms:
        mask &= base_df['广告主平台名称'].isin(platforms)
    if configs:
        mask &= base_df['广告主平台配置名称'].isin(configs)
    if media:
        mask &= base_df['媒体平台名称'].isin(media)
    if ids:
        mask &= base_df['调度中心ID'].isin(ids)

    return base_df[mask]


# ==========================================
# 💾 本地硬盘级持久化与长效 Cookie 隔离逻辑
# ==========================================
BASE_CACHE_DIR = ".streamlit_file_cache"
if not os.path.exists(BASE_CACHE_DIR):
    os.makedirs(BASE_CACHE_DIR)

# 初始化 Cookie 管理器以实现长时间离开后凭证不丢失
cookie_manager = stx.CookieManager()
if cookie_manager.get_all() is None:
    st.stop()

# 尝试从浏览器 Cookie 中获取长效用户唯一凭证
user_uuid = cookie_manager.get("persistent_user_uuid")
if not user_uuid:
    user_uuid = str(uuid.uuid4())
    # 设置长效 Cookie（有效期 1 年）
    cookie_manager.set("persistent_user_uuid", user_uuid, max_age=365 * 24 * 60 * 60)

# 绑定专属的用户隔离硬盘目录
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
        st.session_state["cleaned_data"] = cached_df
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
        df = st.session_state["cleaned_data"]
        st.caption(f"💾 当前使用数据源: `{st.session_state['file_name']}` (已启用长效 Cookie 隔离与断线自动恢复缓存)")

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
                                       default=[f for f in ["广告主激活量", "新登量", "下单量"] if f in numeric_cols])
            show_daily = st.checkbox("开启下钻分日", value=True)

        if not isinstance(selected_date_range, (list, tuple)) or len(selected_date_range) < 2:
            st.info("⏳ 请在左侧边栏选择完整的【开始日期】和【结束日期】...")
            st.stop()

        # 调用高效缓存的向量化过滤引擎
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

            base_needed = set(list(s_metrics) + ["次日回访量", "3日留存次数", "7日留存次数", "前日激活"])
            for r_name in PRESET_RATES: base_needed.update(PRESET_RATES[r_name])
            if show_cvr: base_needed.update([c_num, c_den])

            agg_map = {c: 'sum' for c in base_needed if c in src_df.columns}
            for c in agg_map: src_df[c] = pd.to_numeric(src_df[c], errors='coerce').fillna(0)

            summary = src_df.groupby(dims).agg(agg_map).reset_index()
            sort_target = [c for c in ["广告主激活量", "新登量"] if c in summary.columns]
            if sort_target: summary = summary.sort_values(by=sort_target, ascending=False)
            summary["日期"] = "✨ 汇总"

            if show_daily:
                daily = src_df.groupby(dims + ["日期"]).agg(agg_map).reset_index()
                # 错位对齐各阶留存分子（按时间倒序或正序，利用 shift 将未来的回访数据平移对齐到激活日）
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

            if "广告主平台配置名称" in dims:
                total_row = src_df.agg(agg_map).to_frame().T
                if "派系" in dims: total_row["派系"] = "【全大盘派系汇总】"
                if "产品" in dims: total_row["产品"] = "【全大盘产品汇总】"
                if "广告主平台名称" in dims: total_row["广告主平台名称"] = "【全平台名称汇总】"
                total_row["广告主平台配置名称"], total_row["日期"] = "【全配置号汇总】", "✨ 汇总"
                final = pd.concat([total_row, final], ignore_index=True)

            for name, (n, d) in PRESET_RATES.items():
                if n in final.columns and d in final.columns:
                    num = pd.to_numeric(final[n], errors='coerce').fillna(0)
                    den = pd.to_numeric(final[d], errors='coerce').fillna(0)

                    # 动态替换错位留存的分子
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
                if c in final.columns: final[c] = final[c].fillna(0).astype(int)
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


        # --- 独立且安全的渲染与导出引擎函数 ---
        def style_and_display(res_df, base_dims, wow_cols, table_key="default"):
            if res_df.empty: return st.info("所选筛选条件下无数据")
            table_rates = selected_rate_names + ([cvr_name] if show_cvr else []) + wow_cols
            disp_cols = [d for d in base_dims if d in res_df.columns] + [c for c in s_metrics if
                                                                         c in res_df.columns] + [r for r in table_rates
                                                                                                 if r in res_df.columns]

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
            for col in [c for c in s_metrics if c in res_df.columns]: c_config[col] = st.column_config.NumberColumn(
                format="%d")

            dynamic_height = min(35 * len(res_df) + 40, 700)

            st.dataframe(
                res_df[disp_cols].style.apply(apply_style, axis=1),
                use_container_width=True,
                hide_index=True,
                column_config=c_config,
                height=dynamic_height
            )

            # CSV 一键导出
            csv_data = res_df[disp_cols].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label=f"📥 导出此分析数据",
                data=csv_data,
                file_name=f"OCPX_导出_{table_key}.csv",
                mime="text/csv",
                key=f"download_{table_key}"
            )
            st.divider()


        # ==================== 🚀 页面层级多维下钻对齐渲染 (Tabs 排版优化) ====================
        tab1, tab2, tab3 = st.tabs(["1️⃣ 配置号明细", "2️⃣ 媒体平台明细", "3️⃣ 调度ID明细"])

        with tab1:
            st.subheader("配置号分析")
            style_and_display(
                res1.head(700) if not res1.empty else res1,
                ["派系", "产品", "广告主平台名称", "广告主平台配置名称"] + (["日期"] if show_daily else []),
                w1,
                table_key="配置号明细"
            )

        with tab2:
            st.subheader("媒体平台分析")
            if "媒体平台名称" in f_df_global.columns and not f_df_global.empty:
                media_list_sorted = f_df_global.groupby("媒体平台名称")["广告主激活量"].sum().reset_index().sort_values(
                    by="广告主激活量", ascending=False)["媒体平台名称"].tolist()
                st.markdown(
                    f"💡 当前筛选组合内共覆盖 **{len(media_list_sorted)}** 个媒体：`{' / '.join(media_list_sorted) if media_list_sorted else '无'}`")
            else:
                st.markdown("💡 共有媒体：0 个")

            res2, w2 = process_view(["产品", "广告主平台配置名称", "媒体平台名称"], f_df_global)
            style_and_display(
                res2,
                ["产品", "广告主平台配置名称", "媒体平台名称"] + (["日期"] if show_daily else []),
                w2,
                table_key="媒体平台明细"
            )

        with tab3:
            st.subheader("调度ID分析")
            if "媒体平台名称" in f_df_global.columns and "调度中心ID" in f_df_global.columns and not f_df_global.empty:
                media_id_count = f_df_global.groupby("媒体平台名称")["调度中心ID"].nunique().reset_index()
                media_id_count["激活量"] = media_id_count["媒体平台名称"].map(
                    f_df_global.groupby("媒体平台名称")["广告主激活量"].sum())
                id_detail = " ｜ ".join([f"**{row['媒体平台名称']}** ({row['调度中心ID']}个)" for _, row in
                                        media_id_count.sort_values("激活量", ascending=False).iterrows()])
            else:
                id_detail = "无数据"
            st.markdown(f"🆔 各渠道下调度id分布：{id_detail}")

            res3, w3 = process_view(["广告主平台配置名称", "媒体平台名称", "调度中心ID"], f_df_global)
            style_and_display(
                res3,
                ["广告主平台配置名称", "媒体平台名称", "调度中心ID"] + (["日期"] if show_daily else []),
                w3,
                table_key="调度ID明细"
            )

    except Exception as e:
        st.error(f"处理出现技术错误: {e}")
else:
    st.info("👋 欢迎使用！请在上方上传 OCPX 业务数据报表!\nps：可上传完整底表，无需筛选字段～")
