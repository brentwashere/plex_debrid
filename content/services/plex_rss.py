from base import *

import json
import os
import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace


rss_url = "https://rss.plex.tv/a3e0d5e5-3420-4221-aedf-3474f5569802"
sync_user = 0

STATE_FILE = "plex_rss_synced.json"


def _config_dir():
    # plex_debrid normally runs with --config-dir config, which is mounted
    # to /config in your container.
    if os.path.isdir("/config"):
        return "/config"

    if os.path.isdir("config"):
        return "config"

    return "."


def _state_path():
    return os.path.join(_config_dir(), STATE_FILE)


def _load_state():
    try:
        with open(_state_path(), "r") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data
    except:
        pass

    return {}


def _save_state(state):
    try:
        with open(_state_path(), "w") as f:
            json.dump(state, f, indent=2, sort_keys=True)
    except Exception as e:
        print("[plex rss] could not save sync state:", str(e), flush=True)


def _fetch(url, timeout=20):
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0 plex_debrid RSS importer"
        }
    )
    response.raise_for_status()
    return response


def _parse_feed():
    if not rss_url:
        return []

    response = _fetch(rss_url)

    root = ET.fromstring(response.content)

    items = []

    for node in root.findall("./channel/item"):
        title = node.findtext("title", "").strip()
        link = node.findtext("link", "").strip()
        category = node.findtext("category", "").strip().lower()
        author = node.findtext("author", "").strip()
        pub_date = node.findtext("pubDate", "").strip()

        guid_node = node.find("guid")
        guid = ""

        if guid_node is not None and guid_node.text:
            guid = guid_node.text.strip()

        if not title or not link:
            continue

        if category not in ("movie", "show", "tv"):
            continue

        items.append({
            "title": title,
            "link": link,
            "category": category,
            "guid": guid,
            "author": author,
            "pubDate": pub_date,
        })

    return items


def _resolve_watch_page(item):
    response = _fetch(item["link"])
    html = response.text

    # watch.plex.tv embeds the canonical Plex metadata object in its
    # server-rendered page data:
    #
    # "guid":"plex://movie/<id>"
    # "key":"/library/metadata/<id>"
    # "ratingKey":"<id>"
    # "title":"..."
    # "type":"movie"
    #
    # The HTML may contain escaped quotes because this data can live
    # inside serialized Next.js payloads.

    normalized = html.replace('\\"', '"')

    patterns = [
        re.compile(
            r'"guid":"plex://(?P<type>movie|show)/(?P<id>[A-Za-z0-9]+)".{0,1000}?'
            r'"ratingKey":"(?P=id)"',
            re.S
        ),
        re.compile(
            r'"key":"/library/metadata/(?P<id>[A-Za-z0-9]+)".{0,500}?'
            r'"ratingKey":"(?P=id)".{0,500}?'
            r'"type":"(?P<type>movie|show)"',
            re.S
        ),
    ]

    match = None

    for pattern in patterns:
        match = pattern.search(normalized)
        if match:
            break

    if not match:
        raise Exception("could not locate Plex metadata ID in watch page")

    media_type = match.group("type")
    rating_key = match.group("id")

    expected_type = "show" if item["category"] in ("show", "tv") else "movie"

    if media_type != expected_type:
        raise Exception(
            "resolved media type %s does not match RSS type %s"
            % (media_type, expected_type)
        )

    # Remove the trailing year from the RSS title for cleaner log output.
    display_title = re.sub(r"\s+\(\d{4}\)$", "", item["title"]).strip()

    return SimpleNamespace(
        title=display_title,
        ratingKey=rating_key,
        type=media_type
    )


def sync(watchlist):
    """
    Copy previously unseen entries from Plex Friends RSS into one of the
    configured Plex users' real Plex Watchlists.

    Once an RSS GUID/link has been successfully imported, it is recorded
    in /config/plex_rss_synced.json so plex_debrid can later remove the
    title without the RSS importer immediately adding it again.
    """

    if not rss_url:
        return False

    from content.services import plex

    if len(plex.users) == 0:
        print("[plex rss] no Plex users configured; skipping RSS sync", flush=True)
        return False

    try:
        user_index = int(sync_user)
    except:
        user_index = 0

    if user_index < 0 or user_index >= len(plex.users):
        user_index = 0

    user = plex.users[user_index]

    state = _load_state()

    try:
        items = _parse_feed()
    except Exception as e:
        print("[plex rss] feed error:", str(e), flush=True)
        return False

    added_any = False

    for rss_item in reversed(items):
        state_key = rss_item["guid"] or rss_item["link"]

        if state_key in state:
            continue

        try:
            item = _resolve_watch_page(rss_item)

            # If it is already present in the in-memory Plex watchlist,
            # consider it synchronized without adding it again.
            already_present = False

            for existing in watchlist.data:
                try:
                    if str(existing.ratingKey) == str(item.ratingKey):
                        already_present = True
                        break
                except:
                    pass

            if already_present:
                print(
                    '[plex rss] already on %s`s watchlist: "%s"'
                    % (user[0], item.title),
                    flush=True
                )
            else:
                print(
                    '[plex rss] importing "%s" from shared Plex RSS'
                    % item.title,
                    flush=True
                )

                watchlist.add(item, user)
                added_any = True

            state[state_key] = {
                "title": rss_item["title"],
                "guid": rss_item["guid"],
                "author": rss_item["author"],
                "link": rss_item["link"],
                "ratingKey": item.ratingKey,
                "type": item.type,
                "pubDate": rss_item["pubDate"],
            }

            _save_state(state)

        except Exception as e:
            print(
                '[plex rss] could not import "%s": %s'
                % (rss_item["title"], str(e)),
                flush=True
            )

    return added_any
