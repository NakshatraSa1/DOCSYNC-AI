# DOCSYNC-AI
Csync AI

Smarter Code Reviews. Stronger Code.

Csync AI is a local-first AI-powered code review platform that helps developers identify security vulnerabilities, logic errors, and code quality issues before merging code.

Overview

Traditional code reviews can be time-consuming. Csync AI combines deterministic security scanning with local AI-powered code analysis using Gemma 4 E4B through Ollama.

Key Features

- Local AI Code Review: Uses Gemma 4 E4B for contextual code analysis.
- Security Scanner: Detects hardcoded credentials and potentially dangerous functions.
- Git Integration: Reviews uncommitted changes and branch differences.
- Custom Team Rules: Supports ".privpr.md" coding and security standards.
- Review Reports: Generates structured code review reports.
- Privacy-Focused Architecture: Supports local inference without sending source code to an external AI inference API.

Technology Stack

- Python
- Gemma 4 E4B
- Ollama
- Git
- HTML, CSS and JavaScript

Prerequisites

- Python installed
- Ollama installed
- Gemma 4 E4B model downloaded

Installation

1. Clone the repository

git clone https://github.com/NakshatraSa1/Csync-AI.git
cd Csync-AI

2. Download Gemma 4 E4B

ollama pull gemma4:e4b

3. Install dependencies

pip install -r requirements.txt

4. Start Ollama

Ensure Ollama is running locally.

5. Launch Csync AI

python web_app.py

6. Open the application

Visit:

"http://127.0.0.1:8000"

How It Works

1. Select or provide code for review.
2. The static scanner checks for known risky patterns.
3. Gemma 4 E4B analyzes code context and potential issues.
4. Csync AI presents findings by severity.
5. Generate a structured review report.

Privacy

Csync AI supports local-first inference through Ollama. When configured for local inference, code is processed on the user's machine rather than sent to an external AI inference service. Review other integrations and deployment settings separately.

Current Limitations

- AI findings may include false positives or miss vulnerabilities.
- Detection depends on the implemented scanner rules and model analysis.
- A code review tool does not replace professional security audits.

Contributing

Contributions, bug reports, and feature suggestions are welcome.

Please open an issue or submit a pull request.

License

Released under the MIT License. See "LICENSE" (LICENSE).
