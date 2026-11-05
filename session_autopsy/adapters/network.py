"""Runtime egress: fixed public documentation, without caller-controlled URLs."""
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

DOCUMENTS = {
    "anthropic-prices": "https://platform.claude.com/docs/en/about-claude/pricing.md",
    "openai-prices": "https://developers.openai.com/api/docs/pricing.md",
    "claude-prompting": "https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices.md",
    "openai-prompting": "https://developers.openai.com/api/docs/guides/latest-model.md",
    "claude-agents": "https://code.claude.com/docs/en/sub-agents.md",
    "codex-agents": "https://learn.chatgpt.com/docs/agent-configuration/subagents.md",
}


class FixedRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if newurl not in DOCUMENTS.values():
            raise ValueError("Redirect outside fixed documentation allowlist")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_document(name):
    if name not in DOCUMENTS:
        raise ValueError("Unknown public document")
    opener = build_opener(ProxyHandler({}), HTTPSHandler(), FixedRedirects())
    request = Request(DOCUMENTS[name], headers={"User-Agent": "session-autopsy/0.1"})
    with opener.open(request, timeout=20) as response:
        content = response.read(2_000_001)
    if len(content) > 2_000_000:
        raise ValueError("Documentation exceeds size limit")
    return content.decode("utf-8")
