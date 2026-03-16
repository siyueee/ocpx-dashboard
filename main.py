import streamlit as st
import pandas as pd
import numpy as np

# 1. 基础配置
st.set_page_config(page_title="OCPX看板", layout="wide")
st.title("📊 OCPX 业务数据全维度分析看板")

# --- 预设指标池 ---
PRESET_RATES = {
    "下单率": ("下单量", "广告主激活量"),
    "次留率": ("次日回访量", "前日激活"),
    "激活率": ("广告主激活量", "上报广告主次数"),
    "唤醒率": ("唤醒量", "上报广告主次数"),
    "首唤率": ("首唤量", "上报广告主次数"),
    "新登率": ("新登量", "广告主激活量"),
    "首购率": ("首购量", "新登量"),
    "付费率": ("付费人数", "广告主激活量")
}


# --- 🚀 核心加速逻辑：数据加载缓存 ---
@st.cache_data(ttl=3600)
def load_and_clean_data(file):
    if file.name.endswith('.csv'):
        try:
            raw_df = pd.read_csv(file, encoding='utf_8_sig')
        except:
            raw_df = pd.read_csv(file, encoding='gbk')
    else:
        raw_df = pd.read_excel(file)

    def clean_name(x):
        if pd.isna(x): return x
        s = str(x)
        return s.split('_', 1)[-1] if '_' in s else s

    for col in ['媒体平台名称', '广告主平台配置名称']:
        if col in raw_df.columns:
            raw_df[col] = raw_df[col].apply(clean_name)

    if '调度中心ID' in raw_df.columns:
        raw_df['调度中心ID'] = raw_df['调度中心ID'].astype(str).str.replace('.0', '', regex=False)

    raw_df['日期'] = pd.to_datetime(raw_df['日期']).dt.date

    # 预计算用于“环比”和“次留”的前置数据
    if '广告主激活量' in raw_df.columns:
        sort_cols = [c for c in ["广告主平台配置名称", "媒体平台名称", "调度中心ID", "日期"] if c in raw_df.columns]
        raw_df = raw_df.sort_values(by=sort_cols)
        group_cols = [c for c in sort_cols if c != '日期']
        raw_df['前日激活'] = raw_df.groupby(group_cols)['广告主激活量'].shift(1)
    else:
        raw_df['前日激活'] = 0

    return raw_df


uploaded_file = st.file_uploader("上传报表", type=["csv", "xlsx"])

if uploaded_file:
    try:
        df = load_and_clean_data(uploaded_file)
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()

        # --- 侧边栏 ---
        with st.sidebar:
            st.header("📅 时间维度")
            selected_date_range = st.date_input("选择周期", value=(df['日期'].min(), df['日期'].max()))

            st.divider()
            st.header("📈 率指标 + 自定义CVR")
            selected_rate_names = []
            rate_keys = list(PRESET_RATES.keys())
            col1, col2 = st.columns(2)
            for i, name in enumerate(rate_keys):
                is_default = name in ["下单率", "次留率"]
                with col1 if i % 2 == 0 else col2:
                    if st.checkbox(name, value=is_default):
                        selected_rate_names.append(name)

            # 自定义CVR移入率指标区
            st.markdown("---")
            show_cvr = st.checkbox("开启 自定义CVR", value=True)
            cvr_name = None
            if show_cvr:
                c_num = st.selectbox("CVR 分子", numeric_cols,
                                     index=numeric_cols.index('广告主激活量') if '广告主激活量' in numeric_cols else 0)
                c_den = st.selectbox("CVR 分母", numeric_cols, index=numeric_cols.index(
                    '上报广告主次数') if '上报广告主次数' in numeric_cols else 0)
                cvr_name = f"CVR({c_num}/{c_den})"

            # --- 💡 环比配置 ---
            st.divider()
            st.header("🔄 环比配置")
            enable_wow = st.toggle("开启指标环比 (对比前一日)", value=False)
            wow_targets = []
            if enable_wow:
                wow_targets = st.multiselect("选择需要看环比的数值", numeric_cols,
                                             default=[f for f in ["广告主激活量"] if f in numeric_cols])

            st.divider()
            st.header("🚨 预警设置")
            enable_alert = st.toggle("开启多指标预警", value=False)
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

            st.divider()
            st.header("🔍 维度与筛选")
            t_configs = st.multiselect("配置号筛选", options=df["广告主平台配置名称"].unique().tolist())
            t_media = st.multiselect("媒体筛选", options=df["媒体平台名称"].unique().tolist())
            s_metrics = st.multiselect("数值列", options=numeric_cols,
                                       default=[f for f in ["广告主激活量", "新登量", "下单量"] if f in numeric_cols])
            show_daily = st.checkbox("下钻分日", value=True)


            # --- 计算逻辑 ---
            def process_view(dims):
                base_needed = list(s_metrics) + ["次日回访量"]
                for r_name in PRESET_RATES: base_needed.extend(list(PRESET_RATES[r_name]))
                if show_cvr: base_needed.extend([c_num, c_den])

                agg_map = {c: 'sum' for c in set(base_needed) if c in df.columns}
                if '前日激活' in df.columns: agg_map['前日激活'] = 'sum'

                f_df = df.copy()
                if isinstance(selected_date_range, (list, tuple)) and len(selected_date_range) == 2:
                    f_df = f_df[(f_df['日期'] >= selected_date_range[0]) & (f_df['日期'] <= selected_date_range[1])]
                if t_configs: f_df = f_df[f_df["广告主平台配置名称"].isin(t_configs)]
                if t_media: f_df = f_df[f_df["媒体平台名称"].isin(t_media)]

                # 强制转数值，避免空值/类型错误
                for c in agg_map.keys():
                    if c in f_df.columns:
                        f_df[c] = pd.to_numeric(f_df[c], errors='coerce').fillna(0)

                summary = f_df.groupby(dims).agg(agg_map).reset_index()
                sort_target = [c for c in ["广告主激活量", "新登量"] if c in summary.columns]
                if sort_target: summary = summary.sort_values(by=sort_target, ascending=False)

                if show_daily:
                    daily = f_df.groupby(dims + ["日期"]).agg(agg_map).reset_index()
                    if enable_wow and wow_targets:
                        daily = daily.sort_values(by=dims + ["日期"])
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

                # 总配置号汇总
                if dims == ["广告主平台配置名称"]:
                    total_row = f_df.agg(agg_map).to_frame().T
                    for c in total_row.columns:
                        if c in numeric_cols: total_row[c] = total_row[c].fillna(0).astype(int)
                    total_row["广告主平台配置名称"] = "【全配置号汇总】"
                    total_row["日期"] = "✨ 汇总"
                    final = pd.concat([total_row, final], ignore_index=True)

                # ===================== 【修复除法报错】 =====================
                for name, (n, d) in PRESET_RATES.items():
                    if n in final.columns and d in final.columns:
                        numerator = pd.to_numeric(final[n], errors='coerce').fillna(0)
                        denominator = pd.to_numeric(final[d], errors='coerce').fillna(0)

                        if name == "次留率":
                            final[name] = np.where(denominator > 0, (numerator / denominator) * 100, 0.0)
                        else:
                            final[name] = np.where(denominator != 0, (numerator / denominator) * 100, 0.0)
                    else:
                        final[name] = 0.0

                # 自定义CVR
                if show_cvr and c_num in final.columns and c_den in final.columns:
                    num = pd.to_numeric(final[c_num], errors='coerce').fillna(0)
                    den = pd.to_numeric(final[c_den], errors='coerce').fillna(0)
                    final[cvr_name] = np.where(den != 0, (num / den) * 100, 0.0)
                # ==============================================================

                # 环比
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

                # 整数格式化
                for c in s_metrics:
                    if c in final.columns:
                        final[c] = pd.to_numeric(final[c], errors='coerce').fillna(0).astype(int)

                return final, wow_col_names


        def style_and_display(res_df, base_dims, wow_cols):
            if res_df.empty: return st.info("无数据")

            table_rates = selected_rate_names + ([cvr_name] if show_cvr else []) + wow_cols
            disp_cols = base_dims + [c for c in s_metrics if c in res_df.columns] + table_rates

            def apply_style(row):
                styles = ['' for _ in row]
                if '【全配置号汇总】' in str(row.get('广告主平台配置名称', '')):
                    styles = ['background-color: #FFF2CC; font-weight: bold; color: #D68910' for _ in styles]
                elif '✨ 汇总' in str(row.get('日期', '')):
                    styles = ['background-color: #E6F3FF; font-weight: bold; color: #1f77b4' for _ in styles]

                # 预警
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

                # 环比颜色
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

            c_config = {"日期": st.column_config.TextColumn(width="small")}
            for col in table_rates:
                c_config[col] = st.column_config.NumberColumn(format="%.2f%%", width="small")
            for col in s_metrics:
                if col in disp_cols:
                    c_config[col] = st.column_config.NumberColumn(format="%d")

            st.dataframe(res_df[disp_cols].style.apply(apply_style, axis=1), use_container_width=True, hide_index=True,
                         column_config=c_config)


        # 🚀 渲染页面
        st.subheader("1️⃣ 配置号汇总")
        res1, w1 = process_view(["广告主平台配置名称"])
        display_res1 = res1.head(700) 
        style_and_display(display_res1, ["广告主平台配置名称"] + (["日期"] if show_daily else []), w1)
        st.divider()

        st.subheader("2️⃣ 媒体平台表现")
        f_df = df.copy()
        
        if isinstance(selected_date_range, (list, tuple)) and len(selected_date_range) == 2:
            f_df = f_df[(f_df['日期'] >= selected_date_range[0]) & (f_df['日期'] <= selected_date_range[1])]
        if t_configs: f_df = f_df[f_df["广告主平台配置名称"].isin(t_configs)]
        if t_media: f_df = f_df[f_df["媒体平台名称"].isin(t_media)]
        media_summary = f_df.groupby("媒体平台名称", dropna=True)["广告主激活量"].sum().reset_index().sort_values(
            by="广告主激活量", ascending=False)
        media_list_sorted = media_summary["媒体平台名称"].tolist()
        st.markdown(
            f"**📊 总数：{len(media_list_sorted)} 个** ｜ **📝 明细：{'、'.join(media_list_sorted) if media_list_sorted else '无'}**")
        res2, w2 = process_view(["广告主平台配置名称", "媒体平台名称"])
        style_and_display(res2, ["广告主平台配置名称", "媒体平台名称"] + (["日期"] if show_daily else []), w2)
        st.divider()

        st.subheader("3️⃣ 调度 ID 明细")
        if "媒体平台名称" in f_df.columns and "调度中心ID" in f_df.columns:
            media_id_count = f_df.groupby("媒体平台名称")["调度中心ID"].nunique().reset_index()
            act_sum = f_df.groupby("媒体平台名称")["广告主激活量"].sum()
            media_id_count["激活量"] = media_id_count["媒体平台名称"].map(act_sum)
            media_id_count = media_id_count.sort_values("激活量", ascending=False)
            id_detail = "，".join(
                [f"{row['媒体平台名称']}：{row['调度中心ID']}个" for _, row in media_id_count.iterrows()])
        else:
            id_detail = "无数据"
        st.markdown(f"**🆔 各媒体调度ID：{id_detail}**")
        res3, w3 = process_view(["媒体平台名称", "调度中心ID"])
        style_and_display(res3, ["媒体平台名称", "调度中心ID"] + (["日期"] if show_daily else []), w3)

    except Exception as e:
        st.error(f"处理出现技术错误: {e}")
else:
    st.info("👋 请上传报表使用")
