"""汇总四个方向的技能点行，供 build.py 消费。"""

from catalog.skills_ai import AI
from catalog.skills_ai_more import AI_MORE
from catalog.skills_other import BIGDATA, IOT, SYSTEMS

ROWS = AI + AI_MORE + BIGDATA + SYSTEMS + IOT

# 大模型扩充的别名，写入 aliases.jsonl 时 source=llm，便于后续人工校验。
LLM_ALIASES = {
    "pytorch": ["Pytorch", "PYTORCH", "torch.nn", "nn.Module"],
    "tensorflow": ["Tensorflow", "TensorFlow2", "tf2"],
    "llm": ["大语言模型", "foundation model", "基座模型"],
    "rag": ["检索增强生成RAG", "RAG流水线"],
    "kubernetes": ["kube", "K8S"],
    "golang": ["Golang语言"],
    "prompt-engineering": ["提示词", "prompt tuning", "提示设计"],
    "ai-agent": ["AI智能体", "agentic"],
    "qwen": ["通义", "Qwen-7B", "Qwen-72B"],
    "deepseek": ["deepseek-coder", "DeepSeek Coder"],
    "vllm": ["vLLM serving", "PagedAttention推理"],
    "milvus": ["Zilliz Cloud"],
    "paddlepaddle": ["PaddlePaddle飞桨"],
    "mindspore": ["华为MindSpore"],
    "langchain": ["LangChain Expression Language", "LCEL"],
    "dify": ["Dify.ai"],
    "stable-diffusion": ["SD1.5", "StableDiffusion"],
    "yolo": ["YOLOv5", "YOLOv7", "yolov8"],
    "whisper": ["faster-whisper", "whisper.cpp"],
    "embodied-ai": ["具身智能", "embodied intelligence"],
    "mqtt": ["MQTT 3.1.1", "MQTT 5"],
    "esp32": ["ESP-IDF", "ESP32-S3"],
    "flink": ["Flink DataStream"],
    "spark": ["Spark Core", "spark sql"],
    "clickhouse": ["CH", "clickhouse-client"],
    # TiKV / TiFlash 是 TiDB 体系里独立的组件，不是 TiDB 的别名。
    "tidb": [],
    "ros2": ["rclpy", "rclcpp"],
    "digital-twin": ["digital twins"],
    "tinyml": ["tiny ml", "端侧ML"],
}
