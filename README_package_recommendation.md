# recom 体检套餐推荐系统

## 🎯 系统概述
基于医院体检套餐数据的推荐与问答系统。支持“寻系列高危规则”和“非寻系列 属性/功能/亮点 标签”，并可从 JSON 配置热更新；可选开启基于 `full_items` 的约束与亮点解析以提升准确度。

## 📂 目录结构
```
recom/
├── __init__.py
├── data.py                      # 加载 packages.json（独立于 reco）
├── recommendation_agent.py      # 推荐核心 + 规则加载（支持 JSON 配置）
├── web.py                       # FastAPI UI 与接口（/recom/ui）
├── packages.json                # 套餐数据（本地）
├── demo_package_recommendation.py# 代码演示脚本
└── config/
    ├── keyword_to_tags.json     # 检查项目关键词 → 标签
    ├── risk_rules.json          # 寻系列高危整合标签与触发规则
    ├── meta_tag_rules.json      # 非寻系列的 属性/功能/亮点 规则
    └── full_items_rules.json    # full_items 解析：已婚/性别/儿童倾向与亮点
```

## 🚀 快速开始
- 启动交互式 UI（浏览器演示）
```bash
python -m uvicorn recom.web:app --reload --port 8000
# 访问 http://127.0.0.1:8000/recom/ui
```
- 运行代码演示（控制台输入/输出最直观）
```bash
python recom/demo_package_recommendation.py
```

## 🧩 输入字段（演示/接口通用）
- `age: int`、`gender: male|female`、`budget: float`、`purpose: 常规体检|入职体检|婚前体检|肿瘤筛查|慢病管理|高端体检`
- `health_concerns: [str]`、`family_history: [str]`、`lifestyle_factors: [str]`
- 可选（用于高危/约束更精确）：`marital_status`、`region`、`symptoms`、`medical_history`、`treatment_history`、`occupational_exposure`

> 注意：“吸烟”等应放入 `lifestyle_factors`；例如：`{"lifestyle_factors": ["吸烟"]}`。

## 🧠 标签与规则
- 寻系列：使用 `config/risk_rules.json` 的整合型风险标签（例如「肺癌相关风险」）与触发词（家族史/病史/习惯/地域/职业暴露等）。命中后推荐理由包含“高危匹配：XX相关风险”。
- 暖/爱/和/入职：使用 `config/meta_tag_rules.json` 的“属性/场景 + 功能 + 亮点”规则生成标签，用于精准匹配自然语言需求。
- 自动派生：`config/keyword_to_tags.json` 由检查项目关键词派生通用标签（如“甲胎蛋白”→“肿瘤筛查”）。
- full_items 增强（默认开启）：`recommendation_agent.py` 中 `self.use_full_items_enhance = True`
  - 解析 `full_items` 得到：`married_only`、`contains_female_specific`、`contains_male_specific`、`child_preferred` 等约束
  - 解析亮点：如“颈动脉超声/骨密度/动态血压/胃肠镜/HPV/TCT”
  - 约束未满足时软降分并在推荐理由提示；亮点会显示在理由中

## 🔁 配置热更新
- 修改 `recom/config/*.json` 后，重新实例化 `PackageRecommendationAgent()`（或重启进程）即可生效。
- 若 JSON 缺失或解析失败，系统自动回退到内置默认规则，保证可用。

## 🧪 代码演示脚本（节选）
```python
from recom.recommendation_agent import create_recommendation_agent
agent = create_recommendation_agent()
user = {"age":45, "gender":"male", "budget":2000, "purpose":"肿瘤筛查", "lifestyle_factors":["吸烟"]}
recs = agent.recommend_packages(user, top_n=3)
for i, rec in enumerate(recs, 1):
    print(i, rec.get("package_name"), rec.get("recommendation_reason"))
```

## ✅ 约定与风格
- 代码遵循“高可读性、显式规则、可配置化”的设计；禁止过度注释，保留必要说明。
- UI 演示仅作为辅助，不影响推荐 API；服务端接口路径：`POST /recom/recommend`。

## 📈 后续可选增强
- 将触发词扩展为同义词词表与数值阈值（如吸烟包年）；
- 加入用例集并统计 top1/top3 命中率；
- 用户反馈闭环，持续优化规则与权重。 