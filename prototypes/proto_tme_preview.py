"""PROTOTYPE — throwaway. Delete after S02. Answers: does t.me/s parsing + ?before= work?

Run:  uv run --with selectolax python prototypes/proto_tme_preview.py
"""
import sys, io, json, urllib.request
from selectolax.parser import HTMLParser

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

UA = {"User-Agent": "Mozilla/5.0 (proto)"}
FIX = "tests/fixtures"


def fetch(channel, before=None):
    url = f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return url, r.read().decode("utf-8", "replace")


def parse(html):
    tree = HTMLParser(html)
    posts = []
    for w in tree.css("div.tgme_widget_message"):
        data_post = w.attributes.get("data-post")  # "channel/12345"
        msg_id = int(data_post.split("/")[-1]) if data_post else None
        text_node = w.css_first(".tgme_widget_message_text")
        text = text_node.text(separator="\n", strip=True) if text_node else ""
        date_a = w.css_first("a.tgme_widget_message_date")
        permalink = date_a.attributes.get("href") if date_a else None
        time_node = w.css_first("time")
        dt = time_node.attributes.get("datetime") if time_node else None
        posts.append({"id": msg_id, "dt": dt, "permalink": permalink,
                      "text": (text[:80] + "…") if len(text) > 80 else text})
    return posts


def main():
    import os
    os.makedirs(FIX, exist_ok=True)
    ch = sys.argv[1] if len(sys.argv) > 1 else "telegram"

    url1, html1 = fetch(ch)
    p1 = parse(html1)
    open(f"{FIX}/{ch}_page1.html", "w", encoding="utf-8").write(html1)
    print(f"=== PAGE 1: {url1} ===")
    print(f"posts parsed: {len(p1)}")
    for p in p1[:3]:
        print(json.dumps(p, ensure_ascii=False))
    ids1 = [p["id"] for p in p1 if p["id"]]
    print(f"id range page1: min={min(ids1)} max={max(ids1)}")

    # pagination: ?before=<min id of page1> should return OLDER posts
    before = min(ids1)
    url2, html2 = fetch(ch, before=before)
    p2 = parse(html2)
    open(f"{FIX}/{ch}_page2_before{before}.html", "w", encoding="utf-8").write(html2)
    ids2 = [p["id"] for p in p2 if p["id"]]
    print(f"\n=== PAGE 2: {url2} ===")
    print(f"posts parsed: {len(p2)}  id range: min={min(ids2)} max={max(ids2)}")
    print(f"pagination OK (page2 max < page1 min)? {max(ids2) < before}")
    print(f"overlap ids: {sorted(set(ids1) & set(ids2))}")

    print(f"\nfixtures written under {FIX}/")


if __name__ == "__main__":
    main()
