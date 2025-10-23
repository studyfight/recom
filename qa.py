from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os
import json
from pathlib import Path

# 轻量问答引擎：优先尝试调用大模型；缺省走规则兜底，保证离线可跑

# ========== 加载医院体检注意事项（从JSON配置文件） ==========
def _load_hospital_notice() -> str:
	"""从JSON配置文件加载医院注意事项
	
	优先从 config/hospital_notice.json 加载，失败则使用默认值
	"""
	try:
		config_path = Path(__file__).parent / "config" / "hospital_notice.json"
		if config_path.exists():
			with open(config_path, "r", encoding="utf-8") as f:
				data = json.load(f)
				content = data.get("content", "")
				
				# 如果是数组，用换行符连接；如果是字符串，直接返回
				if isinstance(content, list):
					return "\n".join(content)
				else:
					return content
	except Exception as e:
		print(f"Warning: 加载医院通知配置失败: {e}")
	
	# 默认值
	return "【体检注意事项】\n请咨询体检中心了解详细信息。"

# 加载医院通知（模块级别，只加载一次）
HOSPITAL_NOTICE = _load_hospital_notice()

# ========== 加载完整套餐库（第二层上下文） ==========
def _load_all_packages() -> str:
	"""加载完整套餐库作为第二层上下文
	
	用于回答推荐外的套餐查询，例如“还有什么其他套餐”
	"""
	try:
		from recom2.data import load_packages
		packages = load_packages()
		
		if not packages:
			return ""
		
		# 格式化所有套餐信息（简略版）
		lines = ["【完整套餐库】", ""]
		for pkg in packages:
			name = pkg.get("name", "")
			price = pkg.get("price", 0)
			summary = pkg.get("summary_items", [])
			lines.append(f"{name}(￥{price})：{', '.join(summary[:5])}...")
		
		return "\n".join(lines)
	except Exception as e:
		print(f"Warning: 加载完整套餐库失败: {e}")
		return ""

# 加载完整套餐库（模块级别，只加载一次）
ALL_PACKAGES_CONTEXT = _load_all_packages()

SYSTEM_PROMPT = os.getenv("LLM_SYSTEM_PROMPT", (
	"你是专业的体检套餐顾问，请用通俗易懂的语言回答用户问题。\n\n"
	"回答要求：\n"
	"1. 内容要丰富详细，每个要点展开说明（为什么重要、有什么作用、如何理解）\n"
	"2. 适当补充医学背景知识，帮助用户理解，但用白话解释专业术语\n"
	"3. 给出具体的、可操作的建议，不要泛泛而谈\n"
	"4. 结构清晰，使用小标题分段：【结论】【对比】【补充建议】【项目解释】等\n"
	"5. 语言风格口语化、亲切，像医生面对面讲解\n\n"
	"格式要求：\n"
	"- 不要使用markdown格式符号（如**加粗**、*斜体*），直接用文字表达\n"
	"- 可以用数字序号(1. 2. 3.)、短横线(-)来列点，保持简洁\n"
	"- 少用emoji表情符号，只在必要时用简单的符号(如√ ×)\n"
	"- 表格可以用简单的文字列表代替，更易阅读\n\n"
	"严格要求：\n"
	"- 不编造上下文中未出现的价格、项目、数据\n"
	"- 不确定的信息明确说明'根据现有信息无法确定'\n"
	"- 不夸大项目效果，保持客观中立\n"
))

# ---- 工具：按小标题过滤段落 ----

def _filter_sections(text: str, allowed_titles: List[str]) -> str:
	"""过滤输出，只保留指定的小标题部分（支持emoji + 【】格式）"""
	if not text:
		return text
	lines = text.splitlines()
	keep: List[str] = []
	allow = False
	# 兼容新旧格式：【标题】或 emoji **标题**
	allowed_patterns = []
	for t in allowed_titles:
		allowed_patterns.append(f"【{t}】")
		allowed_patterns.append(f"**{t}**")
		# 还支持emoji开头的标题，例如 💡 核心结论
		if t in ["结论", "核心结论", "对比", "详细对比", "项目解释", "项目解读", "体检前注意", "注意事项"]:
			allowed_patterns.append(t)
	
	for ln in lines:
		stripped = ln.strip()
		# 检测是否是标题行
		is_title = False
		if any(stripped.startswith(p) or p in stripped for p in allowed_patterns):
			allow = True
			is_title = True
		# 如果遇到新的markdown标题或分隔线，可能是新章节
		elif stripped.startswith("#") or stripped.startswith("---") or (stripped.startswith("**") and stripped.endswith("**")):
			# 检查是否是允许的标题
			if not any(p in stripped for p in allowed_patterns):
				allow = False
			else:
				allow = True
				is_title = True
		
		if allow:
			keep.append(ln)
	
	return "\n".join(keep).strip() or text

# ---- 基础知识：常见体检项目解释（可扩展） ----
ITEM_EXPLAINS: Dict[str, str] = {
	"糖化血红蛋白": "反映近2-3个月平均血糖控制，糖尿病筛查与管理的重要指标。",
	"HbA1c": "反映近2-3个月平均血糖控制，糖尿病筛查与管理的重要指标。",
	"CA19-9": "消化道（胰腺/胆道等）相关肿瘤标志物，联合其他检查用于风险提示，不能单独诊断。",
	"CA-19-9": "消化道（胰腺/胆道等）相关肿瘤标志物，联合其他检查用于风险提示，不能单独诊断。",
	"CA-125": "卵巢等来源的肿瘤相关肿瘤标志物，常用于女性生殖系统肿瘤风险提示与随访，需结合影像与临床。",
	"CA125": "卵巢等来源的肿瘤相关肿瘤标志物，常用于女性生殖系统肿瘤风险提示与随访，需结合影像与临床。",
	"CA-15-3": "乳腺癌相关肿瘤标志物之一，主要用于乳腺癌患者随访与疗效监测，不用于单独筛查与诊断。",
	"CA153": "乳腺癌相关肿瘤标志物之一，主要用于乳腺癌患者随访与疗效监测，不用于单独筛查与诊断。",
	"TPSA": "前列腺特异性抗原（总），前列腺疾病筛查辅助指标，需结合FPSA及临床。",
	"FPSA": "前列腺特异性抗原（游离），与TPSA联合评估前列腺风险。",
	"甲胎蛋白": "AFP，肝细胞癌等相关肿瘤标志物，需结合影像与其他指标判读。",
	"癌胚抗原": "CEA，多种肿瘤相关非特异标志物，用于风险提示与随访，不作单独诊断。",
	"甲功三项": "甲状腺功能（如TSH/FT3/FT4），用于评估甲状腺功能亢进或减退。",
	"生化26项": "较全面的代谢/肝肾功能/电解质等检测，用于全身代谢与脏器功能评估。",
	"颈动脉超声": "评估颈动脉斑块与狭窄，提示脑卒中等心脑血管风险。",
	"乳腺超声": "无辐射检查乳腺结构与结节，对育龄女性友好。",
	"子宫及附件超声": "妇科超声，评估子宫与卵巢结构，发现囊肿/肌瘤等。",
	"前列腺超声": "评估前列腺体积与结构，辅助前列腺疾病筛查。",
	"骨密度": "评估骨质疏松风险，常用于中老年或绝经后女性。",
	"胸部CT": "低剂量辐射胸部断层成像，较胸片更敏感，用于肺部结节等筛查。",
	"胸片": "常规胸部平片，辐射更低，敏感性较CT低。",
	"心电图": "评估心律与心肌供血情况，筛查心脏节律与缺血问题。",
	"动态血压": "24小时动态血压监测，评估隐匿性高血压与昼夜节律。",
	"14-C呼气试验": "幽门螺杆菌检测的无创方法，阳性提示感染，需医生评估是否治疗。",
	"13-C呼气试验": "幽门螺杆菌检测的无创方法，阳性提示感染，需医生评估是否治疗。",
}

# ---- 体检前注意事项（通用+专项） ----
GENERAL_NOTES: List[str] = [
	"体检前8小时避免进食，体检当天早晨空腹，不饮茶咖啡与酒精。",
	"体检前1-3天清淡饮食，避免高脂高糖与剧烈运动，保证充足睡眠。",
	"例假期间不做妇科检查与尿检（可改期），怀孕或备孕请事先告知。",
	"随身携带身份证件，体检当日提前15分钟到达体检中心。",
]
SPECIAL_NOTES: Dict[str, List[str]] = {
	"胃镜": ["前晚22点后禁食水，遵医嘱停抗凝/降糖药，随行家属更安心。"],
	"结肠镜": ["前一日流食并按医嘱口服泻剂清肠，检查当日禁食。"],
	"胸部CT": ["避免佩戴金属饰品，配合屏气；有妊娠可能者先与医生沟通。"],
	"乳腺超声": ["尽量避开经期前后乳房胀痛期，放松配合检查。"],
	"TCT": ["采样前48小时避免性生活与阴道用药/冲洗，月经期不做。"],
	"HPV": ["采样前48小时避免性生活与阴道用药/冲洗，月经期不做。"],
	"动态血压": ["佩戴期间按日常作息，避免剧烈运动与水浸，记录用药与症状。"],
	"14-C呼气试验": ["检测前2周停用抗生素/抑酸剂，前1天避免酒精与辛辣。"],
	"13-C呼气试验": ["检测前2周停用抗生素/抑酸剂，前1天避免酒精与辛辣。"],
}


def _contains_any(text: str, keywords: List[str]) -> bool:
	lower = text.lower()
	return any(k.lower() in lower for k in keywords)


def _format_bullets(lines: List[str]) -> str:
	return "\n".join([f"- {line}" for line in lines])


def _norm(s: str) -> str:
	"""去除非字母数字，统一小写，用于鲁棒匹配（e.g. CA153/CA-15-3）。"""
	return "".join(ch.lower() for ch in s if ch.isalnum())


def _summarize_packages(pkgs: List[Dict[str, Any]], top_n: int = 3) -> Tuple[str, List[str]]:
	"""生成对比用的简要上下文与亮点要点列表。
	
	✅ 兼容两种数据格式：
	1. 直接格式：{"name": "xx", "price": 100, "score": 1.5, ...}
	2. 嵌套格式：{"package_name": "xx", "package_info": {"name": "xx", "price": 100}, "score": 1.5, ...}
	"""
	if not pkgs:
		return "", []
	pkgs = pkgs[:top_n]
	rows = []
	highlights: List[str] = []
	
	for p in pkgs:
		# ✅ 兼容两种格式
		package_info = p.get("package_info", {})
		
		# 优先从 package_info 中取，其次直接从 p 中取
		name = package_info.get("name") or p.get("package_name") or p.get("name") or "未知套餐"
		price = package_info.get("price") or p.get("price") or 0
		score = p.get("score") or 0
		
		# 亮点/标签：优先从 package_info，其次从 p
		diff = (package_info.get("highlights_parsed") or 
		        package_info.get("diff_items") or 
		        p.get("diff_items") or 
		        p.get("filtered_key_features") or [])
		
		tags = (package_info.get("tags") or 
		        p.get("tags") or [])
		
		# 推荐理由：优先从 p，其次从 package_info
		reason = (p.get("recommendation_reason") or 
		          p.get("reason") or 
		          package_info.get("recommendation_reason") or 
		          package_info.get("reason") or "")
		
		# 格式化输出
		diff_str = ', '.join(diff[:3]) if diff else '-'  # 只显示前3个亮点
		tags_str = ', '.join(tags[:3]) if tags else '-'  # 只显示前3个标签
		reason_str = reason[:100] + '...' if len(reason) > 100 else reason  # 理由截断
		
		rows.append(f"{name}｜￥{price}｜分数{score:.2f}｜亮点：{diff_str}｜标签：{tags_str}｜理由：{reason_str}")
		
		if diff:
			highlights.extend(diff)
	
	ctx = "\n".join(rows)
	return ctx, list(dict.fromkeys(highlights))


def _explain_item_by_rules(question: str) -> Optional[str]:
	q_norm = _norm(question)
	for key, val in ITEM_EXPLAINS.items():
		if key.lower() in question.lower() or _norm(key) in q_norm:
			return f"【项目解释】{key}：{val}"
	return None


def _notes_from_context(highlights: List[str]) -> List[str]:
	notes = list(GENERAL_NOTES)
	for k, v in SPECIAL_NOTES.items():
		if any(k.lower() in h.lower() for h in highlights):
			notes.extend(v)
	return list(dict.fromkeys(notes))


def _has_llm() -> bool:
	return bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY_1") or os.getenv("BAILIAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY"))


def _llm_only() -> bool:
	return str(os.getenv("LLM_ONLY", "")).lower() == "true"


def _debug_wrap(text: str, source: str) -> str:
	if str(os.getenv("LLM_DEBUG", "")).lower() == "true":
		return f"[{source}]\n" + text
	return text


def _try_llm(prompt: str) -> Optional[str]:
	"""尝试调用环境可用的大模型。优先：百炼原生（LangChain ChatTongyi -> dashscope）；
	失败再退回 OpenAI 兼容端点。
	支持的环境变量：
	- BAILIAN_API_KEY / DASHSCOPE_API_KEY
	- LLM_MODEL（或 OPENAI_MODEL 兼容）
	- LLM_BASE_URL / OPENAI_BASE_URL（仅用于兼容端点）
	"""
	model_name = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL", "qwen-plus")
	bailian_key = os.getenv("BAILIAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
	if bailian_key:
		# 1) 优先使用 LangChain ChatTongyi（多数环境已安装）
		try:
			from langchain_community.chat_models import ChatTongyi  # type: ignore
			from langchain_core.messages import SystemMessage, HumanMessage  # type: ignore
			llm = ChatTongyi(model=model_name, api_key=bailian_key)
			resp = llm.invoke([SystemMessage(content="你是专业的体检套餐顾问。回答要详细丰富，每个要点展开说明，用通俗语言解释医学概念。"), HumanMessage(content=prompt)])
			text = getattr(resp, "content", None)
			if text:
				return text
		except Exception:
			pass
		# 2) 尝试阿里官方 dashscope SDK（若环境已安装）
		try:
			from dashscope import Generation  # type: ignore
			result = Generation.call(model=model_name, prompt=prompt, api_key=bailian_key)
			# 不同版本SDK字段不同，做尽量宽松的兼容
			if result is not None:
				if hasattr(result, "output_text") and result.output_text:
					return result.output_text  # type: ignore
				out = getattr(result, "output", None)
				if out:
					text = getattr(out, "text", None) or getattr(out, "choices", [{}])[0].get("message", {}).get("content")
					if text:
						return text
		except Exception:
			pass
	# 3) 回退到 OpenAI 兼容端点
	api_key = (
		os.getenv("OPENAI_API_KEY")
		or os.getenv("OPENAI_API_KEY_1")
		or bailian_key  # 允许用百炼key走兼容端点
	)
	if not api_key:
		return None
	base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ("https://dashscope.aliyuncs.com/compatible-mode/v1" if bailian_key else None)
	try:
		from openai import OpenAI  # type: ignore
		client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
		resp = client.chat.completions.create(
			model=model_name,
			messages=[
				{"role": "system", "content": "你是专业的体检套餐顾问。回答要详细丰富，每个要点展开说明，用通俗语言解释医学概念。"},
				{"role": "user", "content": prompt},
			],
			temperature=0.3,  # 稍微提高temperature让回答更丰富
		)
		return resp.choices[0].message.content  # type: ignore
	except Exception:
		return None


def _classify_question(question: str) -> str:
	"""【极简版】判断问题是否在三层上下文范围内
	
	三层上下文:推荐结果 + 完整套餐库 + 医院注意事项
	
	返回值:
	- 'related': 与体检/套餐/医院相关 (都可以回答)
	- 'out_of_scope': 明显无关的问题
	"""
	q_lower = question.lower()
	
	# 宽泛匹配: 只要和体检/套餐/医院相关, 都认为在范围内
	related_keywords = [
		# 体检相关
		"体检", "检查", "检测", "筛查",
		# 套餐相关
		"套餐", "推荐", "选", "项目", "包含", "比较", "价格", "费用", "多少钱",
		# 医院相关
		"医院", "体检中心", "地址", "位置", "怎么走", "在哪",
		# 注意事项
		"注意", "准备", "空腹", "须知", "禁食",
		# 健康相关
		"症状", "疾病", "风险", "健康", "指标",
		# 其他
		"适合", "理由", "为什么", "哪个", "怎么",
	]
	
	if _contains_any(q_lower, related_keywords):
		return 'related'
	
	# 其他问题 (明显无关)
	return 'out_of_scope'


def _detect_scope(question: str, has_recommendation: bool) -> str:
	"""判断用户问的是推荐结果还是其他套餐
	
	返回值:
	- 'recommendation': 问的是推荐结果
	- 'other_packages': 问的是其他套餐
	- 'unclear': 不明确,需要根据上下文判断
	"""
	q_lower = question.lower()
	
	# 1. 明确说明想看其他/更多套餐
	other_keywords = [
		"还有什么", "还有哪些", "其他套餐", "更多套餐", 
		"除了这些", "除此之外", "别的套餐",
		"推荐其他", "推荐更多", "补充推荐"
	]
	if _contains_any(q_lower, other_keywords):
		return 'other_packages'
	
	# 2. 指代词: "这些"/"它们"/"这几个" -> 推荐结果
	recommendation_pronouns = [
		"这些套餐", "这些", "它们", "这几个", 
		"上面的", "上述", "以上",
		"给我推荐的", "你推荐的"
	]
	if _contains_any(q_lower, recommendation_pronouns) and has_recommendation:
		return 'recommendation'
	
	# 3. 默认策略: 如果有推荐结果,默认问的是推荐结果
	if has_recommendation:
		return 'recommendation'
	
	# 4. 没有推荐结果,返回不明确(应该提示用户先生成推荐)
	return 'unclear'


def _build_guide_by_type(question_type: str) -> Optional[str]:
	"""【极简版】根据问题类型生成引导词
	
	返回None表示不回答(out_of_scope)
	"""
	
	if question_type == 'related':
		# 三层上下文相关问题: 用通用思考链引导词
		return (
			"请基于上下文灵活回答用户问题:\n\n"
			
			"⚠️ 关键提醒: 当用户说'这些套餐''它们''这几个'时,指的是'推荐结果'里的套餐,不是完整套餐库!\n\n"
			
			"第一步: 判断用户想了解什么(心里思考,不要输出)\n"
			"- 套餐推荐理由? 项目列表? 比较选择? 价格信息?\n"
			"- 体检注意事项? 医院位置? 其他相关信息?\n\n"
			
			"第二步: 选择最合适的回答方式\n"
			"- 问'为什么推荐/理由': 直接解释推荐结果里每个套餐匹配的需求点\n"
			"- 问'有哪些项目/包含什么': 按类别列举推荐结果里的项目\n"
			"- 问'比较/选哪个/哪个更好': 使用【结论】【对比】三段式,对比推荐结果里的套餐\n"
			"- 问'价格/多少钱': 直接列出推荐结果里的套餐价格\n"
			"- 问'还有什么其他套餐': 这时才使用完整套餐库推荐更多选择\n"
			"- 问'医院位置/地址/怎么走': 根据医院注意事项回答\n"
			"- 问'注意事项/准备/空腹': 根据医院注意事项回答\n\n"
			
			"【关键原则】\n"
			"- 优先使用'第一层:推荐结果',只有问'还有其他套餐'才用第二层\n"
			"- 紧扣用户问题,不要答非所问\n"
			"- 只在需要对比选择时才用固定结构\n"
			"- 回答要详细充实,但形式灵活\n"
			"- 如果上下文中没有相关信息,明确说明'无法根据现有信息回答'\n"
			"- 不要编造上下文中没有的信息\n"
		)
	
	else:  # out_of_scope
		return None


def build_prompt(question: str, context_text: str) -> str:
	"""【混合方案】构建问答提示词
	
	✅ 自动包含三层上下文：
	1. 第一层：推荐结果（context_text）
	2. 第二层：完整套餐库（ALL_PACKAGES_CONTEXT）
	3. 第三层：医院注意事项（HOSPITAL_NOTICE）
	
	✅ 混合方案：
	- 明确的问题类型（推荐理由、项目列表、比较选择等）→ 使用精准引导词（方案一）
	- 不明确的问题（general）→ 使用思考链引导词（方案二）
	"""
	# ✅ 构建完整三层上下文 (注明优先级)
	full_context_parts = []
	
	# 第一层: 推荐结果 (最高优先级)
	if context_text:
		full_context_parts.append(
			"【第一层上下文: 推荐结果】\n"
			"⚠️ 重要: 当用户说'这些套餐''它们'时,指的是下面这些推荐结果,不是完整套餐库!\n\n"
			f"{context_text}"
		)
	
	# 第二层: 完整套餐库 (仅当问'还有什么其他套餐'时使用)
	if ALL_PACKAGES_CONTEXT:
		full_context_parts.append(
			"【第二层上下文: 完整套餐库】\n"
			"⚠️ 仅当用户明确问'还有什么其他套餐'时才使用这层!\n\n"
			f"{ALL_PACKAGES_CONTEXT}"
		)
	
	# 第三层: 医院注意事项
	if HOSPITAL_NOTICE:
		full_context_parts.append(
			"【第三层上下文: 医院注意事项】\n"
			f"{HOSPITAL_NOTICE}"
		)
	
	full_context = "\n\n".join(full_context_parts)
	
	# ✅ 混合方案：先分类，再生成对应的引导词
	question_type = _classify_question(question)
	guide = _build_guide_by_type(question_type)
	
	# 通用回答要求
	common_requirements = (
		"\n【回答要求】\n"
		"- 优先使用'推荐结果'回答,只有问'还有其他套餐'时才用完整套餐库\n"
		"- 回答要充实详细，每个要点都要展开说明\n"
		"- 用简洁的文字表达，不要使用过多markdown符号或emoji\n"
		"- 不要编造上下文中未出现的信息\n"
	)
	
	# 可选：添加问题类型标记（用于调试和日志）
	if str(os.getenv("QA_DEBUG", "")).lower() == "true":
		common_requirements = f"\n[问题类型: {question_type}]{common_requirements}"
	
	return f"【系统提示】\n{SYSTEM_PROMPT}\n\n{full_context}\n\n【问题】{question}\n\n{guide}{common_requirements}"


def answer_question(last_result: Optional[Dict[str, Any]], question: str) -> str:
	"""【极简版】对外主函数: 基于last_result上下文回答
	
	只要问题在三层上下文范围内(套餐+医院+健康),都回答。超出范围才拒绝。
	"""
	if not question or not question.strip():
		return "请先输入问题。"
	
	# ✅ 先判断问题类型
	question_type = _classify_question(question)
	
	# ✅ 如果是超出范围的问题，直接返回友好提示
	if question_type == 'out_of_scope':
		return (
			"抱歉，我只能回答与体检套餐和医院相关的问题：\n\n"
			"1. 套餐相关：推荐理由、检查项目、比较选择、价格等\n"
			"2. 医院相关：体检前注意事项、医院位置、交通信息等\n"
			"3. 健康相关：症状、疾病、风险等与体检相关的问题\n\n"
			"如有其他问题，请咨询体检中心工作人员。"
		)

	# 从推荐结果提取候选作为上下文
	recommended: List[Dict[str, Any]] = []
	candidates: List[Dict[str, Any]] = []
	if last_result:
		recommended = last_result.get("recommended") or []
		candidates = last_result.get("candidates") or recommended or []
	pkgs_for_ctx = recommended or candidates
	
	# ✅ 检测用户意图: 问的是推荐结果还是其他套餐
	scope = _detect_scope(question, has_recommendation=bool(pkgs_for_ctx))
	
	# ✅ 如果没有推荐结果,但用户想问推荐结果,给出提示
	if scope == 'unclear':
		return (
			"我注意到当前还没有生成推荐结果。\n\n"
			"请您先在上方'推荐系统'中填写您的信息：\n"
			"1. 基本信息：性别、年龄、预算\n"
			"2. 健康关注：症状、家族病史等\n\n"
			"生成推荐后，再来这里问我任何问题！"
		)
	
	# ✅ 如果用户问的是其他套餐
	if scope == 'other_packages':
		return (
			"感谢您的问题！您想了解更多其他套餐。\n\n"
			"建议您：\n"
			"1. 调整上方'推荐系统'中的选项（如预算、关注点等）\n"
			"2. 重新生成推荐，系统会给出不同的套餐选择\n\n"
			"或者直接咨询体检中心工作人员，他们会给您更多建议。"
		)
	
	ctx_text, ctx_highlights = _summarize_packages(pkgs_for_ctx, top_n=3)

	# ✅ 相关问题: 调用大模型回答
	if _has_llm():
		llm_resp = _try_llm(build_prompt(question, ctx_text))
		if llm_resp:
			return _debug_wrap(llm_resp, "LLM")
		if _llm_only():
			return "当前大模型未可用或响应为空，请检查 Key/模型名/网络。"
	
	# 简单规则回退
	return "抱歉，当前无法回答该问题。请稍后重试或咨询体检中心工作人员。" 