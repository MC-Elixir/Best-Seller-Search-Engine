采集层
Playwright          # 无头浏览器，处理动态渲染
httpx / requests    # 直接API调用（Temu抓包后）
fake-useragent      # UA伪装
rotating-proxies    # 代理轮换（初期可以先不用）
数据处理层
pydantic            # 数据结构定义和验证
pandas              # 数据整理和利润计算
deep-translator     # 中英文翻译（商品标题）
匹配层
1688官方API         # 图搜 + 关键词搜索
openai / anthropic  # LLM辅助判断是否同款
sentence-transformers  # 文本向量相似度（可选）
存储层
SQLite + SQLAlchemy  # 本地轻量数据库，够用
输出层
Streamlit           # 快速做本地可视化界面

项目结构
product-arbitrage/
├── config/
│   └── settings.py          # API keys, 代理配置, 各平台参数
│
├── scrapers/
│   ├── base.py              # 基础爬虫类（重试、限速、UA轮换）
│   ├── amazon.py            # Amazon Best Sellers抓取
│   └── temu.py              # Temu热门商品抓取
│
├── matchers/
│   ├── alibaba_api.py       # 1688 API封装（图搜+关键词）
│   ├── text_matcher.py      # 文本相似度匹配
│   └── llm_judge.py         # LLM最终判断是否同款
│
├── calculators/
│   ├── profit.py            # 利润率计算
│   ├── fba_fees.py          # FBA费用估算
│   └── logistics.py         # 头程物流成本估算
│
├── storage/
│   ├── models.py            # SQLAlchemy ORM模型
│   └── db.py                # 数据库操作封装
│
├── pipeline/
│   └── main_pipeline.py     # 主流程编排
│
├── ui/
│   └── dashboard.py         # Streamlit界面
│
└── main.py                  # 入口
