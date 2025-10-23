# -*- coding: utf-8 -*-
"""
recom2/web.py - 体检套餐推荐系统 Web API

核心功能：
1. 体检套餐个性化推荐
2. 基于推荐结果的智能问答
3. 套餐数据管理和查询

并发安全设计：
- 每次请求创建新的Agent实例，确保线程安全
- 无状态API设计，支持水平扩展
- 通过user_id和trace_id实现请求追踪和用户区分
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Any, Dict

from .recommendation_agent import create_recommendation_agent
from .data import load_packages
from .qa import answer_question
import os
from pathlib import Path

# 加载环境变量配置（可选）
try:
	from dotenv import load_dotenv  # type: ignore
	load_dotenv(dotenv_path=Path(__file__).parent / "config" / ".env")
except Exception:
	# 未安装或未找到 .env 不影响运行
	pass

# 创建FastAPI应用实例
app = FastAPI(title="体检套餐推荐系统", version="1.0.0")

# ========== API 数据模型定义 ==========

class WebRecommendIn(BaseModel):
	"""套餐推荐请求模型
	
	必填参数：
	- user_id: 用户唯一标识
	- gender: 性别（male/female），决定套餐类型
	- age: 年龄，决定体检重点
	- budget: 预算（元），决定价格范围
	
	可选参数（精准匹配加分项）：
	- purpose: 体检目的
	- health_concerns: 健康关注点
	- family_history: 家族病史
	- lifestyle_factors: 生活习惯
	"""
	# 必填参数
	user_id: str  # 用户唯一标识
	gender: str  # 性别：male 或 female
	age: int  # 年龄（岁）
	budget: float  # 预算（元）
	
	# 可选参数
	purpose: Optional[str] = None  # 体检目的：常规体检/入职体检/婚前体检/肿瘤筛查等
	health_concerns: Optional[List[str]] = None  # 健康关注点列表
	family_history: Optional[List[str]] = None  # 家族病史列表
	lifestyle_factors: Optional[List[str]] = None  # 生活习惯因素列表
	top_n: int = 3  # 返回推荐套餐数量，默认3个

class WebRecommendOut(BaseModel):
	trace_id: str  # 请求追踪ID - 用于问题排查和日志关联
	status: str  # 状态：success/error
	timestamp: str  # 响应时间戳 - 便于调试
	data: dict  # 实际数据（包含user_id和recommended）

class WebQAIn(BaseModel):
	user_id: str  # 用户唯一标识（必填）
	question: str  # 用户问题（必填）
	gender: Optional[str] = None  # 用户性别（可选）
	context: Optional[Dict[str, Any]] = None  # 推荐结果上下文（可选）

class WebQAOut(BaseModel):
	trace_id: str  # 请求追踪ID
	status: str  # 状态：success/error
	timestamp: str  # 响应时间戳
	answer: str  # 回答内容

@app.get("/health")
def health():
	return {"ok": True}

FEMALE_KW = ["（女", "女）", "子宫", "卵巢", "乳腺", "宫颈", "HPV", "TCT", "妇科", "盆腔"]
MALE_KW = ["（男", "男）", "前列腺", "PSA"]


def _llm_status_dict() -> Dict[str, Any]:
	openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY_1")
	bailian_key = os.getenv("BAILIAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
	key = openai_key or bailian_key
	has_key = bool(key)
	model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "(default)"
	provider = "openai" if openai_key else ("bailian" if bailian_key else "")
	base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
	return {"has_key": has_key, "model": model, "provider": provider, "base_url": base_url}

@app.get("/recom/llm_status")
def llm_status():
	return _llm_status_dict()


def _filter_items_by_gender(items: List[Dict[str, Any]], gender: str) -> List[Dict[str, Any]]:
	"""根据性别过滤检查项目
	
	逻辑说明：
	1. 男性用户：过滤掉纯女性项目（如妇科检查）
	2. 女性用户：过滤掉纯男性项目（如前列腺检查）
	3. 通用项目：保留（如血常规、肝功能等）
	
	Args:
		items: 检查项目列表
		gender: 用户性别 male/female
		
	Returns:
		过滤后的项目列表
	"""
	if gender not in ("male", "female"):
		return items  # 性别未知，返回全部项目
		
	filtered: List[Dict[str, Any]] = []
	for it in items:
		name = str(it.get("name", ""))
		# 检测项目是否包含性别特异关键词
		is_female = any(k in name for k in FEMALE_KW)
		is_male = any(k in name for k in MALE_KW)
		
		if gender == "male":
			# 男性：排除纯女性项目
			if is_female and not is_male:
				continue
		else:
			# 女性：排除纯男性项目
			if is_male and not is_female:
				continue
				
		filtered.append(it)
	return filtered


def _scan_items_gender(base_pkg: Dict[str, Any]) -> Dict[str, bool]:
	"""扫描套餐的摘要与分组项目，返回是否含男性/女性特异关键词。"""
	has_female = False
	has_male = False
	for s in (base_pkg.get("summary_items") or []):
		text = str(s)
		if any(k in text for k in FEMALE_KW):
			has_female = True
		if any(k in text for k in MALE_KW):
			has_male = True
	for block in (base_pkg.get("full_items") or []):
		for it in (block.get("items") or []):
			name = str(it.get("name", ""))
			if any(k in name for k in FEMALE_KW):
				has_female = True
			if any(k in name for k in MALE_KW):
				has_male = True
	return {"female": has_female, "male": has_male}


def _infer_declared_gender(base_pkg: Dict[str, Any]) -> Optional[str]:
	code = str(base_pkg.get("code", ""))
	name = str(base_pkg.get("name", ""))
	if code.endswith("_M") or "(男" in name:
		return "male"
	if code.endswith("_F") or "(女" in name:
		return "female"
	return None


def _expand_by_gender(base_pkg: Dict[str, Any]) -> List[Dict[str, Any]]:
	declared = _infer_declared_gender(base_pkg)
	price = base_pkg.get("price")
	# 从项目自动推断
	flags = _scan_items_gender(base_pkg)
	female_only = flags["female"] and not flags["male"]
	male_only = flags["male"] and not flags["female"]
	both_genders = flags["male"] and flags["female"]
	# 若已声明性别，但项目仅属于另一性别，则直接不展示该套餐
	if declared == "male" and female_only:
		return []
	if declared == "female" and male_only:
		return []
	# 1) 已声明性别或仅限定某一性别 -> 只输出相应性别
	if declared or female_only or male_only:
		gender = declared or ("female" if female_only else "male")
		pkg = {**base_pkg}
		if isinstance(price, dict):
			pkg["price"] = price.get("male" if gender == "male" else "female")
		summary = base_pkg.get("summary_items") or []
		pkg["summary_items"] = [x["name"] for x in _filter_items_by_gender([{ "name": s } for s in summary], gender)]
		full_items = []
		for block in base_pkg.get("full_items", []) or []:
			items = _filter_items_by_gender(block.get("items", []), gender)
			if items:
				full_items.append({"category": block.get("category"), "items": items})
		pkg["full_items"] = full_items
		return [pkg]
	# 2) 若检测到同时含男女特异项目 -> 必须拆分
	if both_genders:
		result: List[Dict[str, Any]] = []
		for gender, zh in (("male", "男士"), ("female", "女士")):
			pkg = {**base_pkg}
			pkg["name"] = f"{base_pkg['name']}({zh})" if "(" not in base_pkg['name'] else base_pkg['name']
			pkg["code"] = f"{base_pkg['code']}_{'M' if gender=='male' else 'F'}"
			pkg["price"] = price.get("male") if isinstance(price, dict) and gender == "male" else (price.get("female") if isinstance(price, dict) else price)
			summary = base_pkg.get("summary_items") or []
			pkg["summary_items"] = [x["name"] for x in _filter_items_by_gender([{ "name": s } for s in summary], gender)]
			full_items = []
			for block in base_pkg.get("full_items", []) or []:
				items = _filter_items_by_gender(block.get("items", []), gender)
				if items:
					full_items.append({"category": block.get("category"), "items": items})
			pkg["full_items"] = full_items
			result.append(pkg)
		return result
	# 3) 无明显性别特征：若价格按男女区分，则按价格拆分（不过滤项目）；否则不拆分
	if isinstance(price, dict):
		candidates = [("male", "男士", price.get("male")), ("female", "女士", price.get("female"))]
		result: List[Dict[str, Any]] = []
		for gender, zh, pv in candidates:
			if pv is None:
				continue
			pkg = {**base_pkg}
			pkg["name"] = f"{base_pkg['name']}({zh})" if "(" not in base_pkg['name'] else base_pkg['name']
			pkg["code"] = f"{base_pkg['code']}_{'M' if gender=='male' else 'F'}"
			pkg["price"] = pv
			# 不过滤项目，因为并无性别特异项
			result.append(pkg)
		return result or [base_pkg]
	# 4) 其它情况：不拆分
	return [base_pkg]


@app.get("/recom/packages")
def list_packages():
	# 1) 从本地数据源加载（首次可从 reco 导出后即独立）
	base_list = load_packages()
	# 2) 不再从 taocan 合并，避免重复
	# 3) 按性别展开
	expanded: List[Dict[str, Any]] = []
	for pkg in base_list:
		expanded.extend(_expand_by_gender(pkg))
	return expanded

@app.get("/recom/packages/source")
def pkg_source():
	return {"source": "local packages.json (exportable from reco once) + expand_by_gender"}

@app.get("/recom/ui")
def recom_ui_removed():
	return {"message": "UI removed in recom2; use API only."}

@app.post("/api/v1/agents/package-recommendations", response_model=WebRecommendOut)
def package_recommendations(payload: WebRecommendIn) -> WebRecommendOut:
	"""
	体检套餐个性化推荐接口
	
	并发安全设计：
	1. 每次请求创建独立的Agent实例（无状态架构）
	2. 不同用户的请求完全隔离，线程安全
	3. 通过user_id区分用户，通过trace_id追踪请求
	
	用户区分机制：
	- payload.user_id: 业务层面的用户标识
	- trace_id: 系统生成的请求追踪ID（用于日志关联和问题排查）
	- timestamp: 请求时间戳
	
	RESTful设计：
	- 路径：/api/v1/agents/package-recommendations
	- 方法：POST
	- 返回标准格式：{trace_id, status, timestamp, data}
	"""
	import uuid
	from datetime import datetime
	
	# ✅ 并发安全关键：每次请求创建新的Agent实例
	# 优点：
	# - 完全无状态，支持水平扩展
	# - 避免多用户并发时的状态污染
	# - 每个请求独立处理，互不影响
	agent = create_recommendation_agent()
	
	# ✅ 参数校验（保证推荐质量）
	if payload.gender not in ["male", "female"]:
		return WebRecommendOut(
			trace_id=f"error_{uuid.uuid4().hex[:12]}",
			status="error",
			timestamp=datetime.now().isoformat(),
			data={"error": "性别参数错误，必须为 'male' 或 'female'"}
		)
	
	if not (0 < payload.age < 150):
		return WebRecommendOut(
			trace_id=f"error_{uuid.uuid4().hex[:12]}",
			status="error",
			timestamp=datetime.now().isoformat(),
			data={"error": "年龄参数错误，必须为 1-149 之间的整数"}
		)
	
	if payload.budget <= 0:
		return WebRecommendOut(
			trace_id=f"error_{uuid.uuid4().hex[:12]}",
			status="error",
			timestamp=datetime.now().isoformat(),
			data={"error": "预算参数错误，必须大于 0"}
		)
	
	# 构造用户画像数据
	# 注意：这里是请求级别的临时数据，不会持久化或跨请求共享
	user = {
		"age": payload.age,
		"gender": payload.gender,
		"budget": payload.budget,
		"purpose": payload.purpose or "常规体检",
		"health_concerns": payload.health_concerns or [],
		"family_history": payload.family_history or [],
		"lifestyle_factors": payload.lifestyle_factors or [],
	}
	
	# 调用推荐算法
	# agent.recommend_packages 是无状态函数，不会修改全局状态
	recs = agent.recommend_packages(user, top_n=payload.top_n or 3)
	
	# ✅ 返回标准化响应格式
	# 用户区分和追踪机制：
	# 1. trace_id: 本次请求的唯一标识（用于日志查询和问题定位）
	# 2. user_id: 原样返回，方便前端关联
	# 3. timestamp: 响应时间，便于性能分析
	return WebRecommendOut(
		trace_id=f"req_{uuid.uuid4().hex[:12]}",  # 生成12位唯一追踪ID
		status="success",
		timestamp=datetime.now().isoformat(),  # ISO 8601格式时间戳
		data={
			"user_id": payload.user_id,  # 返回用户ID用于前端关联
			"recommended": recs  # 推荐结果列表
		}
	)

@app.post("/api/v1/agents/qa", response_model=WebQAOut)
def qa(payload: WebQAIn) -> WebQAOut:
	"""
	问答接口 - 基于推荐结果回答用户问题
	
	功能说明：
	1. 接收用户问题和推荐结果上下文
	2. 调用qa.py中的answer_question函数
	3. 返回标准化的问答响应
	"""
	import uuid
	from datetime import datetime
	
	# 检测是否需要推荐上下文
	question_lower = payload.question.lower()
	requires_context_keywords = [
		"推荐", "为什么", "为啥", "套餐", "区别", "对比", 
		"哪个好", "选哪个", "怎么选", "更适合", "更好"
	]
	
	requires_context = any(kw in payload.question for kw in requires_context_keywords)
	has_context = payload.context and payload.context.get("recommended")
	
	# 如果问题需要推荐结果但没有提供，返回友好提示
	if requires_context and not has_context:
		return WebQAOut(
			trace_id=f"qa_{uuid.uuid4().hex[:12]}",
			status="success",
			timestamp=datetime.now().isoformat(),
			answer="您的问题需要基于推荐结果来回答。请先调用套餐推荐接口获取推荐结果，然后将结果作为 context 传入问答接口。\n\n调用流程：\n1. 先调用 /api/v1/agents/package-recommendations 获取推荐\n2. 保存返回的 data 字段\n3. 调用问答接口时将 data 作为 context 参数传入"
		)
	
	# 调用问答函数
	try:
		answer = answer_question(payload.context, payload.question)
		
		return WebQAOut(
			trace_id=f"qa_{uuid.uuid4().hex[:12]}",
			status="success",
			timestamp=datetime.now().isoformat(),
			answer=answer
		)
	except Exception as e:
		# 错误处理
		return WebQAOut(
			trace_id=f"qa_{uuid.uuid4().hex[:12]}",
			status="error",
			timestamp=datetime.now().isoformat(),
			answer=f"处理问题时出错: {str(e)}"
		)


@app.get("/health")
def health():
	return {"ok": True} 