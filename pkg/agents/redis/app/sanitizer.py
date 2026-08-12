import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml

PUBLIC_CATEGORY = "public"
CONDITIONAL_CATEGORY = "conditional"
ALWAYS_BLOCKED_CATEGORY = "always_blocked"

DEFAULT_POLICY_CONFIG: Dict[str, Dict[str, Any]] = {
    "name": {
        "category": PUBLIC_CATEGORY,
        "aliases": ["name", "full_name", "display_name"],
    },
    "status": {
        "category": PUBLIC_CATEGORY,
        "aliases": ["status", "state"],
    },
    "age": {
        "category": PUBLIC_CATEGORY,
        "aliases": ["age"],
    },
    "timestamp": {
        "category": PUBLIC_CATEGORY,
        "aliases": ["timestamp", "created_at", "updated_at", "created", "updated"],
    },
    "email": {
        "category": CONDITIONAL_CATEGORY,
        "aliases": ["email", "e-mail", "email_address", "email address"],
        "question_patterns": [r"\bemail\b", r"\be-mail\b", r"\bemail address\b"],
        "value_pattern": r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    },
    "phone": {
        "category": CONDITIONAL_CATEGORY,
        "aliases": ["phone", "phone_number", "phone number", "mobile", "cell", "cell phone"],
        "question_patterns": [r"\bphone\b", r"\bphone number\b", r"\bmobile\b", r"\bcell phone\b"],
        "value_pattern": r"^\+?[0-9][0-9\-\s().]{6,}$",
    },
    "address": {
        "category": CONDITIONAL_CATEGORY,
        "aliases": ["address", "mailing_address", "mailing address", "street_address", "street address"],
        "question_patterns": [r"\baddress\b", r"\bmailing address\b", r"\bstreet address\b"],
    },
    "salary": {
        "category": CONDITIONAL_CATEGORY,
        "aliases": ["salary", "pay", "compensation", "wage"],
        "question_patterns": [r"\bsalary\b", r"\bpay\b", r"\bcompensation\b", r"\bwage\b"],
        "value_pattern": r"^\$?\d[\d,]*(?:\.\d{2})?$",
    },
    "date_of_birth": {
        "category": CONDITIONAL_CATEGORY,
        "aliases": ["dob", "date_of_birth", "date of birth", "birthdate", "birthday"],
        "question_patterns": [r"\bdob\b", r"\bdate of birth\b", r"\bbirthdate\b", r"\bbirthday\b"],
    },
    "password": {
        "category": ALWAYS_BLOCKED_CATEGORY,
        "aliases": ["password", "passwd", "passcode", "pin"],
        "question_patterns": [r"\bpassword\b", r"\bpasswd\b", r"\bpasscode\b", r"\bpin\b"],
    },
    "secret": {
        "category": ALWAYS_BLOCKED_CATEGORY,
        "aliases": ["secret", "secrets", "client_secret", "client secret", "private_secret", "private secret"],
        "question_patterns": [r"\bsecret\b", r"\bclient secret\b", r"\bprivate secret\b"],
    },
    "token": {
        "category": ALWAYS_BLOCKED_CATEGORY,
        "aliases": [
            "token",
            "tokens",
            "api_token",
            "api token",
            "access_token",
            "access token",
            "refresh_token",
            "refresh token",
            "auth_token",
            "auth token",
            "session_token",
            "session token",
            "id_token",
            "id token",
        ],
        "question_patterns": [r"\btoken\b", r"\bapi token\b", r"\baccess token\b", r"\brefresh token\b"],
    },
    "api_key": {
        "category": ALWAYS_BLOCKED_CATEGORY,
        "aliases": ["api_key", "api key", "apikey", "access_key", "access key"],
        "question_patterns": [r"\bapi key\b", r"\bapikey\b", r"\baccess key\b"],
    },
    "private_key": {
        "category": ALWAYS_BLOCKED_CATEGORY,
        "aliases": ["private_key", "private key", "ssh_key", "ssh key", "rsa_private_key", "rsa private key"],
        "question_patterns": [r"\bprivate key\b", r"\bssh key\b", r"\brsa private key\b"],
    },
    "credential": {
        "category": ALWAYS_BLOCKED_CATEGORY,
        "aliases": ["credential", "credentials", "secret_key", "secret key"],
        "question_patterns": [r"\bcredential\b", r"\bcredentials\b"],
    },
}

KEY_LIKE_FIELDS = {
    "key",
    "keys",
    "sample_keys",
    "from_pattern",
    "to_pattern",
    "pattern",
    "patterns",
    "referenced_patterns",
}


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _metadata_for_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return {
            "sanitized": True,
            "value_type": "string",
            "length": len(value),
        }
    if isinstance(value, (int, float, bool)):
        return {
            "sanitized": True,
            "value_type": type(value).__name__,
        }
    return {
        "sanitized": True,
        "value_type": type(value).__name__,
    }


def _looks_like_bulk_request(question: str) -> bool:
    lowered = question.lower()
    return any(
        phrase in lowered
        for phrase in [
            "list all",
            "show all",
            "all users",
            "all records",
            "all items",
            "all customers",
            "all accounts",
            "every user",
            "every record",
            "each user",
            "each record",
            "dump all",
            "export all",
        ]
    )


@dataclass(frozen=True)
class PolicyRule:
    name: str
    category: str
    aliases: Tuple[str, ...] = ()
    question_patterns: Tuple[str, ...] = ()
    value_pattern: Optional[str] = None


@dataclass
class SanitizationReport:
    applied: bool = False
    redacted_fields: int = 0

    def mark_redaction(self, count: int = 1) -> None:
        self.applied = True
        self.redacted_fields += count

    def merge(self, other: "SanitizationReport") -> None:
        if other.applied:
            self.applied = True
        self.redacted_fields += other.redacted_fields


@dataclass
class SanitizationPolicy:
    rules: Dict[str, PolicyRule] = field(default_factory=dict)
    alias_index: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "SanitizationPolicy":
        return cls.from_config({})

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "SanitizationPolicy":
        rules: Dict[str, PolicyRule] = {}

        for name, spec in DEFAULT_POLICY_CONFIG.items():
            rules[name] = PolicyRule(
                name=name,
                category=spec["category"],
                aliases=tuple(spec.get("aliases", [])),
                question_patterns=tuple(spec.get("question_patterns", [])),
                value_pattern=spec.get("value_pattern"),
            )

        custom_policies = cfg.get("field_policies", {})
        if isinstance(custom_policies, dict):
            for name, spec in custom_policies.items():
                if not isinstance(spec, dict):
                    continue
                category = str(spec.get("category", PUBLIC_CATEGORY)).lower()
                aliases = tuple(spec.get("aliases", []) or [])
                question_patterns = tuple(spec.get("question_patterns", []) or [])
                value_pattern = spec.get("value_pattern")
                rules[_normalize_name(str(name))] = PolicyRule(
                    name=_normalize_name(str(name)),
                    category=category,
                    aliases=aliases,
                    question_patterns=question_patterns,
                    value_pattern=value_pattern,
                )

        alias_index: Dict[str, str] = {}
        for rule in rules.values():
            alias_index[_normalize_name(rule.name)] = rule.name
            for alias in rule.aliases:
                alias_index[_normalize_name(alias)] = rule.name

        return cls(rules=rules, alias_index=alias_index)

    def canonical_name(self, field_name: str) -> str:
        normalized = _normalize_name(field_name)
        return self.alias_index.get(normalized, normalized)

    def rule_for(self, field_name: str) -> PolicyRule:
        canonical = self.canonical_name(field_name)
        if canonical in self.rules:
            return self.rules[canonical]
        return PolicyRule(name=canonical, category=PUBLIC_CATEGORY)

    def category_for(self, field_name: str) -> str:
        return self.rule_for(field_name).category

    def question_mentions_rule(self, question: str, rule: PolicyRule) -> bool:
        lowered = question.lower()
        for pattern in rule.question_patterns:
            if re.search(pattern, lowered):
                return True
        for alias in rule.aliases:
            if alias and alias.lower() in lowered:
                return True
        return False

    def requested_fields(self, question: str) -> List[str]:
        requested = []
        for rule in self.rules.values():
            if rule.category == ALWAYS_BLOCKED_CATEGORY:
                continue
            if self.question_mentions_rule(question, rule):
                requested.append(rule.name)
        return requested

    def allows_final_field(
        self,
        question: str,
        field_name: str,
        value: Any = None,
        tool_name: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> bool:
        rule = self.rule_for(field_name)
        if rule.category == ALWAYS_BLOCKED_CATEGORY:
            return False
        if rule.category == PUBLIC_CATEGORY:
            return True
        if _looks_like_bulk_request(question):
            return False
        if not self.question_mentions_rule(question, rule):
            return False
        if value is None:
            return True
        if self._value_matches_rule(rule, value):
            return True
        if self._context_implies_field(field_name, tool_name, arguments):
            return True
        return False

    def _context_implies_field(
        self,
        field_name: str,
        tool_name: Optional[str],
        arguments: Optional[Dict[str, Any]],
    ) -> bool:
        if not arguments:
            return False
        key = arguments.get("key")
        if not isinstance(key, str):
            return False
        normalized_key = _normalize_name(key)
        canonical = self.canonical_name(field_name)
        return canonical in normalized_key or field_name in normalized_key

    def _value_matches_rule(self, rule: PolicyRule, value: Any) -> bool:
        if not isinstance(value, str):
            return True
        if rule.value_pattern and re.search(rule.value_pattern, value):
            return True
        if rule.name == "address":
            return len(value.strip()) > 0
        if rule.name == "salary":
            return bool(re.search(r"^\$?\d[\d,]*(?:\.\d{2})?$", value.strip()))
        return True


class DataSanitizer:
    def __init__(self, policy: Optional[SanitizationPolicy] = None):
        self.policy = policy or SanitizationPolicy.default()

    @classmethod
    def from_runtime_config(cls) -> "DataSanitizer":
        return cls(policy=cls._load_policy_from_config())

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        base_dir = os.path.abspath(__file__)
        for _ in range(5):
            base_dir = os.path.dirname(base_dir)
        config_path = os.path.join(base_dir, "config", "redis_config.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    @classmethod
    def _load_policy_from_config(cls) -> SanitizationPolicy:
        config = cls._load_config()
        sanitizer_cfg = config.get("sanitizer", {})
        if not isinstance(sanitizer_cfg, dict):
            sanitizer_cfg = {}
        return SanitizationPolicy.from_config(sanitizer_cfg)

    def sanitize_schema(self, payload: Any) -> Tuple[Any, SanitizationReport]:
        return payload, SanitizationReport()

    def sanitize_tool_output_for_llm_text(
        self,
        text: str,
        tool_name: Optional[str] = None,
    ) -> Tuple[str, SanitizationReport]:
        return self._sanitize_text_metadata(text, tool_name=tool_name)

    def sanitize_tool_output_for_log_text(
        self,
        text: str,
        tool_name: Optional[str] = None,
    ) -> Tuple[str, SanitizationReport]:
        return self._sanitize_text_metadata(text, tool_name=tool_name)

    def sanitize_tool_output_for_final_answer(
        self,
        payload: Any,
        question: str,
        tool_name: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, SanitizationReport]:
        report = SanitizationReport()
        return self._sanitize_final(payload, question, report, parent_key=None, tool_name=tool_name, arguments=arguments), report

    def sanitize_tool_output_for_final_answer_text(
        self,
        text: str,
        question: str,
        tool_name: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, SanitizationReport]:
        try:
            parsed = json.loads(text)
        except Exception:
            report = SanitizationReport()
            requested = [
                field_name
                for field_name in self.policy.requested_fields(question)
                if self.policy.category_for(field_name) == CONDITIONAL_CATEGORY
            ]
            if tool_name == "get" and requested and not _looks_like_bulk_request(question):
                return text, report
            return self._sanitize_text_metadata(text)

        sanitized, report = self.sanitize_tool_output_for_final_answer(
            parsed,
            question=question,
            tool_name=tool_name,
            arguments=arguments,
        )
        return json.dumps(sanitized), report

    def sanitize_text_for_llm(self, text: str) -> Tuple[str, SanitizationReport]:
        return self._sanitize_text_metadata(text)

    def sanitize_text_for_log(self, text: str) -> Tuple[str, SanitizationReport]:
        return self._sanitize_text_metadata(text)

    def _sanitize_text_metadata(self, text: str, tool_name: Optional[str] = None) -> Tuple[str, SanitizationReport]:
        report = SanitizationReport()
        try:
            parsed = json.loads(text)
        except Exception:
            report.mark_redaction()
            return json.dumps(
                {
                    "sanitized": True,
                    "content_type": "text",
                    "length": len(text),
                }
            ), report

        sanitized = self._sanitize_metadata(parsed, report, parent_key=None, tool_name=tool_name)
        return json.dumps(sanitized), report

    def _sanitize_metadata(
        self,
        value: Any,
        report: SanitizationReport,
        parent_key: Optional[str],
        tool_name: Optional[str] = None,
    ) -> Any:
        if isinstance(value, dict):
            sanitized: Dict[str, Any] = {}
            for key, child in value.items():
                sanitized[key] = self._sanitize_metadata(child, report, str(key), tool_name=tool_name)
            return sanitized

        if isinstance(value, list):
            return [self._sanitize_metadata(item, report, parent_key, tool_name=tool_name) for item in value]

        if isinstance(value, tuple):
            return [self._sanitize_metadata(item, report, parent_key, tool_name=tool_name) for item in value]

        if isinstance(value, str):
            if tool_name == "scan_keys" and parent_key == "keys":
                return value
            if parent_key and _normalize_name(parent_key) in KEY_LIKE_FIELDS:
                report.mark_redaction()
                return self._normalize_redis_key(value)
            report.mark_redaction()
            return _metadata_for_scalar(value)

        if isinstance(value, (int, float, bool)) or value is None:
            report.mark_redaction()
            return _metadata_for_scalar(value)

        report.mark_redaction()
        return _metadata_for_scalar(value)

    def _sanitize_final(
        self,
        value: Any,
        question: str,
        report: SanitizationReport,
        parent_key: Optional[str],
        tool_name: Optional[str],
        arguments: Optional[Dict[str, Any]],
    ) -> Any:
        if isinstance(value, dict):
            sanitized: Dict[str, Any] = {}
            for key, child in value.items():
                sanitized[key] = self._sanitize_final(
                    child,
                    question,
                    report,
                    parent_key=str(key),
                    tool_name=tool_name,
                    arguments=arguments,
                )
            return sanitized

        if isinstance(value, list):
            return [
                self._sanitize_final(
                    item,
                    question,
                    report,
                    parent_key=parent_key,
                    tool_name=tool_name,
                    arguments=arguments,
                )
                for item in value
            ]

        if isinstance(value, tuple):
            return [
                self._sanitize_final(
                    item,
                    question,
                    report,
                    parent_key=parent_key,
                    tool_name=tool_name,
                    arguments=arguments,
                )
                for item in value
            ]

        if parent_key is None:
            if tool_name == "get" and isinstance(arguments, dict):
                inferred_field = self._infer_field_from_arguments(arguments)
                if inferred_field and self.policy.allows_final_field(question, inferred_field, value=value, tool_name=tool_name, arguments=arguments):
                    return value
            report.mark_redaction()
            return _metadata_for_scalar(value)

        rule = self.policy.rule_for(parent_key)
        if rule.category == ALWAYS_BLOCKED_CATEGORY:
            report.mark_redaction()
            return "[REDACTED]"

        if rule.category == PUBLIC_CATEGORY:
            return value

        if self.policy.allows_final_field(question, rule.name, value=value, tool_name=tool_name, arguments=arguments):
            return value

        report.mark_redaction()
        return "[REDACTED]"

    def _infer_field_from_arguments(self, arguments: Dict[str, Any]) -> Optional[str]:
        key = arguments.get("key")
        if not isinstance(key, str):
            return None

        normalized_key = _normalize_name(key)
        for rule in self.policy.rules.values():
            if rule.category == ALWAYS_BLOCKED_CATEGORY:
                continue
            if _normalize_name(rule.name) in normalized_key:
                return rule.name
            for alias in rule.aliases:
                if _normalize_name(alias) in normalized_key:
                    return rule.name
        return None

    def _normalize_redis_key(self, key: str) -> str:
        if ":" not in key:
            return key

        normalized_parts: List[str] = []
        for part in key.split(":"):
            if self._looks_dynamic_segment(part):
                normalized_parts.append("*")
            else:
                normalized_parts.append(part)
        return ":".join(normalized_parts)

    @staticmethod
    def _looks_dynamic_segment(part: str) -> bool:
        if not part:
            return False
        if part.isdigit():
            return True
        if re.fullmatch(r"[0-9a-fA-F-]{8,}", part):
            return True
        if len(part) >= 8 and any(ch.isdigit() for ch in part):
            return True
        return False
