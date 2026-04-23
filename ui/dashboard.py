"""Streamlit 可视化。运行: `streamlit run ui/dashboard.py`"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# 允许从项目根路径导入
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import ArbitragePipeline, PipelineConfig  # noqa: E402
from storage import ArbitrageOpportunity, MatchedSupplier, SourceProduct, get_db  # noqa: E402


st.set_page_config(page_title="Best Seller Arbitrage", layout="wide")
st.title("跨平台选品套利面板")

db = get_db()


with st.sidebar:
    st.header("抓取 / 分析")
    platforms = st.multiselect("平台", ["amazon", "temu"], default=["amazon", "temu"])
    limit = st.slider("每平台商品数", 1, 30, 5)
    offers = st.slider("每商品 1688 匹配数", 1, 10, 5)
    min_margin = st.slider("最低利润率", 0.0, 0.8, 0.25, step=0.05)
    ship_mode = st.selectbox("头程方式", ["sea", "air"], index=0)
    run_btn = st.button("运行 Pipeline", type="primary")


if run_btn:
    if not platforms:
        st.error("至少选择一个平台")
    else:
        with st.spinner("采集中..."):
            cfg = PipelineConfig(
                platforms=platforms,
                limit_per_platform=limit,
                offers_per_product=offers,
                min_margin=min_margin,
                ship_mode=ship_mode,
            )
            stats = ArbitragePipeline(cfg).run()
        st.success(f"完成: {stats}")


tab_opps, tab_sources, tab_suppliers = st.tabs(["套利机会", "源商品", "匹配货源"])


def _load_opportunities() -> pd.DataFrame:
    with db.session() as s:
        rows = (
            s.query(ArbitrageOpportunity, SourceProduct, MatchedSupplier)
            .join(SourceProduct, SourceProduct.id == ArbitrageOpportunity.source_id)
            .join(MatchedSupplier, MatchedSupplier.id == ArbitrageOpportunity.supplier_id)
            .order_by(ArbitrageOpportunity.margin.desc())
            .all()
        )
    data = []
    for opp, src, sup in rows:
        data.append(
            {
                "平台": src.platform,
                "商品": src.title,
                "售价(USD)": opp.sell_price_usd,
                "1688价(CNY)": sup.price_cny,
                "成本(USD)": opp.cost_usd,
                "FBA(USD)": opp.fba_fee_usd,
                "头程(USD)": opp.logistics_usd,
                "佣金(USD)": opp.referral_fee_usd,
                "利润(USD)": opp.profit_usd,
                "利润率": f"{opp.margin:.1%}",
                "相似度": f"{sup.similarity:.2f}" if sup.similarity else "-",
                "源链接": src.url,
                "货源链接": sup.url,
            }
        )
    return pd.DataFrame(data)


def _load_sources() -> pd.DataFrame:
    with db.session() as s:
        rows = s.query(SourceProduct).order_by(SourceProduct.platform, SourceProduct.rank).all()
    return pd.DataFrame(
        [
            {
                "平台": r.platform,
                "ID": r.external_id,
                "排名": r.rank,
                "标题": r.title,
                "类目": r.category,
                "售价(USD)": r.price_usd,
                "评分": r.rating,
                "评论数": r.review_count,
                "重量(kg)": r.weight_kg,
                "链接": r.url,
            }
            for r in rows
        ]
    )


def _load_suppliers() -> pd.DataFrame:
    with db.session() as s:
        rows = s.query(MatchedSupplier, SourceProduct).join(
            SourceProduct, SourceProduct.id == MatchedSupplier.source_id
        ).order_by(MatchedSupplier.similarity.desc()).all()
    return pd.DataFrame(
        [
            {
                "源商品": src.title,
                "货源标题": sup.title_cn,
                "价格(CNY)": sup.price_cny,
                "起订量": sup.moq,
                "相似度": sup.similarity,
                "同款": bool(sup.llm_same_product),
                "判断理由": sup.llm_reason,
                "链接": sup.url,
            }
            for sup, src in rows
        ]
    )


with tab_opps:
    df = _load_opportunities()
    if df.empty:
        st.info("暂无数据，先点击左侧 `运行 Pipeline`。")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "下载 CSV",
            df.to_csv(index=False).encode("utf-8-sig"),
            file_name="arbitrage_opportunities.csv",
            mime="text/csv",
        )

with tab_sources:
    df = _load_sources()
    if df.empty:
        st.info("暂无源商品数据。")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

with tab_suppliers:
    df = _load_suppliers()
    if df.empty:
        st.info("暂无匹配货源数据。")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
