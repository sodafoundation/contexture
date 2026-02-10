import json
from pathlib import Path
from jinja2 import Template
from datetime import datetime

import os
import dotenv
dotenv.load_dotenv()

template_dir = os.getenv("TEMPLATE_PATH")
override_path = os.getenv("OVERRIDE_PATH")
examples_path = os.getenv("EXAMPLES_PATH")
info_path = os.getenv("INFO_PATH")

class PromptBuilder:
    def __init__(self, template_dir=template_dir):
        self.sections = {}
        self.load_sections(template_dir)
        self.context_chunks = []
        self.user_question = ""
        self.overrides = {}
        self.golden_examples = []
        self.additional_info = {}

    def load_sections(self, template_dir):
        for file in Path(template_dir).glob("*.md"):
            self.sections[file.stem] = file.read_text()

    def with_context(self, chunks):
        self.context_chunks = chunks
        return self

    def with_user_question(self, question):
        self.user_question = question
        return self

    def with_overrides(self, override_path=override_path):
        path = Path(override_path)
        if path.exists():
            content = path.read_text().strip()
            if content:
                self.overrides = json.loads(content)
        return self

    def with_golden_examples(self, examples_path=examples_path):
        path = Path(examples_path)
        if path.exists():
            content = path.read_text().strip()
            if content:
                self.golden_examples = json.loads(content)
        return self

    def with_additional_info(self, info_path=info_path):
        path = Path(info_path)
        if path.exists():
            content = path.read_text().strip()
            if content:
                self.additional_info = json.loads(content)
        return self

    def build(self):
        now = datetime.utcnow()
        template = """
{{ system }}

{{ domain }}

{% for example in golden_examples %}
Example:
Q: {{ example.question }}
A: {{ example.answer }}
{% endfor %}

{% if context_chunks %}
Relevant Prometheus Metrics:
{% for chunk in context_chunks %}
{{ chunk }}
{% endfor %}
{% endif %}

{% if additional_info %}
Additional Information:
{% for key, value in additional_info.items() %}
{{ key }}: {{ value }}
{% endfor %}
{% endif %}

{{ postamble }}
{{ overrides_text }}

Now process this user question and generate the PromQL query:
{{ user_question }}
"""
        prompt = Template(template).render(
            system=self.sections.get("system", ""),
            domain=self.sections.get("domain", ""),
            postamble=Template(self.sections.get("postamble", "")).render(current_time=now.isoformat() + "Z"),
            golden_examples=self.golden_examples,
            context_chunks=self.context_chunks,
            user_question=self.user_question,
            overrides_text="\n".join(f"{k}: {v}" for k, v in self.overrides.items()),
            additional_info=self.additional_info
        )
        return prompt