"""
카테고리 정의 — 규칙기반 분류용 (1단).
각 카테고리 = GitHub topics(우선) + description 키워드(보조).
순서 = 우선순위(구체적 → 광범위). 위에서부터 먼저 매칭되면 확정.
못 거른 repo만 로컬 LLM(2단)으로 분류.
"""

# (카테고리, topics 집합, 키워드 집합) — 위일수록 우선
CATEGORIES = [
    # AI/에이전트 보안 — 악성 스킬·플러그인·MCP 공급망 공격, 프롬프트 인젝션,
    # 모델 탈취/포이즈닝, LLM 레드팀·취약점 스캔, 가드레일. 최상위 우선순위:
    # 보안 전용 repo는 generic(MCP·Agent·Eval)보다 먼저 잡아 한곳에 모은다.
    ("Security", {
        "ai-security", "llm-security", "ml-security", "model-security", "ai-safety",
        "prompt-injection", "jailbreak", "llm-jailbreak", "llm-guardrails", "guardrails",
        "red-teaming", "ai-red-teaming", "llm-red-teaming", "red-team",
        "adversarial-attacks", "adversarial-machine-learning", "adversarial-examples",
        "adversarial-ml", "supply-chain-security", "mcp-security", "agent-security",
        "llm-vulnerability", "vulnerability-scanner", "ai-red-team", "model-poisoning",
    }, {
        "ai security", "llm security", "prompt injection", "jailbreak", "red teaming",
        "red-teaming", "adversarial attack", "supply chain", "vulnerability scanner",
        "agent security", "model security", "guardrail", "ai safety", "data exfiltration",
        "model poisoning", "secure your llm", "secure your ai", "malicious model",
    }),
    ("MCP", {
        "mcp", "mcp-server", "mcp-servers", "model-context-protocol", "mcp-client",
    }, {
        "mcp server", "model context protocol", "mcp servers",
    }),
    ("Browser", {
        "web-scraping", "browser-automation", "scraping", "crawler", "web-agent",
        "browser-use", "web-automation", "scraper",
    }, {
        "web scraping", "browser automation", "crawl the web", "scrape the web",
        "browser agent",
    }),
    ("Agent", {
        "ai-agent", "ai-agents", "llm-agent", "autonomous-agents", "agents",
        "multi-agent", "agentic", "autonomous-ai", "agent-framework", "ai-agent-framework",
    }, {
        "ai agent", "autonomous agent", "multi-agent", "agentic", "tool use",
        "function calling", "agent framework",
    }),
    ("RAG", {
        "rag", "retrieval-augmented-generation", "vector-database", "vector-search",
        "embeddings", "semantic-search", "vector-store", "vectordb", "knowledge-base",
    }, {
        "retrieval-augmented", "rag pipeline", "vector store", "vector database",
        "semantic search", "embedding", "knowledge base",
    }),
    ("Fine-tuning", {
        "fine-tuning", "finetuning", "lora", "qlora", "rlhf", "peft",
        "instruction-tuning", "model-training", "sft", "dpo", "training",
    }, {
        "fine-tune", "fine-tuning", "instruction tuning", "lora", "rlhf",
        "supervised fine", "train your own", "pretraining",
    }),
    ("Multimodal", {
        "multimodal", "vision-language-model", "vlm", "multimodal-llm",
        "image-text", "multi-modal", "vision-language",
    }, {
        "multimodal", "vision-language", "vision language", "image and text",
    }),
    ("Code-AI", {
        "code-generation", "copilot", "code-assistant", "ai-coding",
        "code-completion", "coding-assistant", "code-llm", "ai-pair-programming",
        "developer-tools",
    }, {
        "code generation", "coding assistant", "ai pair", "copilot",
        "code completion", "autocomplete code", "coding agent",
    }),
    ("Robotics", {
        "robotics", "embodied-ai", "robot-learning", "manipulation", "ros",
        "robot", "embodied", "autonomous-driving", "self-driving",
    }, {
        "embodied", "robot learning", "manipulation", "autonomous driving",
        "self-driving",
    }),
    ("RL", {
        "reinforcement-learning", "deep-reinforcement-learning", "rl",
        "q-learning", "policy-gradient", "rlhf-training", "multi-agent-rl",
    }, {
        "reinforcement learning", "policy gradient", "q-learning",
        "reward model", "markov decision",
    }),
    ("Vision", {
        "computer-vision", "image-generation", "diffusion-models", "stable-diffusion",
        "object-detection", "segmentation", "image-classification", "ocr",
        "text-to-image", "image-editing", "face-recognition", "pose-estimation",
        "video-generation", "image-to-image", "super-resolution",
    }, {
        "computer vision", "image generation", "object detection", "segmentation",
        "diffusion", "text-to-image", "image editing", "video generation",
    }),
    ("Audio-Speech", {
        "speech-recognition", "text-to-speech", "tts", "asr", "speech-to-text",
        "voice-cloning", "audio-generation", "whisper", "music-generation",
        "speech-synthesis", "voice", "audio", "speech",
    }, {
        "speech recognition", "text to speech", "speech to text", "voice clon",
        "audio generation", "music generation", "speech synthesis",
    }),
    ("NLP", {
        "nlp", "natural-language-processing", "text-classification",
        "named-entity-recognition", "sentiment-analysis", "machine-translation",
        "question-answering", "summarization", "ner", "topic-modeling",
    }, {
        "natural language processing", "text classification", "named entity",
        "sentiment analysis", "machine translation", "summarization",
    }),
    ("Eval", {
        "evaluation", "benchmark", "llm-evaluation", "model-evaluation", "eval",
        "benchmarking", "leaderboard", "llm-eval", "guardrails", "observability",
    }, {
        "evaluation framework", "llm evaluation", "benchmark", "leaderboard",
        "guardrail", "red teaming", "model evaluation",
    }),
    ("MLOps", {
        "mlops", "model-serving", "ml-infrastructure", "experiment-tracking",
        "model-deployment", "inference", "ml-pipeline", "feature-store",
        "model-monitoring", "llmops", "llm-serving", "quantization",
        "inference-engine", "gpu", "distributed-training",
    }, {
        "model serving", "model deployment", "inference server", "ml pipeline",
        "experiment tracking", "feature store", "quantization", "llm serving",
    }),
    ("Dataset", {
        "dataset", "datasets", "data-annotation", "synthetic-data",
        "data-labeling", "data-curation",
    }, {
        "dataset", "data annotation", "synthetic data", "data labeling",
        "data curation",
    }),
    ("Prompt", {
        "prompt-engineering", "prompts", "system-prompt", "jailbreak",
        "awesome-prompts", "prompt", "prompt-injection",
    }, {
        "prompt engineering", "system prompt", "collection of prompts",
        "prompt library", "prompt template",
    }),
    ("LLM", {
        "llm", "large-language-models", "large-language-model", "gpt",
        "transformers", "language-model", "prompt-engineering", "chatbot",
        "openai", "foundation-models", "llama", "mistral", "gemini", "claude",
        "deepseek", "qwen", "rag-chatbot", "chatgpt",
    }, {
        "large language model", "language model", "prompt engineering", "chatbot",
        "foundation model", "gpt", "instruction-following",
    }),
    # ↓ 낮은 우선순위: 위 구체 카테고리 다 놓친 leftover만 잡음 (범용 ML·교육)
    ("Learning", {
        "tutorial", "tutorials", "course", "awesome", "awesome-list", "roadmap",
        "lessons", "learning-resources", "education", "examples", "book",
        "curriculum", "study",
    }, {
        "tutorial", "course", "lessons", "roadmap", "for beginners",
        "from scratch", "awesome list", "learning path", "study",
    }),
    ("Framework", {
        "machine-learning", "deep-learning", "pytorch", "tensorflow",
        "scikit-learn", "jax", "keras", "neural-network", "neural-networks",
        "onnx", "ml", "deep-neural-networks", "numpy", "data-science",
    }, {
        "machine learning framework", "deep learning framework",
        "neural network library", "machine learning library", "ml framework",
    }),
]

FALLBACK = "Other"  # 규칙으로 못 거른 거 → 나중에 LLM 분류 대상


def classify(topics, description, language=None):
    """topics/description으로 카테고리 1개 반환. 못 정하면 FALLBACK."""
    topics_set = {t.lower() for t in (topics or [])}
    desc = (description or "").lower()

    # 1순위: topics 정확 매칭 (구체적 카테고리 먼저)
    for cat, cat_topics, _ in CATEGORIES:
        if topics_set & cat_topics:
            return cat
    # 2순위: description 키워드
    for cat, _, keywords in CATEGORIES:
        if any(kw in desc for kw in keywords):
            return cat
    return FALLBACK


# 수집용 시드 쿼리 (GitHub Search q에 던질 topic) — 풀 실행 시 사용
SEED_TOPICS = [
    "llm", "large-language-models", "ai-agents", "agentic", "rag",
    "transformers", "fine-tuning", "lora", "multimodal", "vision-language-model",
    "computer-vision", "diffusion-models", "stable-diffusion", "object-detection",
    "speech-recognition", "text-to-speech", "nlp", "reinforcement-learning",
    "code-generation", "copilot", "robotics", "embodied-ai",
    "mlops", "model-serving", "llm-evaluation", "quantization",
    "mcp", "mcp-server", "web-scraping", "browser-automation", "prompt-engineering",
    "machine-learning", "deep-learning", "generative-ai",
    # AI 보안 시드 — 신규 보안 repo 수집용
    "ai-security", "llm-security", "prompt-injection", "ai-red-teaming",
    "adversarial-machine-learning", "supply-chain-security", "mcp-security", "ai-safety",
]
