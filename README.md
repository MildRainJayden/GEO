# AI Visibility China (AIVC)

中国 AI 搜索可见度与 GEO（Generative Engine Optimization）优化平台 MVP。

当前版本可以在没有真实模型 API Key 的情况下运行完整闭环：自动补全品牌信息、自动生成中文问题、调用统一 Provider、分析品牌提及、评分、引用来源、竞品矩阵、内容缺口、GEO 建议、推荐概率和 30 天执行计划，并输出 JSON / HTML / PDF 报告。

## 快速开始

```powershell
$PY="C:\Users\Rain\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $PY -m backend.aivc.cli --brand 美的 --providers deepseek --output-dir outputs-midea
& $PY -m backend.aivc.app
```

打开 `http://127.0.0.1:8000` 后即可用内置 Nike 示例测试。

## 接入真实 API

不要把 API Key 写入代码或提交到 Git。复制 `.env.example` 为 `.env`，按需填写一个或多个平台：

```env
GPT_API_KEY=
GPT_BASE_URL=https://api.openai.com/v1
GPT_MODEL=gpt-4.1-mini

DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus

DOUBAO_API_KEY=
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=doubao-seed-1-6-250615

MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimax.chat/v1
MINIMAX_MODEL=MiniMax-M1
```

只用 DeepSeek 跑美的：

```powershell
$PY="C:\Users\Rain\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $PY -m backend.aivc.cli --brand 美的 --providers deepseek --output-dir outputs-midea
```

指定多个真实平台：

```powershell
& $PY -m backend.aivc.cli --brand 美的 --providers gpt,deepseek,doubao,minimax,qwen --output-dir outputs-real
```

API 调用时可以指定：

```json
{
  "brand_name": "Nike",
  "providers": ["deepseek"]
}
```

新增 OpenAI-compatible 平台不需要改代码，可以在 `.env` 放：

```env
AIVC_OPENAI_COMPATIBLE_PROVIDERS=[{"name":"my-provider","api_key_env":"MY_PROVIDER_API_KEY","base_url":"https://api.example.com/v1","model":"model-name"}]
MY_PROVIDER_API_KEY=
```

## API

- `POST /audit`：创建并执行测评
- `GET /audit/{id}`：获取任务状态
- `GET /audit/{id}/result`：获取结果 JSON
- `GET /audit/{id}/report`：获取 HTML 报告
- `POST /compare`：生成竞品矩阵
- `POST /optimize`：生成 GEO 建议
- `POST /content/generate`：生成可复制内容
- `GET /openapi.json`：OpenAPI 摘要

示例请求：

```json
{
  "brand_name": "Nike",
  "website": "https://www.nike.com",
  "industry": "运动服饰",
  "products": ["运动鞋", "运动服饰", "跑步装备"],
  "competitors": ["Adidas", "Puma", "Under Armour", "安踏", "李宁"],
  "question_count": 60
}
```

## 目录

```text
backend/aivc/
  api/                 标准库 HTTP API
  providers/           统一 Provider 接口与 gpt/deepseek/doubao/minimax/qwen
  analysis/            提及、评分、引用、竞品、GEO 分析
  services/            审计编排服务
  report/              HTML / PDF 报告
frontend/static/       本地可用的单页界面
tests/                 unittest 闭环测试
```

## 后续接入真实模型

每个 Provider 都实现 `ProviderClient.query(question, brand)`。新增真实 API 时，保留统一返回 `ProviderResponse` 即可；没有官方 API 的平台可以在对应模块中接 Playwright 自动化。
