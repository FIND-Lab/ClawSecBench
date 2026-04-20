# ClawSecBench
ClawSecBench is a benchmark specifically designed to evaluate the security of claw systems. It is based on a lifecycle-oriented layered threat model, which corresponds to the core stages of Agent operation and systematically covers typical risk scenarios throughout the Agent's entire lifecycle, including skill supply chain contamination, indirect prompt injection, memory poisoning, context drift, intent deviation, and execution guardrail bypass. This project provides structured pairwise attack/benign samples, aiming to offer a standardized evaluation platform for AI Agent security research.

## Dataset Structure

### Scale and Splits
- Total samples: 150 (30 samples per layer)
- Splits: harmful/benign = 75/75

### Data Format Definition
The dataset is provided in JSON format. 

| Field	| Type | Description |
|-------|------|-------------|
|id|int|Unique identifier for the test case. |
|layer|string|One of the five layers (e.g., "trusted foundation").|
|category|string|Specific attack subtype (e.g., "skill supply-chain attacks").|
|goal|string|"harmful" or "benign".|
|input|list[str]|The user prompt(s). If round > 1, this contains the history.|
|round|int|Number of conversation turns.|
|environment|list[object]|Simulated external context (e.g., file content, tool outputs, website HTML).|

## Layer and Attack Details

### 1. Trusted Foundation Layer
- **Attack surface**: The installation and configuration of agents/extensions/plugins/skills.
- **Attack Category**
    - **Skill Supply-Chain**
        - **Malicious Creation**: Creating a skill with a misleading description to hijack call chains.
        - **Obfuscation**: Hiding malicious logic within normal-looking skill files.
        - **Tool Chain Hijacking**: Skill modifies configuration to call other malicious tools.
    - **Configuration Tampering**
        - **Skill Config**: Modifying existing skill code to break functionality or exfiltrate data.
        - **Agent Identity**: Modifying `SOUL.md`, `IDENTITY.md`, or `AGENTS.md` to alter behavior.

### 2. Perception Input Layer
- **Attack surface**: Untrusted data processed by the agent's tools (browser, file reader).
- **Attack Category**
    - **Indirect Prompt Injection**: Payloads embedded in websites, emails, or documents.

### 3. Cognitive State Layer
- **Attack surface**: Long-term memory storage (`MEMORY.md`) and context window management.
- **Attack Category**
    - **Memory Poisoning**: Injecting malicious rules into persistent memory.
    - **Context Drift**: Long contexts causing the agent to forget initial safety instructions.

### 4. Decision Alignment Layer
- **Attack surface**: Ambiguity in natural language understanding leading to dangerous actions.
- **Attack Category**
    - **Intent Misunderstanding**: Agent misinterprets the intent of a benign expression and thus executes high-risk actions.

### 5. Execution Control Layer
- **Attack surface**: The final shell/command execution step.
- **Attack Category**
    - **Guardrail Bypass**: The agent bypasses the preset safety guardrail rules and executes unauthorized high-risk shell commands.
