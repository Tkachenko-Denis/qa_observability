from __future__ import annotations


def render_links_markdown_table(links: list[dict[str, str]]) -> str:
    rows = ["| Service | Purpose |", "| --- | --- |"]
    for item in links:
        system = str(item["system"]).replace("|", "\\|")
        url = str(item["url"]).replace(")", "%29")
        purpose = str(item["purpose"]).replace("|", "\\|")
        rows.append(f"| [{system}]({url}) | {purpose} |")
    return "\n".join(rows)
