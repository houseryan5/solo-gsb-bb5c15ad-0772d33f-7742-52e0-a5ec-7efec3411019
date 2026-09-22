# 多评委评分校准 Web 应用

上传含「选手 / 评委 / 项目 / 分数」的 CSV，系统按评委用 **中位数 + MAD（中位绝对偏差）** 做稳健标准化，
合成项目总分、识别标准化前后的**名次反转**；可逐项标记「保留原分 / 采用校准分」并填写理由，
排名实时重算，最后导出带审计明细的 CSV。

- 后端：FastAPI（纯 Python 标准库实现统计算法，无 numpy/pandas 依赖）
- 前端：原生 HTML / CSS / JavaScript（无构建步骤、无前端框架）
- 存储：**不使用任何数据库**，会话仅以单个 `session.json` 保存在 Docker 卷中，清空会话即删除

## 单条命令启动

```bash
docker compose up -d --build
```

启动后访问：

- 应用地址：<http://localhost:8000>
- 接口文档（Swagger）：<http://localhost:8000/docs>

停止与移除：

```bash
docker compose down            # 停止（数据卷保留）
docker compose down -v         # 停止并删除数据卷（彻底清空数据）
```

## 配置

通过环境变量 / `.env` 文件配置（均为可选项）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HOST_PORT` | `8000` | 宿主机映射端口，例如 `HOST_PORT=9000 docker compose up -d` |
| `DATA_DIR` | `/data` | 容器内会话文件目录（已挂载命名卷 `calibration-data`） |

自定义端口示例：

```bash
echo "HOST_PORT=9000" > .env
docker compose up -d --build
# 访问 http://localhost:9000
```

数据物理位置（Docker 管理的命名卷）：

```bash
docker volume inspect judge-calibration_calibration-data
```

## CSV 格式

UTF-8（带 BOM 亦可）或 GB18030 编码，必需四列，表头支持中英文：

| 中文表头 | 英文别名 | 含义 |
| --- | --- | --- |
| 选手 | `contestant` / `name` | 选手姓名或编号 |
| 评委 | `judge` | 评委姓名或编号 |
| 项目 | `project` / `event` | 比赛项目 |
| 分数 | `score` / `points` | 数值打分 |

每行是「某评委给某选手在某项目上的一个分数」（长表）。同一选手/评委/项目重复、分数非数字、
缺列等情况会返回明确的中文错误提示，不会写入数据。

页面点「下载示例 CSV」可获取示例数据（5 名选手 × 4 名评委 × 3 个项目，
内含因评委宽严不一与偏好打分造成的名次反转）。

## 校准方法

对每位评委的所有打分：

```
median  = 中位数
MAD     = median(|x − median|)
robust_z = 0.6745 × (x − median) / MAD
校准分   = 全体分数中位数 + (全体MAD / 0.6745) × robust_z
```

- 校准分映射回原始分量纲，可直接与原分对照；
- 当某评委半数以上打分相同导致 `MAD = 0` 时，自动退化为**样本标准差**（页面与导出中标注「标准差(MAD=0退化)」）；
- 该评委打分完全无差异时 z 分记为 0；
- 项目总分 = 各评委分数的**均值**；总评总分 = 各项目总分之和；
- 名次采用标准竞赛排名（并列同名次，1、1、3 名）。

## 页面功能

1. **上传 CSV / 下载示例 / 导出审计 CSV / 清空会话**
2. **概览**：选手、评委、项目、评分项数量与反转对数
3. **名次反转**：列出所有校准前后领先关系对调的选手对（项目内与总评两个范围）
4. **评委校准参数**：每位评委的中位数、MAD、均值、标准差、实际使用尺度
5. **项目排名 / 总评排名**：并列展示原分、校准分、生效分三套分数与名次，原名次→生效名次的进退用 ▲▼ 标注，涉及反转的行高亮
6. **逐项裁决**：对每个评分切换「校准分 / 原分」并填写理由，保存后全部排名**实时重算**；支持项目筛选、姓名搜索、一键全部校准 / 全部原分

裁决默认采用校准分；重新上传数据时，键值（选手|项目|评委）仍存在的旧裁决与理由会保留。

## 导出审计 CSV

`GET /api/export`（页面「导出审计 CSV」按钮）下载 UTF-8 BOM 编码的 `audit_calibration.csv`：

- 主表每行一个评分项：原始分、稳健 Z、校准分、生效分、采用方式、理由、与原分差，
  并冗余该选手该项目三套均分/名次与反转标记、总评三套总分/名次与反转标记、该评委的中位数/MAD/尺度；
- 附页 1「名次反转审计」：每一对反转的原分领先者、校准后领先者及双向分差；
- 附页 2「评委分布参数」：每位评委的分布统计与退化策略标注。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/state` | 当前会话与全部计算结果 |
| POST | `/api/upload` | 上传 CSV（multipart 字段 `file`） |
| PUT | `/api/decisions` | 批量提交逐项裁决 `{decisions: {"选手|项目|评委": {mode, reason}}}` |
| PUT | `/api/decisions/bulk` | 一键设置全部项 `{mode: "raw" | "calibrated"}` |
| GET | `/api/export` | 下载审计 CSV |
| GET | `/api/sample` | 下载示例 CSV |
| DELETE | `/api/session` | 清空会话（删除数据卷中的 session.json） |
| GET | `/api/health` | 健康检查 |

## 本地开发（不用 Docker）

需要 Python 3.11+：

```bash
pip install -r requirements.txt
DATA_DIR=./data uvicorn app.main:app --reload --port 8000
```

重新生成示例数据：

```bash
python scripts/gen_sample.py
```

## 目录结构

```
├── app/
│   ├── main.py          # FastAPI 路由
│   ├── calibration.py   # CSV 解析、MAD 稳健标准化、排名与反转
│   ├── storage.py       # 数据卷 JSON 会话持久化
│   ├── export.py        # 审计 CSV 导出
│   ├── sample_data.csv  # 内置示例数据
│   └── static/          # 原生 JS 前端（index.html / app.js / styles.css）
├── scripts/gen_sample.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```
