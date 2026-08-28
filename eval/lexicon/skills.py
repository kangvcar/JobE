"""技能点词表。规范名与切分准则一致；匹配时别名映射到 name。"""

from __future__ import annotations

import re
from dataclasses import dataclass

FAMILIES = ("ai", "bigdata", "smart_system", "iot", "general", "soft")


@dataclass(frozen=True)
class SkillDef:
    name: str
    family: str
    aliases: tuple[str, ...] = ()

    def all_forms(self) -> tuple[str, ...]:
        forms = (self.name,) + self.aliases
        seen: list[str] = []
        for f in forms:
            if f and f not in seen:
                seen.append(f)
        return tuple(seen)


def _s(name: str, family: str, *aliases: str) -> SkillDef:
    return SkillDef(name=name, family=family, aliases=aliases)


SKILLS: tuple[SkillDef, ...] = (
    # --- 人工智能 ---
    _s("Python", "ai", "python"),
    _s("PyTorch", "ai", "pytorch", "Pytorch"),
    _s("TensorFlow", "ai", "tensorflow", "Tensorflow", "TF"),
    _s("JAX", "ai", "jax"),
    _s("CUDA", "ai", "cuda"),
    _s("cuDNN", "ai", "cudnn"),
    _s("TensorRT", "ai", "tensorrt", "Tensor RT"),
    _s("ONNX", "ai", "onnx"),
    _s("OpenVINO", "ai", "openvino"),
    _s("Triton", "ai", "Triton Inference Server"),
    _s("DeepSpeed", "ai", "deepspeed"),
    _s("Megatron", "ai", "Megatron-LM", "megatron"),
    _s("HuggingFace", "ai", "Hugging Face", "transformers库"),
    _s("vLLM", "ai", "vllm"),
    _s("LangChain", "ai", "langchain"),
    _s("LlamaIndex", "ai", "llama-index"),
    _s("LoRA", "ai", "lora", "QLoRA", "qlora"),
    _s("RLHF", "ai", "rlhf"),
    _s("RAG", "ai", "检索增强生成"),
    _s("Agent", "ai", "智能体", "LLM Agent"),
    _s("Transformer", "ai", "transformer"),
    _s("BERT", "ai", "bert"),
    _s("GPT", "ai", "gpt"),
    _s("大模型", "ai", "LLM", "大语言模型", "生成式大模型"),
    _s("机器学习", "ai", "Machine Learning", "ML"),
    _s("深度学习", "ai", "Deep Learning", "DL"),
    _s("强化学习", "ai", "Reinforcement Learning", "RL"),
    _s("计算机视觉", "ai", "CV", "视觉算法"),
    _s("目标检测", "ai", "Object Detection"),
    _s("语义分割", "ai", "Semantic Segmentation"),
    _s("实例分割", "ai", "Instance Segmentation"),
    _s("图像分类", "ai"),
    _s("OCR", "ai", "文字识别"),
    _s("OpenCV", "ai", "opencv"),
    _s("MMDetection", "ai", "mmdetection"),
    _s("YOLO", "ai", "YOLOv5", "YOLOv8", "yolo"),
    _s("NLP", "ai", "自然语言处理"),
    _s("文本分类", "ai"),
    _s("命名实体识别", "ai", "NER"),
    _s("机器翻译", "ai"),
    _s("语音识别", "ai", "ASR", "语音转写"),
    _s("语音合成", "ai", "TTS"),
    _s("多模态", "ai", "Multimodal"),
    _s("扩散模型", "ai", "Diffusion", "Stable Diffusion"),
    _s("GAN", "ai", "生成对抗网络"),
    _s("推荐系统", "ai", "推荐算法"),
    _s("召回", "ai", "召回算法"),
    _s("排序", "ai", "排序模型", "Learning to Rank"),
    _s("特征工程", "ai"),
    _s("XGBoost", "ai", "xgboost"),
    _s("LightGBM", "ai", "lightgbm"),
    _s("scikit-learn", "ai", "sklearn", "Scikit-Learn"),
    _s("图神经网络", "ai", "GNN", "GCN"),
    _s("知识图谱", "ai"),
    _s("向量数据库", "ai", "Milvus", "Faiss", "FAISS"),
    _s("Milvus", "ai"),
    _s("Faiss", "ai", "FAISS"),
    _s("分布式训练", "ai", "模型并行", "数据并行"),
    _s("混合精度", "ai", "AMP", "FP16"),
    _s("模型量化", "ai", "量化", "INT8"),
    _s("模型蒸馏", "ai", "知识蒸馏"),
    _s("模型推理", "ai", "推理优化", "推理加速"),
    _s("MLOps", "ai", "机器学习工程"),
    _s("A/B测试", "ai", "AB测试", "A/B 测试"),
    _s("Prompt Engineering", "ai", "提示词工程", "Prompt"),
    _s("微调", "ai", "SFT", "Fine-tune", "finetune", "Fine-tuning"),
    _s("预训练", "ai", "Pretrain", "pre-training"),
    _s("NeRF", "ai"),
    _s("点云深度学习", "ai", "3D视觉"),
    _s("时序预测", "ai", "时间序列"),
    _s("因果推断", "ai"),
    _s("NCCL", "ai"),
    _s("MPI", "ai"),
    # --- 大数据 ---
    _s("Hadoop", "bigdata", "hadoop"),
    _s("Spark", "bigdata", "spark", "SparkSQL", "Spark SQL"),
    _s("Flink", "bigdata", "flink", "Apache Flink"),
    _s("Kafka", "bigdata", "kafka"),
    _s("Hive", "bigdata", "hive"),
    _s("HBase", "bigdata", "hbase"),
    _s("ClickHouse", "bigdata", "clickhouse"),
    _s("StarRocks", "bigdata", "starrocks"),
    _s("Doris", "bigdata", "Apache Doris"),
    _s("Presto", "bigdata"),
    _s("Trino", "bigdata"),
    _s("Impala", "bigdata"),
    _s("Elasticsearch", "bigdata", "ES", "elastic search"),
    _s("Redis", "bigdata", "redis"),
    _s("MySQL", "bigdata", "mysql"),
    _s("PostgreSQL", "bigdata", "postgres", "pgsql"),
    _s("TiDB", "bigdata", "tidb"),
    _s("MongoDB", "bigdata", "mongodb"),
    _s("Oracle", "bigdata"),
    _s("SQL", "bigdata"),
    _s("数据仓库", "bigdata", "数仓"),
    _s("实时数仓", "bigdata"),
    _s("数据湖", "bigdata", "Data Lake"),
    _s("ETL", "bigdata", "ELT"),
    _s("数据建模", "bigdata"),
    _s("维度建模", "bigdata"),
    _s("数据治理", "bigdata"),
    _s("数据质量", "bigdata"),
    _s("数据中台", "bigdata"),
    _s("CDC", "bigdata", "Flink CDC"),
    _s("Iceberg", "bigdata", "Apache Iceberg"),
    _s("Hudi", "bigdata", "Apache Hudi"),
    _s("Paimon", "bigdata", "Apache Paimon"),
    _s("Airflow", "bigdata", "airflow"),
    _s("DolphinScheduler", "bigdata", "海豚调度"),
    _s("DataX", "bigdata"),
    _s("MapReduce", "bigdata"),
    _s("YARN", "bigdata"),
    _s("Zookeeper", "bigdata", "ZooKeeper"),
    _s("用户画像", "bigdata"),
    _s("指标平台", "bigdata"),
    _s("特征平台", "bigdata"),
    _s("实时计算", "bigdata", "流式计算"),
    _s("离线计算", "bigdata"),
    _s("数据开发", "bigdata"),
    _s("InfluxDB", "bigdata"),
    _s("TDengine", "bigdata", "涛思"),
    _s("DolphinDB", "bigdata"),
    # --- 智能系统 ---
    _s("ROS", "smart_system", "ros"),
    _s("ROS2", "smart_system", "ROS 2", "ros2"),
    _s("SLAM", "smart_system"),
    _s("路径规划", "smart_system", "运动规划"),
    _s("运动控制", "smart_system"),
    _s("感知融合", "smart_system", "多传感器融合", "传感器融合"),
    _s("自动驾驶", "smart_system", "智能驾驶", "智驾"),
    _s("高精地图", "smart_system", "HD Map"),
    _s("CAN", "smart_system", "CAN总线"),
    _s("AUTOSAR", "smart_system", "Autosar"),
    _s("ISO 26262", "smart_system", "ISO26262"),
    _s("功能安全", "smart_system"),
    _s("点云", "smart_system", "PCL"),
    _s("PCL", "smart_system"),
    _s("激光雷达", "smart_system", "LiDAR", "Lidar"),
    _s("毫米波雷达", "smart_system"),
    _s("卡尔曼滤波", "smart_system", "Kalman"),
    _s("PID", "smart_system", "PID控制"),
    _s("MPC", "smart_system", "模型预测控制"),
    _s("Apollo", "smart_system", "百度Apollo"),
    _s("Autoware", "smart_system"),
    _s("CARLA", "smart_system"),
    _s("Gazebo", "smart_system"),
    _s("嵌入式Linux", "smart_system", "Embedded Linux"),
    _s("实时操作系统", "smart_system"),
    _s("控制算法", "smart_system"),
    _s("规划控制", "smart_system"),
    _s("定位", "smart_system", "定位算法"),
    _s("标定", "smart_system", "传感器标定"),
    _s("仿真", "smart_system", "仿真平台"),
    _s("车载以太网", "smart_system"),
    _s("SOME/IP", "smart_system"),
    _s("QNX", "smart_system"),
    _s("Android Automotive", "smart_system"),
    # --- 物联网 ---
    _s("MQTT", "iot"),
    _s("CoAP", "iot"),
    _s("ZigBee", "iot", "Zigbee"),
    _s("LoRa", "iot", "LoRaWAN"),
    _s("NB-IoT", "iot", "NBIoT", "NB IOT"),
    _s("STM32", "iot"),
    _s("FreeRTOS", "iot"),
    _s("RTOS", "iot"),
    _s("嵌入式", "iot", "嵌入式开发"),
    _s("MCU", "iot"),
    _s("模组", "iot"),
    _s("网关", "iot", "物联网网关"),
    _s("边缘计算", "iot", "Edge Computing"),
    _s("数字孪生", "iot"),
    _s("OPC-UA", "iot", "OPC UA", "OPCUA"),
    _s("Modbus", "iot"),
    _s("OTA", "iot"),
    _s("物联网平台", "iot", "IoT平台", "IoT 平台"),
    _s("Wi-Fi", "iot", "WiFi", "wifi"),
    _s("BLE", "iot", "蓝牙", "Bluetooth"),
    _s("5G", "iot"),
    _s("低功耗", "iot"),
    _s("传感器", "iot"),
    _s("原理图", "iot"),
    _s("PCB", "iot"),
    _s("驱动开发", "iot", "设备驱动", "BSP"),
    _s("BSP", "iot"),
    _s("Keil", "iot"),
    _s("I2C", "iot"),
    _s("SPI", "iot"),
    _s("UART", "iot"),
    _s("ARM", "iot"),
    _s("RISC-V", "iot", "RISCV"),
    # --- 通用工程 ---
    _s("Linux", "general"),
    _s("Git", "general"),
    _s("Docker", "general"),
    _s("Kubernetes", "general", "K8s", "k8s", "K8S"),
    _s("CI/CD", "general", "CICD", "持续集成"),
    _s("Go", "general", "Golang", "golang"),
    _s("Java", "general"),
    _s("C++", "general", "Cpp", "cplusplus"),
    _s("C 语言", "general", "C语言", "C/C++"),  # C/C++ 整词命中时同时会再匹配 C++；见匹配器去重
    _s("Rust", "general"),
    _s("Scala", "general"),
    _s("Shell", "general", "Bash", "shell"),
    _s("JavaScript", "general", "JS", "TypeScript", "TS"),
    _s("微服务", "general"),
    _s("分布式系统", "general", "分布式"),
    _s("高并发", "general"),
    _s("高可用", "general"),
    _s("设计模式", "general"),
    _s("计算机网络", "general"),
    _s("操作系统", "general"),
    _s("数据结构", "general"),
    _s("算法", "general", "算法基础", "LeetCode"),
    _s("计算机组成", "general"),
    _s("编译原理", "general"),
    _s("HTTP", "general"),
    _s("gRPC", "general", "GRPC", "grpc"),
    _s("RPC", "general"),
    _s("RESTful", "general", "REST API", "REST"),
    _s("Nginx", "general"),
    _s("消息队列", "general", "MQ"),
    _s("面向对象", "general", "OOP"),
    _s("多线程", "general", "并发编程"),
    _s("网络编程", "general"),
    _s("性能优化", "general"),
    _s("单元测试", "general"),
    _s("Linux 内核", "general", "内核开发"),
    _s("Makefile", "general", "CMake"),
    _s("CMake", "general"),
    _s("GCC", "general"),
    _s("GDB", "general"),
    _s("MATLAB", "general", "Matlab", "matlab"),
    _s("FPGA", "general"),
    _s("Verilog", "general"),
    _s("DSP", "general"),
    # --- 软技能（计入抽取，不计入档位覆盖率）---
    _s("沟通能力", "soft"),
    _s("团队合作", "soft", "团队协作", "跨团队协作"),
    _s("技术写作", "soft", "文档能力"),
    _s("英语", "soft", "英语书面表达", "英语口语", "CET-6", "CET6"),
    _s("项目管理", "soft"),
    _s("带人", "soft", "团队管理", "带团队"),
    _s("技术评审", "soft", "Code Review", "代码评审"),
)


def build_index() -> tuple[dict[str, SkillDef], list[tuple[str, SkillDef]]]:
    by_name = {s.name: s for s in SKILLS}
    forms: list[tuple[str, SkillDef]] = []
    for s in SKILLS:
        for form in s.all_forms():
            forms.append((form, s))
    forms.sort(key=lambda x: len(x[0]), reverse=True)
    return by_name, forms


BY_NAME, FORMS = build_index()

_SKIP_SOFT_ATTITUDE = re.compile(
    r"责任心|抗压|热爱学习|积极向上|执行力|有激情|认同公司|吃苦耐劳|加班|价值观"
)


def _is_ascii_token(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def _find_all(text: str, needle: str) -> list[tuple[int, int]]:
    if not needle:
        return []
    hits: list[tuple[int, int]] = []
    if _is_ascii_token(needle) and needle.lower() not in {"c"}:
        pattern = re.compile(rf"(?<![A-Za-z0-9_+]){re.escape(needle)}(?![A-Za-z0-9_+])", re.I)
        for m in pattern.finditer(text):
            hits.append((m.start(), m.end()))
        return hits
    start = 0
    while True:
        i = text.find(needle, start)
        if i < 0:
            break
        hits.append((i, i + len(needle)))
        start = i + 1
    return hits


def extract_skills(text: str) -> list[dict]:
    """按最长匹配、不重叠切分。同一规范名只保留首次。"""
    occupied = [False] * len(text)
    found: dict[str, dict] = {}
    for form, skill in FORMS:
        if skill.name in found:
            continue
        for start, end in _find_all(text, form):
            if any(occupied[start:end]):
                continue
            if form.replace(" ", "") in {"C/C++", "c/c++"}:
                # 准则 R1：斜杠列举拆开
                found["C 语言"] = {
                    "name": "C 语言",
                    "family": "general",
                    "surface_form": text[start : start + 1],
                    "span": {"start": start, "end": start + 1},
                }
                found["C++"] = {
                    "name": "C++",
                    "family": "general",
                    "surface_form": "C++",
                    "span": {"start": end - 3, "end": end},
                }
                for i in range(start, end):
                    occupied[i] = True
                break
            found[skill.name] = {
                "name": skill.name,
                "family": skill.family,
                "surface_form": text[start:end],
                "span": {"start": start, "end": end},
            }
            for i in range(start, end):
                occupied[i] = True
            break
    ordered = sorted(found.values(), key=lambda x: x["span"]["start"])
    return ordered


def necessity_for_span(text: str, start: int) -> str:
    window = text[max(0, start - 80) : start]
    if re.search(r"加分|优先|plus|了解即可|有则更好", window, re.I):
        return "bonus"
    return "required"


def level_hint_for_span(text: str, start: int) -> int | None:
    window = text[max(0, start - 12) : start + 8]
    if re.search(r"精通|专家级|深入", window):
        return 3
    if re.search(r"掌握|熟悉|熟练|良好", window):
        return 2
    if re.search(r"了解|接触|听说", window):
        return 1
    return None
