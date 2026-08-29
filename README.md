# tomato-AI-Tarot

基于 LLM 的高级神秘塔罗牌占卜

## 安装

```bash
pip install -r requirements.txt
```

默认走本机 [Ollama](https://ollama.com/)  
也可以把 `TAROT_PROVIDER` 设为 `openai`，接入任何 OpenAI 兼容服务

## 运行

复制 `.env.example` 为 `.env` 后按需改地址和 key，再运行：

```bash
python example.py
python example.py -q "我该不该换工作？" --astrology
python example.py --provider openai --url https://api.deepseek.com/v1 --model deepseek-chat
```

命令行参数会覆盖 `.env`

| 参数 | 环境变量 | 默认值 | 含义 |
| --- | --- | --- | --- |
| `-q / --question` |  | `我的重复梦境试图传达什么` | 要占卜啥内容 |
| `--provider` | `TAROT_PROVIDER` | `ollama` | `ollama` 或 `openai` |
| `--url` | `TAROT_URL` | `localhost:11434` | 服务地址 |
| `--model` | `TAROT_MODEL` | `llama3.1:latest` | 文本模型 |
| `--api-key` | `TAROT_API_KEY` | 空 | OpenAI 兼容服务的 key；也可读 `OPENAI_API_KEY` |
| `--astrology` |  | 关 | 塔罗 + 占星 |
| `--card-select` |  | `0` | `0` 全牌 / `1` 大阿尔卡那 / `2` 小阿尔卡那 |
| `-o` |  | `output.png` | 牌阵图输出路径 |

其它环境变量（无对应 CLI）：

| 环境变量 | 默认值 | 含义 |
| --- | --- | --- |
| `TAROT_MAJOR_ARCANA_MAX_ID` | `21` | 大阿尔卡那最大 `id` |
| `TAROT_ZODIAC_KEYS` | 十二星座英文名，逗号分隔 | 以太元素展开用的星座 key |
| `TAROT_NAME_SUFFIXES` | `牌阵,展开法,展开,阵列` | 选阵时从中文名剥掉的后缀 |

牌阵与卡图配置见 `tarot_config.py`、`tarot_all_cn.json`、`resources/`
