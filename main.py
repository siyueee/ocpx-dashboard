import streamlit as st
import pandas as pd
import numpy as np

# 1. 基础网页配置（设定主题色与标题）
st.set_page_config(page_title="OCPX业务数据全维度分析看板", layout="wide", initial_sidebar_state="expanded")

# 顶部业务主标题（带装饰线）
st.markdown("<h2 style='text-align: center; color: #1F77B4;'>🥑 OCPX 业务数据分析看板</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>欢迎提出使用建议~🍦</p>", unsafe_allow_html=True)
st.divider()

# --- 预设指标池 ---
PRESET_RATES = {
    "下单率": ("下单量", "广告主激活量"),
    "次留率": ("次日回访量", "广告主激活量"),
    "激活率": ("广告主激活量", "上报广告主次数"),
    "唤醒率": ("唤醒量", "上报广告主次数"),
    "首唤率": ("首唤量", "上报广告主次数"),
    "新登率": ("新登量", "广告主激活量"),
    "首购率": ("首购量", "新登量"),
    "付费率": ("付费人数", "广告主激活量")
}


# --- 🚀 OCPX 专属高性能 Excel/CSV 数据加载引擎 ---
def load_and_clean_data(file):
    if file.name.endswith('.csv'):
        try:
            raw_df = pd.read_csv(file, encoding='utf_8_sig')
        except:
            try:
                raw_df = pd.read_csv(file, encoding='gbk')
            except:
                raw_df = pd.read_csv(file, encoding='gb18030')
    else:
        try:
            raw_df = pd.read_excel(file, engine='calamine')
        except Exception as e:
            raw_df = pd.read_excel(file)

    raw_df.columns = raw_df.columns.str.strip()

    def clean_name(x):
        if pd.isna(x): return "未知"
        s = str(x).strip()
        if s == "" or s.lower() == "nan": return "未知"
        return s.split('_', 1)[-1] if '_' in s else s

    if '广告主平台名称' not in raw_df.columns and '广告主平台' in raw_df.columns:
        raw_df.rename(columns={'广告主平台': '广告主平台名称'}, inplace=True)

    cols_to_clean = ['广告主平台名称', '媒体平台名称', '广告主平台配置名称']
    for col in cols_to_clean:
        if col in raw_df.columns:
            raw_df[col] = raw_df[col].apply(clean_name)
        else:
            raw_df[col] = "未分类"

    if '调度中心ID' in raw_df.columns:
        raw_df['调度中心ID'] = raw_df['调度中心ID'].astype(str).str.replace('.0', '', regex=False).str.strip().fillna("未关联ID")
    else:
        raw_df['调度中心ID'] = "未关联ID"

    raw_df['日期'] = pd.to_datetime(raw_df['日期'], errors='coerce').dt.date

    if '广告主激活量' in raw_df.columns:
        sort_cols = [c for c in ["广告主平台配置名称", "媒体平台名称", "调度中心ID", "日期"] if c in raw_df.columns]
        raw_df = raw_df.sort_values(by=sort_cols)
        group_cols = [c for c in sort_cols if c != '日期']
        raw_df['前日激活'] = raw_df.groupby(group_cols)['广告主激活量'].shift(1)
    else:
        raw_df['前日激活'] = 0

    return raw_df


# --- 🔒 Session 状态内存锁 ---
if "cleaned_data" not in st.session_state:
    st.session_state["cleaned_data"] = None
if "file_name" not in st.session_state:
    st.session_state["file_name"] = None

uploaded_file = st.file_uploader("📥 上传原始报表数据 (支持 .xlsx / .csv)", type=["csv", "xlsx"])

if uploaded_file:
    if st.session_state["file_name"] != uploaded_file.name:
        with st.status("🚀 正在激活云端计算引擎并清洗大盘数据...", expanded=True) as status:
            st.write("📦 正在识别文件格式与字符集编码...")
            cleaned_df = load_and_clean_data(uploaded_file)
            st.write("🧹 正在执行流失维度空值防御和去重对齐...")
            st.session_state["cleaned_data"] = cleaned_df
            st.session_state["file_name"] = uploaded_file.name
            # 🛠️ 智能加载箱状态更新闭环
            status.update(label="✅ 数据分析锁加载完成，可以开始筛选下钻！", state="complete", expanded=False)
        st.toast(f"成功加载文件: {uploaded_file.name}", icon="🔥")

# 只有当全局 Session 状态里确实存在数据时，才向下渲染看板
if st.session_state["cleaned_data"] is not None:
    try:
        df = st.session_state["cleaned_data"]
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()

        # --- 侧边栏配置区 ---
        with st.sidebar:
            # 🔄 顺位调整一：漏斗四级动态联动筛选直接调到最上方，符合运营排查业务的直觉
            st.markdown("<h3 style='color: #1F77B4;'>🔍 漏斗动态筛选</h3>", unsafe_allow_html=True)

            # 1. 广告主平台
            platform_options = sorted(df["广告主平台名称"].unique().tolist())
            select_all_plat = st.checkbox("🔗 全选所有平台", value=False)
            t_platforms = st.multiselect(
                "1. 广告主平台",
                options=platform_options,
                default=platform_options if select_all_plat else []
            )

            # 联动计算配置号
            sub_df_for_config = df.copy()
            if t_platforms:
                sub_df_for_config = sub_df_for_config[sub_df_for_config["广告主平台名称"].isin(t_platforms)]
            config_options = sorted(sub_df_for_config["广告主平台配置名称"].unique().tolist())

            # 2. 配置号
            select_all_config = st.checkbox("🔗 全选当前配置号", value=False)
            t_configs = st.multiselect(
                "2. 配置号筛选",
                options=config_options,
                default=config_options if select_all_config else []
            )

            # 联动计算媒体
            sub_df_for_media = sub_df_for_config.copy()
            if t_configs:
                sub_df_for_media = sub_df_for_media[sub_df_for_media["广告主平台配置名称"].isin(t_configs)]
            media_options = sorted(sub_df_for_media["媒体平台名称"].unique().tolist())

            # 3. 媒体
            select_all_media = st.checkbox("🔗 全选当前媒体", value=False)
            t_media = st.multiselect(
                "3. 媒体筛选",
                options=media_options,
                default=media_options if select_all_media else []
            )

            # 联动计算调度ID
            sub_df_for_id = sub_df_for_media.copy()
            if t_media:
                sub_df_for_id = sub_df_for_id[sub_df_for_id["媒体平台名称"].isin(t_media)]
            id_options = sorted(sub_df_for_id["调度中心ID"].unique().tolist())

            # 4. 调度中心 ID 筛选
            select_all_ids = st.checkbox("🔗 全选当前调度ID", value=False)
            t_ids = st.multiselect(
                "4. 调度中心ID筛选",
                options=id_options,
                default=id_options if select_all_ids else []
            )

            st.divider()
            # 🔄 顺位调整二：日期筛选移至第二顺位
            st.markdown("<h3 style='color: #1F77B4;'>⏱️ 过滤基准</h3>", unsafe_allow_html=True)
            valid_dates = df['日期'].dropna()
            min_d, max_d = (valid_dates.min(), valid_dates.max()) if not valid_dates.empty else (None, None)
            selected_date_range = st.date_input("选择周期范围", value=(min_d, max_d))

            st.divider()
            st.markdown("<h3 style='color: #1F77B4;'>📈 率指标池</h3>", unsafe_allow_html=True)
            selected_rate_names = []
            rate_keys = list(PRESET_RATES.keys())
            col1, col2 = st.columns(2)
            for i, name in enumerate(rate_keys):
                is_default = name in ["下单率", "次留率"]
                with col1 if i % 2 == 0 else col2:
                    if st.checkbox(name, value=is_default):
                        selected_rate_names.append(name)

            st.markdown("---")
            show_cvr = st.checkbox("⚙️ 开启 自定义CVR", value=True)
            cvr_name = None
            if show_cvr:
                c_num = st.selectbox("CVR 分子", numeric_cols,
                                     index=numeric_cols.index('广告主激活量') if '广告主激活量' in numeric_cols else 0)
                c_den = st.selectbox("CVR 分母", numeric_cols, index=numeric_cols.index(
                    '上报广告主次数') if '上报广告主次数' in numeric_cols else 0)
                cvr_name = f"CVR({c_num}/{c_den})"

            st.divider()
            st.markdown("<h3 style='color: #1F77B4;'>🔄 环比监控</h3>", unsafe_allow_html=True)
            enable_wow = st.toggle("开启指标环比 (对比前一日)", value=False)
            wow_targets = []
            if enable_wow:
                wow_targets = st.multiselect("选择看环比的数值列", numeric_cols,
                                             default=[f for f in ["广告主激活量"] if f in numeric_cols])

            st.divider()
            st.markdown("<h3 style='color: #FF4B4B;'>🚨 多指标风控预警</h3>", unsafe_allow_html=True)
            enable_alert = st.toggle("开启爆红预警高亮", value=False)
            alert_rules = []
            if enable_alert:
                alert_targets_pool = list(selected_rate_names)
                if cvr_name: alert_targets_pool.append(cvr_name)
                if not alert_targets_pool:
                    st.warning("请先勾选显示的率指标")
                else:
                    chosen_targets = st.multiselect("选择需要预警的指标", alert_targets_pool)
                    for target in chosen_targets:
                        st.markdown(f"**{target} 预警配置**")
                        c_logic, c_val = st.columns([1, 2])
                        with c_logic: logic = st.selectbox("逻辑", ["<", "<=", ">", ">=", "=="], key=f"lg_{target}")
                        with c_val: val = st.number_input("阈值(%)", value=5.0, step=0.1, key=f"val_{target}")
                        alert_rules.append({"target": target, "logic": logic, "val": val})

            st.markdown("---")
            s_metrics = st.multiselect("表内显示指标", options=numeric_cols,
                                       default=[f for f in ["广告主激活量", "新登量", "下单量"] if f in numeric_cols])
            show_daily = st.checkbox("开启下钻分日", value=True)

        # --- 🛡️ 拦截未选完的日期 ---
        if not isinstance(selected_date_range, (list, tuple)) or len(selected_date_range) < 2:
            st.info("⏳ 请在左侧边栏选择完整的【开始日期】和【结束日期】...")
            st.stop()

        # --- ⚡ 核心全局精准过滤切片 ---
        f_df_global = df.copy()
        f_df_global = f_df_global[
            (f_df_global['日期'] >= selected_date_range[0]) & (f_df_global['日期'] <= selected_date_range[1])]

        if t_platforms:
            f_df_global = f_df_global[f_df_global["广告主平台名称"].isin(t_platforms)]
        if t_configs:
            f_df_global = f_df_global[f_df_global["广告主平台配置名称"].isin(t_configs)]
        if t_media:
            f_df_global = f_df_global[f_df_global["媒体平台名称"].isin(t_media)]
        if t_ids:
            f_df_global = f_df_global[f_df_global["调度中心ID"].isin(t_ids)]


        # --- 🚀 核心计算引擎函数 (提前执行以供给 KPI 卡片提取精准的大盘率指标) ---
        def process_view(dims, src_df):
            if src_df.empty:
                return pd.DataFrame(), []

            base_needed = list(s_metrics) + ["次日回访量"]
            for r_name in PRESET_RATES: base_needed.extend(list(PRESET_RATES[r_name]))
            if show_cvr: base_needed.extend([c_num, c_den])

            agg_map = {c: 'sum' for c in set(base_needed) if c in src_df.columns}
            if '前日激活' in src_df.columns: agg_map['前日激活'] = 'sum'

            for c in agg_map.keys():
                if c in src_df.columns:
                    src_df[c] = pd.to_numeric(src_df[c], errors='coerce').fillna(0)

            summary = src_df.groupby(dims).agg(agg_map).reset_index()
            sort_target = [c for c in ["广告主激活量", "新登量"] if c in summary.columns]
            if sort_target: summary = summary.sort_values(by=sort_target, ascending=False)

            if show_daily:
                daily = src_df.groupby(dims + ["日期"]).agg(agg_map).reset_index()
                daily = daily.sort_values(by=dims + ["日期"], ascending=True)
                daily["_tmp_next_stay"] = daily.groupby(dims)["次日回访量"].shift(-1).fillna(0)

                if enable_wow and wow_targets:
                    for col in wow_targets:
                        daily[f"prev_{col}"] = daily.groupby(dims)[col].shift(1)

                summary["日期"] = "✨ 汇总"
                combined = []
                for i in range(len(summary)):
                    row = summary.iloc[[i]]
                    mask = True
                    for d in dims: mask &= (daily[d] == row[d].iloc[0])
                    combined.append(pd.concat([row, daily[mask].sort_values(by="日期", ascending=False)]))
                final = pd.concat(combined, ignore_index=True) if combined else summary
            else:
                final = summary

            if dims == ["广告主平台配置名称"] or dims == ["广告主平台名称", "广告主平台配置名称"]:
                total_row = src_df.agg(agg_map).to_frame().T
                for c in total_row.columns:
                    if c in numeric_cols: total_row[c] = total_row[c].fillna(0).astype(int)
                if "广告主平台名称" in dims: total_row["广告主平台名称"] = "【全大盘汇总】"
                total_row["广告主平台配置名称"] = "【全配置号汇总】"
                total_row["日期"] = "✨ 汇总"
                final = pd.concat([total_row, final], ignore_index=True)

            # 率指标计算
            for name, (n, d) in PRESET_RATES.items():
                if n in final.columns and d in final.columns:
                    numerator = pd.to_numeric(final[n], errors='coerce').fillna(0)
                    denominator = pd.to_numeric(final[d], errors='coerce').fillna(0)

                    if name == "次留率":
                        if "_tmp_next_stay" in final.columns:
                            is_daily = (final["日期"] != "✨ 汇总")
                            actual_n = np.where(is_daily, final["_tmp_next_stay"], numerator)
                            final[name] = np.where(denominator > 0, (actual_n / denominator) * 100, 0.0)
                        else:
                            final[name] = np.where(denominator > 0, (numerator / denominator) * 100, 0.0)
                    else:
                        final[name] = np.where(denominator != 0, (numerator / denominator) * 100, 0.0)
                else:
                    final[name] = 0.0

            # CVR 计算
            if show_cvr and c_num in final.columns and c_den in final.columns:
                num = pd.to_numeric(final[c_num], errors='coerce').fillna(0)
                den = pd.to_numeric(final[c_den], errors='coerce').fillna(0)
                final[cvr_name] = np.where(den != 0, (num / den) * 100, 0.0)

            # 环比计算
            wow_col_names = []
            if enable_wow and wow_targets:
                for col in wow_targets:
                    p_col = f"prev_{col}"
                    if p_col in final.columns:
                        wow_col = f"{col}环比"
                        is_real_date = (final["日期"] != "✨ 汇总")
                        cur = pd.to_numeric(final[col], errors='coerce').fillna(0)
                        pre = pd.to_numeric(final[p_col], errors='coerce').fillna(0)
                        final[wow_col] = np.where(
                            is_real_date & (pre != 0),
                            ((cur - pre) / pre) * 100, 0.0
                        )
                        wow_col_names.append(wow_col)

            for c in s_metrics:
                if c in final.columns:
                    final[c] = pd.to_numeric(final[c], errors='coerce').fillna(0).astype(int)

            return final, wow_col_names


        # 提前计算配置号大盘视图，确保顶层反射卡片能抓取到最精准的汇总率指标
        base_dims_v1 = ["广告主平台配置名称"]
        if t_platforms or "广告主平台名称" in f_df_global.columns:
            base_dims_v1 = ["广告主平台名称", "广告主平台配置名称"]
        res1, w1 = process_view(base_dims_v1, f_df_global)

        # ✨ 视觉装饰 1：智能动态反射 KPI 卡片（完美兼容“有下单无新登”等各类特殊、缺失业务数据链）
        if not f_df_global.empty:
            active_kpi_pool = []

            # ① 绝对数值指标追加（动态同步侧边栏）
            for m_col in s_metrics:
                if m_col in f_df_global.columns:
                    active_kpi_pool.append({"name": m_col, "type": "number"})

            # ② 率指标追加（动态同步侧边栏）
            for r_name in selected_rate_names:
                if r_name in PRESET_RATES:
                    active_kpi_pool.append({"name": r_name, "type": "rate"})
            if show_cvr and cvr_name:
                active_kpi_pool.append({"name": cvr_name, "type": "rate"})

            # ③ 兜底防御：若侧边栏全空，硬编码前两项防止报错空白
            if not active_kpi_pool:
                default_cols = [c for c in ["广告主激活量", "下单量", "新登量"] if c in f_df_global.columns]
                for d_c in default_cols:
                    active_kpi_pool.append({"name": d_c, "type": "number"})

            # 取前 4 个激活指标渲染成大厂风高亮彩色卡片
            display_kpis = active_kpi_pool[:4]
            kpi_cols = st.columns(len(display_kpis))

            card_colors = ["#1F77B4", "#FF7F0E", "#2CA02C", "#9467BD"]
            card_style = """
            <div style="
                background-color: #F8F9FA; 
                padding: 15px; 
                border-radius: 8px; 
                border-left: 5px solid {color}; 
                box-shadow: 2px 2px 8px rgba(0,0,0,0.04);
                text-align: left;">
                <span style="font-size: 13px; color: #666666; font-weight: 500;">{label}</span>
                <h3 style="margin: 3px 0 0 0; color: #2C3E50; font-size: 24px; font-family: -apple-system, sans-serif;">{value}</h3>
            </div>
            """

            for idx, kpi in enumerate(display_kpis):
                kpi_name = kpi["name"]
                kpi_type = kpi["type"]
                color = card_colors[idx % len(card_colors)]

                with kpi_cols[idx]:
                    if kpi_type == "number":
                        val_sum = int(f_df_global[kpi_name].sum())
                        st.markdown(card_style.format(label=f"📊 周期总 {kpi_name}", value=f"{val_sum:,}", color=color),
                                    unsafe_allow_html=True)

                    elif kpi_type == "rate":
                        if 'res1' in locals() and not res1.empty and kpi_name in res1.columns:
                            rate_val = res1[kpi_name].iloc[0]
                        else:
                            if kpi_name in PRESET_RATES:
                                n_col, d_col = PRESET_RATES[kpi_name]
                                n_sum = f_df_global[n_col].sum() if n_col in f_df_global.columns else 0
                                d_sum = f_df_global[d_col].sum() if d_col in f_df_global.columns else 0
                                rate_val = (n_sum / d_sum * 100) if d_sum > 0 else 0.0
                            elif show_cvr and kpi_name == cvr_name:
                                n_sum = f_df_global[c_num].sum() if c_num in f_df_global.columns else 0
                                d_sum = f_df_global[c_den].sum() if c_den in f_df_global.columns else 0
                                rate_val = (n_sum / d_sum * 100) if d_sum > 0 else 0.0
                            else:
                                rate_val = 0.0

                        st.markdown(
                            card_style.format(label=f"📈 大盘综合 {kpi_name}", value=f"{rate_val:.2f}%", color=color),
                            unsafe_allow_html=True)
            st.write("")
            st.divider()
        else:
            st.warning("⚠️ 当前筛选组合下无数据，请检查侧边栏多选框是否勾选。")


        # --- 前端样式与数据表格渲染引擎 ---
        def style_and_display(res_df, base_dims, wow_cols):
            if res_df.empty: return st.info("所选筛选条件下无数据")

            table_rates = selected_rate_names + ([cvr_name] if show_cvr else []) + wow_cols

            actual_dims = [d for d in base_dims if d in res_df.columns]
            actual_metrics = [c for c in s_metrics if c in res_df.columns]
            actual_rates = [r for r in table_rates if r in res_df.columns]
            disp_cols = actual_dims + actual_metrics + actual_rates

            def apply_style(row):
                styles = ['' for _ in row]
                if '【全配置号汇总】' in str(row.get('广告主平台配置名称', '')) or '【全大盘汇总】' in str(row.get('广告主平台名称', '')):
                    styles = ['background-color: #FFF2CC; font-weight: bold; color: #D68910' for _ in styles]
                elif '✨ 汇总' in str(row.get('日期', '')):
                    styles = ['background-color: #E6F3FF; font-weight: bold; color: #1f77b4' for _ in styles]

                if enable_alert:
                    for rule in alert_rules:
                        target, logi, threshold = rule['target'], rule['logic'], rule['val']
                        if target in disp_cols:
                            try:
                                val = float(row[target])
                                hit = False
                                if logi == "<":
                                    hit = (val < threshold)
                                elif logi == "<=":
                                    hit = (val <= threshold)
                                elif logi == ">":
                                    hit = (val > threshold)
                                elif logi == ">=":
                                    hit = (val >= threshold)
                                elif logi == "==":
                                    hit = (abs(val - threshold) < 0.01)
                                if hit:
                                    idx = disp_cols.index(target)
                                    styles[idx] = 'color: white; font-weight: bold; background-color: #FF4B4B;'
                            except:
                                pass

                for w_col in wow_cols:
                    if w_col in disp_cols:
                        idx = disp_cols.index(w_col)
                        try:
                            val = float(row[w_col])
                            if val > 0:
                                styles[idx] += '; color: #d00000; font-weight: bold;'
                            elif val < 0:
                                styles[idx] += '; color: #008000; font-weight: bold;'
                        except:
                            pass
                return styles

            c_config = {}
            if "日期" in disp_cols:
                c_config["日期"] = st.column_config.TextColumn(width="small")
            for col in actual_rates:
                c_config[col] = st.column_config.NumberColumn(format="%.2f%%", width="small")
            for col in actual_metrics:
                c_config[col] = st.column_config.NumberColumn(format="%d")

            st.dataframe(res_df[disp_cols].style.apply(apply_style, axis=1), use_container_width=True, hide_index=True,
                         column_config=c_config)


        # 🚀 ==================== 页面层级多维下钻对齐渲染 ====================

        st.subheader("1️⃣ 配置号大盘分析汇总")
        display_res1 = res1.head(700) if not res1.empty else res1
        style_and_display(display_res1, base_dims_v1 + (["日期"] if show_daily else []), w1)
        st.divider()

        st.subheader("2️⃣ 媒体平台明细")
        if "媒体平台名称" in f_df_global.columns and not f_df_global.empty:
            media_summary = f_df_global.groupby("媒体平台名称", dropna=True)["广告主激活量"].sum().reset_index().sort_values(
                by="广告主激活量", ascending=False)
            media_list_sorted = media_summary["媒体平台名称"].tolist()
            st.markdown(
                f"💡 当前筛选组合内共覆盖 **{len(media_list_sorted)}** 个媒体：`{' / '.join(media_list_sorted) if media_list_sorted else '无'}`")
        else:
            st.markdown("💡 共有媒体：0 个")

        base_dims_v2 = base_dims_v1 + ["媒体平台名称"]
        res2, w2 = process_view(base_dims_v2, f_df_global)
        style_and_display(res2, base_dims_v2 + (["日期"] if show_daily else []), w2)
        st.divider()

        st.subheader("3️⃣ 调度ID明细")
        if "媒体平台名称" in f_df_global.columns and "调度中心ID" in f_df_global.columns and not f_df_global.empty:
            media_id_count = f_df_global.groupby("媒体平台名称")["调度中心ID"].nunique().reset_index()
            act_sum = f_df_global.groupby("媒体平台名称")["广告主激活量"].sum()
            media_id_count["激活量"] = media_id_count["媒体平台名称"].map(act_sum)
            media_id_count = media_id_count.sort_values("激活量", ascending=False)
            id_detail = " ｜ ".join(
                [f"**{row['媒体平台名称']}** ({row['调度中心ID']}个)" for _, row in media_id_count.iterrows()])
        else:
            id_detail = "无数据"

        st.markdown(f"🆔 各渠道下调度id分布：{id_detail}")
        base_dims_v3 = ["媒体平台名称", "调度中心ID"]
        res3, w3 = process_view(base_dims_v3, f_df_global)
        style_and_display(res3, base_dims_v3 + (["日期"] if show_daily else []), w3)

    except Exception as e:
        st.error(f"处理出现技术错误: {e}")
else:
    st.info("👋 欢迎使用！请在上方上传 OCPX 业务数据报表!")
    st.info("ps：可上传完整底表，无需筛选字段～")
