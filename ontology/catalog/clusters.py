"""技能簇。方向对应新一代信息技术四个方向，簇是方向下的技能内核。"""

CLUSTERS = [
    # 人工智能
    ("cluster.prog-lang", "编程语言", "Programming Languages", "ai"),
    ("cluster.ml-framework", "机器学习框架", "Machine Learning Frameworks", "ai"),
    ("cluster.llm-genai", "大模型与生成式人工智能", "LLM and Generative AI", "ai"),
    ("cluster.cv", "计算机视觉", "Computer Vision", "ai"),
    ("cluster.nlp", "自然语言处理", "Natural Language Processing", "ai"),
    ("cluster.speech", "语音处理", "Speech Processing", "ai"),
    ("cluster.rl", "强化学习", "Reinforcement Learning", "ai"),
    ("cluster.recsys", "推荐系统", "Recommender Systems", "ai"),
    ("cluster.mlops", "机器学习工程与MLOps", "MLOps", "ai"),
    ("cluster.ml-theory", "机器学习基础", "ML Foundations", "ai"),
    ("cluster.eval", "模型评测与对齐", "Evaluation and Alignment", "ai"),
    ("cluster.agent", "智能体", "Agents", "ai"),
    ("cluster.accel", "训练与推理加速", "Training and Inference Acceleration", "ai"),
    ("cluster.multimodal", "多模态", "Multimodal Learning", "ai"),
    # 大数据
    ("cluster.batch-compute", "批处理与分布式计算", "Batch and Distributed Compute", "bigdata"),
    ("cluster.stream", "流处理", "Stream Processing", "bigdata"),
    ("cluster.lakehouse", "数据湖仓", "Lakehouse", "bigdata"),
    ("cluster.olap", "分析型数据库", "Analytical Databases", "bigdata"),
    ("cluster.db", "事务与存储", "Transactional Stores", "bigdata"),
    ("cluster.bi", "商业智能", "Business Intelligence", "bigdata"),
    ("cluster.de-tools", "数据集成与调度", "Data Integration and Orchestration", "bigdata"),
    ("cluster.governance", "数据治理与质量", "Data Governance", "bigdata"),
    ("cluster.cloud-data", "云数据平台", "Cloud Data Platforms", "bigdata"),
    # 智能系统
    ("cluster.robotics", "机器人", "Robotics", "intelligent_systems"),
    ("cluster.industrial", "工业自动化与工业软件", "Industrial Automation", "intelligent_systems"),
    ("cluster.embedded", "嵌入式与实时系统", "Embedded and Realtime", "intelligent_systems"),
    ("cluster.digital-twin", "数字孪生与仿真", "Digital Twin and Simulation", "intelligent_systems"),
    ("cluster.vr-ar", "虚拟现实与增强现实", "VR and AR", "intelligent_systems"),
    ("cluster.eda", "集成电路与EDA", "EDA and IC Design", "intelligent_systems"),
    ("cluster.vehicle", "智能网联汽车", "Intelligent Connected Vehicles", "intelligent_systems"),
    # 物联网
    ("cluster.iot-protocol", "物联网应用协议", "IoT Application Protocols", "iot"),
    ("cluster.iot-wireless", "物联网无线与接入", "IoT Wireless", "iot"),
    ("cluster.iot-hw", "物联网硬件与模组", "IoT Hardware", "iot"),
    ("cluster.iot-platform", "物联网平台与中间件", "IoT Platforms", "iot"),
    ("cluster.edge", "边缘计算", "Edge Computing", "iot"),
    ("cluster.iot-security", "物联网安全", "IoT Security", "iot"),
]
