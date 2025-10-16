from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Any, Dict

from .recommendation_agent import create_recommendation_agent
from .data import load_packages
import os
from pathlib import Path
try:
	from dotenv import load_dotenv  # type: ignore
	load_dotenv(dotenv_path=Path(__file__).parent / "config" / ".env")
except Exception:
	# 未安装或未找到 .env 不影响运行
	pass

app = FastAPI(title="体检套餐推荐系统", version="1.0.0")

class WebRecommendIn(BaseModel):
	user_id: str  # 用户唯一标识（必填）- 用于区分不同用户请求
	age: Optional[int] = None
	gender: Optional[str] = None  # male/female/None
	budget: Optional[float] = None
	purpose: Optional[str] = None
	health_concerns: Optional[List[str]] = None
	family_history: Optional[List[str]] = None
	lifestyle_factors: Optional[List[str]] = None
	top_n: int = 3

class WebRecommendOut(BaseModel):
	trace_id: str  # 请求追踪ID - 用于问题排查和日志关联
	status: str  # 状态：success/error
	timestamp: str  # 响应时间戳 - 便于调试
	data: dict  # 实际数据（包含user_id和recommended）

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
	if gender not in ("male", "female"):
		return items
	filtered: List[Dict[str, Any]] = []
	for it in items:
		name = str(it.get("name", ""))
		is_female = any(k in name for k in FEMALE_KW)
		is_male = any(k in name for k in MALE_KW)
		if gender == "male":
			if is_female and not is_male:
				continue
		else:
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
	
	改动说明：
	1. 路径改为RESTful风格：/api/v1/agents/package-recommendations
	2. 每次创建新Agent：解决多用户并发冲突
	3. 返回标准格式：包含trace_id、timestamp等追踪信息
	"""
	import uuid
	from datetime import datetime
	
	# ✅ 关键改动：每次请求创建新Agent，避免状态共享
	agent = create_recommendation_agent()
	
	# 构造用户信息
	user = {
		"age": payload.age or 0,
		"gender": payload.gender or "male",
		"budget": payload.budget or 0,
		"purpose": payload.purpose or "常规体检",
		"health_concerns": payload.health_concerns or [],
		"family_history": payload.family_history or [],
		"lifestyle_factors": payload.lifestyle_factors or [],
	}
	
	# 调用推荐算法
	recs = agent.recommend_packages(user, top_n=payload.top_n or 3)
	
	# ✅ 返回标准化格式
	return WebRecommendOut(
		trace_id=f"req_{uuid.uuid4().hex[:12]}",  # 生成唯一追踪ID
		status="success",
		timestamp=datetime.now().isoformat(),  # ISO 8601格式时间
		data={
			"user_id": payload.user_id,
			"recommended": recs
		}
	)

# QA/流式等演示接口在对接版本中移除，仅保留推荐API与健康检查


@app.get("/health")
def health():
	return {"ok": True} 