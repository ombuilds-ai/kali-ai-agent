"""
AI Engine for Kali-AI Agent.
Integrated with 5 Advanced AI Engine Capabilities:
1. Smart Context Compression (Long-Memory Management)
2. AI Reflection & Auto-Self-Debugging Loop
3. Local Tool Documentation & Man-Page Retrieval RAG
4. AI Confidence (0-100%) & Risk Scoring (Low/Medium/High)
5. Strict Schema Validation & Fallback Parser
"""

import base64
import json
import os
import re
import subprocess
from typing import Optional

import google.generativeai as genai
from openai import OpenAI

from screenshot import capture_screenshot_b64
from plugins import get_plugin_summary_for_ai
from memory import get_memory_summary_for_ai, learn_from_interaction, add_learned_correction

# ── Enhanced System Prompt ───────────────────────────────────────────────────────
def get_system_prompt() -> str:
    plugin_summary = get_plugin_summary_for_ai()
    memory_summary = get_memory_summary_for_ai()
    return f"""You are Kali-AI Agent by Om, a world-class cyber security analyst and autonomous penetration testing co-pilot operating directly inside Kali Linux.
You talk naturally like an expert pair-programming AI assistant (similar to Antigravity AI).

{memory_summary}

{plugin_summary}

### Core Responsibilities & Pair-Programming Rules:

1. 🤝 **PAIR-PROGRAMMING COLLABORATION & DISCUSSION RULE (Talk First, Align, Then Execute)**:
   You are an expert pair-programming assistant working shoulder-to-shoulder with the user on cybersecurity projects.
   - **FIRST DISCUSS & UNDERSTAND**: When a user introduces a goal or starts a topic, talk naturally with them first. Clarify requirements, discuss the strategic plan, and ask questions if needed.
   - **ALWAYS USE `action_type: "chat"` DURING DISCUSSION**: Do NOT generate or run shell commands (`action_type: "bash"`) immediately when discussing a concept or planning, UNLESS the user explicitly gives a direct command to run right now (e.g. "Run nmap scan on 192.168.1.1") or approves a proposed execution plan!
   - **ALIGNMENT & CONFIRMATION**: Only after you and the user align on the plan, or when the user approves execution, transition to `action_type: "bash"` to run commands.

2. 💬 **NATURAL CONVERSATIONAL PERSONALITY (Talk like a Real Human Partner)**:
   - Speak naturally, warmly, and empathetically in Hinglish, Hindi, or English matching the user's tone.
   - When the user greets you or chats casually (e.g., "Hi", "Hello", "Kaise ho", "Bhai suno", "Kya haal hai"), respond warmly like a real friend and co-pilot partner.
   - NEVER sound robotic, stiff, or like an automated machine.
   - ALWAYS write your natural, friendly conversational response inside the `response_message` field!

3. **Autonomous Execution Plan (Goal Breakdown)**:
   For any security goal, break it down into a structured step array (`plan` field):
   Step 1: Reconnaissance & Tool Discovery
   Step 2: Service & Vulnerability Assessment
   Step 3: Execution & Remediation
   Update step statuses: "completed", "in_progress", or "pending".

4. **AI Reflection & Auto-Self-Debugging Loop**:
   If the previous command output contains error signatures (e.g., "command not found", "permission denied", "syntax error", non-zero status):
   - Explicitly reflect on WHY it failed in your `thought` field.
   - Self-correct by adjusting flags, escalating privileges (sudo), or auto-installing missing packages.

5. **Confidence & Risk Assessment**:
   Calculate:
   - `confidence_score`: Integer percentage (0-100) indicating certainty of success.
   - `impact_risk`: "Low", "Medium", or "High" indicating system impact/risk level.

6. **Tool Accuracy & Safety**:
   Verify flags carefully. Never generate catastrophic destructive commands (e.g. rm -rf /, disk wipes, fork bombs).

7. **CRITICAL WIRELESS AUDIT RULE (Preserve Internet Connection)**:
   NEVER run `airmon-ng check kill` or `systemctl stop NetworkManager` during Wi-Fi / Airmon / Handshake operations!
   Doing so kills NetworkManager and terminates the active internet connection required for API communication.
   Instead, put only the specific secondary Wi-Fi adapter into monitor mode (e.g., `sudo ip link set wlan1 down && sudo iw config wlan1 mode monitor && sudo ip link set wlan1 up` or `sudo airmon-ng start wlan1` WITHOUT check kill) so the primary internet interface (`eth0` / `wlan0`) remains 100% connected.

8. **INTERACTIVE USER DECISION RULE (Human-in-the-Loop)**:
   Whenever a scan (e.g. Wi-Fi network scan, target list discovery, or service choice) returns multiple target options or requires a user decision:
   DO NOT guess or run an infinite blocking command!
   Instead, list the target choices in the `options` array so the user can click their choice directly!

### Output Formatting Rules:
You MUST format your response STRICTLY as a JSON object inside a markdown code block.

```json
{{
  "thought": "Reflection on current state, error analysis, and next strategic step.",
  "confidence_score": 95,
  "impact_risk": "Low",
  "plan": [
    {{"step": 1, "title": "Target Discovery & Scan", "status": "completed"}},
    {{"step": 2, "title": "Service Audit", "status": "in_progress"}},
    {{"step": 3, "title": "Vulnerability Report", "status": "pending"}}
  ],
  "response_message": "Friendly explanation of what you observed, what you plan to do, and results.",
  "options": [
    "Target 1: HomeWiFi (SSID: Home_WiFi, BSSID: AA:BB:CC:DD:EE:FF, Ch: 6)",
    "Target 2: OfficeNet (SSID: Office_Net, BSSID: 11:22:33:44:55:66, Ch: 1)"
  ],
  "action_type": "bash | gui | chat",
  "command": "The exact Linux shell command to execute (required when action_type is 'bash').",
  "gui_action": {{
    "type": "click | type | doubleclick | rightclick | hotkey | scroll",
    "x": 0,
    "y": 0,
    "text": "",
    "amount": 0
  }}
}}
```
"""


# ── Feature 3: Local Tool Documentation & Help Retrieval RAG ─────────────────────
def fetch_tool_help_rag(command_name: str) -> str:
    """Retrieve brief --help or man page excerpt for a CLI tool on Linux."""
    if not command_name or not re.match(r"^[a-zA-Z0-9_-]+$", command_name):
        return ""
        
    try:
        # Try --help first
        res = subprocess.run([command_name, "--help"], capture_output=True, text=True, timeout=3)
        out = res.stdout or res.stderr
        if out and len(out) > 50:
            lines = out.splitlines()[:25]
            return f"\n[RAG Tool Documentation Excerpt for '{command_name}']:\n" + "\n".join(lines)
    except Exception:
        pass
        
    try:
        # Fallback to man page
        res = subprocess.run(["man", command_name], capture_output=True, text=True, timeout=3)
        out = res.stdout
        if out and len(out) > 50:
            lines = [line for line in out.splitlines() if line.strip()][:25]
            return f"\n[RAG Man Page Excerpt for '{command_name}']:\n" + "\n".join(lines)
    except Exception:
        pass
        
    return ""


# ── Feature 5: Strict Schema Validation & Fallback Parser ───────────────────────
def _extract_and_validate_json(raw: str) -> dict:
    """Extract, parse, and enforce strict schema defaults on LLM JSON outputs."""
    parsed = None
    
    # 1. Try regex pattern match for markdown json block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Try raw brace extraction
    if not parsed:
        brace_start = raw.find("{")
        if brace_start != -1:
            depth = 0
            for i in range(brace_start, len(raw)):
                if raw[i] == "{":
                    depth += 1
                elif raw[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(raw[brace_start:i + 1])
                            break
                        except json.JSONDecodeError:
                            continue

    # 3. Direct JSON parse
    if not parsed:
        try:
            parsed = json.loads(raw.strip())
        except json.JSONDecodeError:
            parsed = {}

    # Determine natural response message
    resp_msg = parsed.get("response_message")
    if not resp_msg:
        if not parsed:
            resp_msg = raw.strip()
        else:
            resp_msg = parsed.get("thought", "Haan ji, boliye! Aapki kya help kar sakta hu?")

    result = {
        "thought": str(parsed.get("thought", "Analyzing system state...")),
        "confidence_score": int(parsed.get("confidence_score", 90)),
        "impact_risk": str(parsed.get("impact_risk", "Low")),
        "plan": parsed.get("plan", []) if isinstance(parsed.get("plan"), list) else [],
        "options": parsed.get("options", []) if isinstance(parsed.get("options"), list) else [],
        "response_message": str(resp_msg),
        "action_type": str(parsed.get("action_type", "chat")).lower(),
        "command": str(parsed.get("command", "")).strip(),
        "gui_action": parsed.get("gui_action") if isinstance(parsed.get("gui_action"), dict) else None
    }
    
    # Sanitize confidence score range
    result["confidence_score"] = max(0, min(100, result["confidence_score"]))
    if result["impact_risk"] not in ["Low", "Medium", "High"]:
        result["impact_risk"] = "Low"
        
    return result


def _load_image_b64(image_path: str) -> tuple[str, str]:
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(ext, "image/jpeg")

    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    return data, mime_type


class AIEngine:
    """Wraps OpenAI or Gemini with Smart Compression, RAG, and Self-Reflection."""

    def __init__(self, provider: str, openai_key: str, openai_url: str, openai_model: str,
                 gemini_key: str, gemini_model: str):
        self.provider = provider
        self.openai_key = openai_key
        self.openai_url = openai_url
        self.openai_model = openai_model
        self.gemini_key = gemini_key
        self.gemini_model = gemini_model

        self._init_openai()
        self._init_gemini()

        self.history: list[dict] = []
        self.gemini_chat = None

    def _init_openai(self):
        if self.openai_key:
            self.openai_client = OpenAI(api_key=self.openai_key, base_url=self.openai_url)
        else:
            self.openai_client = None

    def _init_gemini(self):
        if self.gemini_key:
            genai.configure(api_key=self.gemini_key)
            self.gemini_model_obj = genai.GenerativeModel(
                self.gemini_model,
                system_instruction=get_system_prompt(),
            )
            self.gemini_chat = self.gemini_model_obj.start_chat(history=[])
        else:
            self.gemini_model_obj = None
            self.gemini_chat = None

    def reconfigure(self, provider: str, openai_key: str, openai_url: str, openai_model: str,
                    gemini_key: str, gemini_model: str) -> None:
        self.provider = provider
        self.openai_key = openai_key
        self.openai_url = openai_url
        self.openai_model = openai_model
        self.gemini_key = gemini_key
        self.gemini_model = gemini_model

        self._init_openai()
        self._init_gemini()

    def reset_history(self) -> None:
        self.history.clear()
        if self.gemini_model_obj:
            self.gemini_chat = self.gemini_model_obj.start_chat(history=[])

    # ── Feature 1: Smart Context Compression (Long-Memory Management) ─────────────
    def _compress_history_if_needed(self):
        """Cap and summarize long conversation history to conserve token budget."""
        if len(self.history) > 10:
            # Keep first message, compress middle history, keep last 4 messages
            first_msg = self.history[0]
            recent_msgs = self.history[-4:]
            
            summary_text = f"[System Memory Summary: Previous session involved {len(self.history) - 5} command executions and analyses.]"
            summary_msg = {"role": "system", "content": summary_text}
            
            self.history = [first_msg, summary_msg] + recent_msgs

    def test_connection(self) -> tuple[bool, str]:
        if self.provider == "openai":
            return self._test_openai()
        else:
            return self._test_gemini()

    def _test_openai(self) -> tuple[bool, str]:
        if not self.openai_key:
            return False, "OpenAI API key is not set"
        if not self.openai_url:
            return False, "OpenAI Base URL is not set"

        try:
            client = OpenAI(api_key=self.openai_key, base_url=self.openai_url)
            response = client.models.list()
            model_count = len(list(response.data)) if hasattr(response, 'data') else 0
            return True, f"Connected successfully! {model_count} models available"
        except Exception:
            try:
                client = OpenAI(api_key=self.openai_key, base_url=self.openai_url)
                client.chat.completions.create(
                    model=self.openai_model,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=5
                )
                return True, f"Connected! Using model: {self.openai_model}"
            except Exception as e2:
                return False, f"Connection failed: {str(e2)}"

    def _test_gemini(self) -> tuple[bool, str]:
        if not self.gemini_key:
            return False, "Gemini API key is not set"

        try:
            genai.configure(api_key=self.gemini_key)
            model = genai.GenerativeModel(self.gemini_model)
            response = model.generate_content("Hi")
            return True, f"Connected! Using model: {self.gemini_model}"
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower():
                return False, "⚠️ Gemini Rate Limit / Quota Exceeded (HTTP 429)!\nWait 60s or switch model to 'gemini-1.5-flash'."
            elif "api_key" in err.lower() or "invalid" in err.lower():
                return False, "❌ Invalid Gemini API Key. Please check your key at aistudio.google.com"
            return False, f"Connection failed: {err[:150]}"

    def get_available_models(self) -> list[str]:
        if self.provider == "openai":
            return self._get_openai_models()
        else:
            return self._get_gemini_models()

    def _get_openai_models(self) -> list[str]:
        if not self.openai_key:
            return []

        # Strategy 1: Direct HTTP GET /models to handle OpenRouter / AgentRouter / Custom Gateways
        try:
            import requests
            base = self.openai_url.rstrip('/')
            url = base if base.endswith('/models') else (f"{base}/models" if base.endswith('/v1') else f"{base}/v1/models")
            headers = {"Authorization": f"Bearer {self.openai_key}"}
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code == 200:
                data = r.json()
                items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                models = [m.get("id") for m in items if isinstance(m, dict) and m.get("id")]
                if models:
                    return sorted(list(set(models)))
        except Exception:
            pass

        # Strategy 2: OpenAI Client SDK list()
        try:
            client = OpenAI(api_key=self.openai_key, base_url=self.openai_url)
            response = client.models.list()
            data = getattr(response, "data", [])
            models = [m.id if hasattr(m, "id") else (m.get("id") if isinstance(m, dict) else str(m)) for m in data]
            models = [str(m) for m in models if m]
            if models:
                return sorted(list(set(models)))
        except Exception:
            pass

        return [
            "gpt-4o",
            "gpt-4o-mini",
            "claude-3-5-sonnet",
            "claude-3-opus",
            "deepseek-coder",
            "llama-3-70b",
        ]

    def _get_gemini_models(self) -> list[str]:
        if not self.gemini_key:
            return []

        try:
            genai.configure(api_key=self.gemini_key)
            models = genai.list_models()
            result = []
            for m in models:
                methods = getattr(m, 'supported_generation_methods', [])
                if 'generateContent' in methods:
                    name = m.name.replace('models/', '')
                    result.append(name)
            if result:
                return sorted(list(set(result)))
        except Exception:
            pass

        return [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]

    def send(
        self,
        user_text: str,
        attach_screenshot: bool = True,
        terminal_output: Optional[str] = None,
        image_paths: Optional[list[str]] = None,
    ) -> dict:
        self._compress_history_if_needed()
        
        if self.provider == "openai":
            return self._send_openai(user_text, attach_screenshot, terminal_output, image_paths)
        else:
            return self._send_gemini(user_text, attach_screenshot, terminal_output, image_paths)

    def _send_openai(
        self,
        user_text: str,
        attach_screenshot: bool = True,
        terminal_output: Optional[str] = None,
        image_paths: Optional[list[str]] = None,
    ) -> dict:
        if not self.openai_client:
            raise RuntimeError("OpenAI client not initialized. Check API key.")

        content: list[dict] = []

        # Feature 2 & 3: Inject reflection prompt & RAG tool docs if output is present
        if terminal_output:
            rag_docs = ""
            # Extract first word of potential failed/executed command for RAG
            first_cmd = terminal_output.strip().split()[0] if terminal_output.strip() else ""
            if first_cmd:
                rag_docs = fetch_tool_help_rag(first_cmd)
                
            content.append({
                "type": "text",
                "text": f"[Terminal Execution Output]\n{terminal_output}\n{rag_docs}",
            })

        if user_text:
            content.append({"type": "text", "text": user_text})

        if image_paths:
            for img_path in image_paths:
                try:
                    b64_data, mime_type = _load_image_b64(img_path)
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_data}",
                            "detail": "low",
                        },
                    })
                except Exception as exc:
                    content.append({"type": "text", "text": f"[Image load failed: {img_path}: {exc}]"})

        if attach_screenshot:
            try:
                b64 = capture_screenshot_b64()
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "low",
                    },
                })
            except Exception as exc:
                content.append({"type": "text", "text": f"[Screenshot capture failed: {exc}]"})

        user_message = {"role": "user", "content": content}
        self.history.append(user_message)

        messages = [{"role": "system", "content": get_system_prompt()}] + self.history

        response = self.openai_client.chat.completions.create(
            model=self.openai_model,
            messages=messages,
            max_tokens=2048,
            temperature=0.7,
            timeout=45.0,
        )

        if isinstance(response, str):
            raw_reply = response
        elif isinstance(response, dict):
            choices = response.get("choices", [])
            if choices and isinstance(choices[0], dict):
                raw_reply = choices[0].get("message", {}).get("content", "")
            else:
                raw_reply = str(response)
        elif hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                raw_reply = choice.message.content or ""
            elif isinstance(choice, dict):
                raw_reply = choice.get("message", {}).get("content", "")
            else:
                raw_reply = str(choice)
        else:
            raw_reply = str(response)

        self.history.append({"role": "assistant", "content": raw_reply})
        return _extract_and_validate_json(raw_reply)

    def _send_gemini(
        self,
        user_text: str,
        attach_screenshot: bool = True,
        terminal_output: Optional[str] = None,
        image_paths: Optional[list[str]] = None,
    ) -> dict:
        if not self.gemini_model_obj:
            raise RuntimeError("Gemini model not initialized. Check API key.")

        parts = []

        if terminal_output:
            rag_docs = ""
            first_cmd = terminal_output.strip().split()[0] if terminal_output.strip() else ""
            if first_cmd:
                rag_docs = fetch_tool_help_rag(first_cmd)
                
            parts.append(f"[Terminal Execution Output]\n{terminal_output}\n{rag_docs}\n")

        if user_text:
            parts.append(user_text)

        if image_paths:
            for img_path in image_paths:
                try:
                    b64_data, mime_type = _load_image_b64(img_path)
                    image_bytes = base64.b64decode(b64_data)
                    parts.append({"mime_type": mime_type, "data": image_bytes})
                    parts.append("[User attached image above]")
                except Exception as exc:
                    parts.append(f"[Image load failed: {img_path}: {exc}]")

        if attach_screenshot:
            try:
                b64 = capture_screenshot_b64()
                screenshot_bytes = base64.b64decode(b64)
                parts.append({"mime_type": "image/jpeg", "data": screenshot_bytes})
                parts.append("[Screenshot attached above]")
            except Exception as exc:
                parts.append(f"[Screenshot capture failed: {exc}]")

        try:
            if self.gemini_chat is None:
                self.gemini_chat = self.gemini_model_obj.start_chat(history=[])

            response = self.gemini_chat.send_message(
                parts,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 2048,
                },
                request_options={"timeout": 45.0}
            )

            raw_reply = response.text
            return _extract_and_validate_json(raw_reply)

        except Exception as e:
            error_str = str(e)
            if "history" in error_str.lower() or "invalid" in error_str.lower():
                self.gemini_chat = self.gemini_model_obj.start_chat(history=[])
                try:
                    response = self.gemini_chat.send_message(
                        parts,
                        generation_config={
                            "temperature": 0.7,
                            "max_output_tokens": 2048,
                        },
                        request_options={"timeout": 45.0}
                    )
                    raw_reply = response.text
                    return _extract_and_validate_json(raw_reply)
                except Exception as e2:
                    raise RuntimeError(f"Gemini API error (retry): {str(e2)}")
            raise RuntimeError(f"Gemini API error: {error_str}")
